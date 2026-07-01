import hashlib
import json
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.sql import text, func
from sqlalchemy.dialects.postgresql import insert
from database import ProcessedSite, PolicyChunk
from ai_engine import embedding_model


async def get_scan_by_url_async(db: AsyncSession, url: str):
    url_hash = hashlib.md5(url.encode()).hexdigest()
    result = await db.execute(select(ProcessedSite).filter(ProcessedSite.url_hash == url_hash))
    return result.scalars().first()

async def get_relevant_chunks_async(db: AsyncSession, base_url: str, query_embedding: list, limit: int = 30):
    result = await db.execute(
        select(PolicyChunk)
        .options(joinedload(PolicyChunk.site))
        .join(ProcessedSite)
        .filter(ProcessedSite.url.startswith(base_url))
        .order_by(PolicyChunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    return result.scalars().all()



async def update_scan_content_async(db: AsyncSession, url: str, policy_text: str = None, chunks: list = None, internal_links: list = None):
    url_hash = hashlib.md5(url.encode()).hexdigest()
    result = await db.execute(select(ProcessedSite).filter(ProcessedSite.url_hash == url_hash))
    db_scan = result.scalars().first()
    
    if not db_scan:
        db_scan = ProcessedSite(url_hash=url_hash, url=url, policy_text=policy_text, internal_links=internal_links or [])
        db.add(db_scan)
        await db.flush() # Flush to get db_scan.id assigned automatically!
    else:
        db_scan.policy_text = policy_text
        if internal_links is not None:
            db_scan.internal_links = internal_links
        
    if chunks:
        await db.execute(text("CREATE TEMP TABLE IF NOT EXISTS temp_text_chunks (child_text TEXT, parent_text TEXT) ON COMMIT DROP;"))
        await db.execute(text("TRUNCATE temp_text_chunks;"))
        
        # Insert chunks iteratively for the temp table
        for c, _, p in chunks:
            await db.execute(
                text("INSERT INTO temp_text_chunks (child_text, parent_text) VALUES (:child, :parent)"),
                {"child": c, "parent": p}
            )
            
        await db.execute(text("SET pg_trgm.similarity_threshold = 0.90;"))
        
        gate_result_raw = await db.execute(text("""
            SELECT p.site_id, COUNT(DISTINCT t.child_text) as match_count
            FROM temp_text_chunks t
            INNER JOIN policy_chunks p ON p.parent_text % t.parent_text
            GROUP BY p.site_id
            ORDER BY match_count DESC
        """))
        gate_result = gate_result_raw.fetchall()
        
        total_matched_chunks = sum(row.match_count for row in gate_result) if gate_result else 0
        total_incoming_chunks = len(chunks)
        
        if total_incoming_chunks > 0 and (total_matched_chunks / total_incoming_chunks) >= 0.90:
            similar_site_urls = []
            for row in gate_result[:3]:
                site_res = await db.execute(select(ProcessedSite).filter(ProcessedSite.id == row.site_id))
                site_rec = site_res.scalars().first()
                if site_rec:
                    similar_site_urls.append(site_rec.url)
                    
            error_payload = {
                "status": "rejected",
                "reason": "Thin Wrapper (>90% character similarity)",
                "similar_sites": similar_site_urls
            }
            db_scan.policy_text = json.dumps(error_payload)
            await db.commit()
            print(f"[REJECTED] {url}: Site is a >=90% duplicate (Thin Wrapper). Matches: {similar_site_urls}")
            return {"success": False, "reason": error_payload}

        print(f"[EMBED] Generating {total_incoming_chunks} embeddings for new site...")
        child_texts_only = [c for c, _, _ in chunks]
        embeddings = embedding_model.embed_documents(child_texts_only)
        
        added_count = 0
        for (c, _, p), e in zip(chunks, embeddings):
            chunk_record = PolicyChunk(
                site_id=db_scan.id,
                chunk_text=c,
                parent_text=p,
                embedding=e
            )
            db.add(chunk_record)
            added_count += 1
            
        print(f"[SUCCESS] Added {added_count} new chunks unconditionally.")
            
    await db.commit()
    await db.refresh(db_scan)
    return {"success": True, "scan": db_scan}


async def get_stale_scans_async(db: AsyncSession, days_old: int = 30):
    from datetime import datetime, timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=days_old)
    result = await db.execute(select(ProcessedSite).filter(ProcessedSite.created_at < cutoff_date))
    return result.scalars().all()

async def get_chunks_for_scan_async(db: AsyncSession, site_id: int):
    result = await db.execute(select(PolicyChunk).filter(PolicyChunk.site_id == site_id))
    chunks = result.scalars().all()
    result_list = []
    for c in chunks:
        parts = c.parent_text.split('\n\n', 1)
        heading_string = parts[0] if len(parts) > 1 else "Root Document"
        result_list.append((c.chunk_text, heading_string, c.parent_text))
    return result_list

async def apply_delta_update_async(db: AsyncSession, site_id: int, to_delete: list, to_add: list, to_update_parents: list):
    deleted_count = 0
    if to_delete:
        res = await db.execute(delete(PolicyChunk).filter(
            PolicyChunk.site_id == site_id,
            PolicyChunk.chunk_text.in_(to_delete)
        ))
        deleted_count = res.rowcount
        
    added_count = 0
    if to_add:
        child_texts_only = [c[0] for c in to_add]
        print(f"[EMBED] [Delta] Generating {len(child_texts_only)} embeddings for updated chunks...")
        embeddings = embedding_model.embed_documents(child_texts_only)
        
        for (child_text, parent_text), emb in zip(to_add, embeddings):
            chunk_record = PolicyChunk(
                site_id=site_id,
                chunk_text=child_text,
                parent_text=parent_text,
                embedding=emb
            )
            db.add(chunk_record)
            added_count += 1
                
    updated_parents_count = 0
    if to_update_parents:
        for old_text, new_text in to_update_parents:
            res = await db.execute(
                text("UPDATE policy_chunks SET parent_text = :new_text WHERE site_id = :site_id AND parent_text = :old_text"),
                {"new_text": new_text, "site_id": site_id, "old_text": old_text}
            )
            updated_parents_count += res.rowcount
            
        print(f"[UPDATE] Sibling Update: Updated {updated_parents_count} chunks to their new parent_text without re-embedding!")
    
    await db.commit()
    return deleted_count, added_count

async def update_scan_timestamp_async(db: AsyncSession, scan_id: int):
    await db.execute(update(ProcessedSite).where(ProcessedSite.id == scan_id).values(created_at=func.now()))
    await db.commit()