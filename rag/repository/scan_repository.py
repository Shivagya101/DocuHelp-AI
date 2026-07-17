import hashlib
import json
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.sql import text, func
from sqlalchemy.dialects.postgresql import insert
from database import ProcessedSite, PolicyChunk
from ai_engine import embedding_model
from utils.url_utils import clean_url
from utils.minhash_provider import generate_minhash, get_lsh


async def get_scan_by_url_async(db: AsyncSession, url: str):
    """
    Used in main.py (/analyze endpoint). 
    Quickly checks if a URL already exists in the database so the API can 
    return immediately instead of queuing a redundant scrape task.
    """
    url = clean_url(url)
    url_hash = hashlib.md5(url.encode()).hexdigest()
    result = await db.execute(select(ProcessedSite).filter(ProcessedSite.url_hash == url_hash))
    return result.scalars().first()

async def get_relevant_chunks_async(db: AsyncSession, base_url: str, query_embedding: list, limit: int = 30):
    """
    Used in ai_engine.py (generate_response_stream). 
    Performs a pgvector cosine distance search to find the top 30 most relevant 
    text chunks that match the user's chat question.
    """
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
    """
    Used in parser_worker.py (for brand new URLs).
    Creates the main ProcessedSite record, runs a 90% Plagiarism check against 
    the entire database, and if clean, calls Cohere to generate vector embeddings 
    for all chunks and saves them.
    """
    url = clean_url(url)
    url_hash = hashlib.md5(url.encode()).hexdigest()
    result = await db.execute(select(ProcessedSite).filter(ProcessedSite.url_hash == url_hash))
    db_scan = result.scalars().first()
    
    if not db_scan:
        db_scan = ProcessedSite(url_hash=url_hash, url=url, policy_text=policy_text, internal_links=internal_links or [])
        db.add(db_scan)
        await db.flush() # Flush to get db_scan.id assigned automatically!
    else:
        print(f"[Parser] URL {url} already exists. Skipping duplicate RabbitMQ delivery.")
        return {"success": True, "scan": db_scan, "message": "Already processed"}
        
    if chunks:
        # MinHash Deduplication: Global Check before processing!
        print(f"[Parser] Running MinHash LSH deduplication check for {url}...")
        lsh = get_lsh()
        
        # Combine all chunk texts to create a single document-level MinHash
        full_text = " ".join([c for c, _, _ in chunks])
        minhash_sig = generate_minhash(full_text)
        
        # Query Redis LSH for any documents that are >=90% similar
        matching_site_ids = lsh.query(minhash_sig)
        
        if matching_site_ids:
            # We found collisions! Fetch their URLs to show the user.
            similar_site_urls = []
            for m_id in matching_site_ids[:3]:
                # m_id is stored as string in Redis
                site_res = await db.execute(select(ProcessedSite).filter(ProcessedSite.id == int(m_id)))
                site_rec = site_res.scalars().first()
                if site_rec:
                    similar_site_urls.append(site_rec.url)
                    
            error_payload = {
                "status": "rejected",
                "reason": "Thin Wrapper (>90% character similarity via MinHash)",
                "similar_sites": similar_site_urls
            }
            db_scan.policy_text = json.dumps(error_payload)
            await db.commit()
            print(f"[REJECTED] {url}: Site is a >=90% duplicate (Thin Wrapper). Matches: {similar_site_urls}")
            return {"success": False, "reason": error_payload}
            
        # No duplicates found! Insert into Redis LSH to protect against future duplicates.
        # Note: In production with millions of rows, we'd use lsh.insertion_session()
        lsh.insert(str(db_scan.id), minhash_sig)
        print(f"[Parser] MinHash check passed. Inserted {url} into LSH index.")

        total_incoming_chunks = len(chunks)
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
    """
    Used in cron_worker.py.
    The midnight cron job calls this to fetch all websites that haven't been 
    synced in over 30 days so they can be pushed to the queue for a refresh.
    """
    from datetime import datetime, timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=days_old)
    result = await db.execute(select(ProcessedSite).filter(ProcessedSite.created_at < cutoff_date))
    return result.scalars().all()

async def get_chunks_for_scan_async(db: AsyncSession, site_id: int):
    """
    Used in parser_worker.py (during Delta Updates).
    Fetches all existing chunks for a site from the database so the parser can 
    run the Merkle Tree comparison against the newly scraped HTML.
    """
    result = await db.execute(select(PolicyChunk).filter(PolicyChunk.site_id == site_id))
    chunks = result.scalars().all()
    result_list = []
    for c in chunks:
        parts = c.parent_text.split('\n\n', 1)
        heading_string = parts[0] if len(parts) > 1 else "Root Document"
        result_list.append((c.chunk_text, heading_string, c.parent_text))
    return result_list

async def apply_delta_update_async(db: AsyncSession, site_id: int, to_delete: list, to_add: list, to_update_parents: list):
    """
    Used in parser_worker.py (during Delta Updates).
    Applies precise surgical edits to the database (deleting removed text, 
    embedding ONLY newly added text, and updating parent headers without re-embedding).
    """
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

async def update_scan_metadata_async(db: AsyncSession, scan_id: int, internal_links: list = None):
    """
    Used in parser_worker.py.
    When a Delta Update finishes successfully, this resets the created_at 
    timestamp so the cron job knows to wait another 30 days before syncing again.
    Also updates the internal_links array if new links were found.
    """
    update_stmt = update(ProcessedSite).where(ProcessedSite.id == scan_id).values(created_at=func.now())
    if internal_links is not None:
        update_stmt = update_stmt.values(internal_links=internal_links)
        
    await db.execute(update_stmt)
    await db.commit()