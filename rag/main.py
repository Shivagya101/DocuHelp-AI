from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
import json
import hashlib
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import database
from database import get_async_db, ProcessedSite
from repository import scan_repository
from utils.redis_provider import enqueue_scrape_task, get_async_redis_connection
import ai_engine
from utils.rate_limiter import check_rate_limit, extract_client_ip
from utils.url_utils import clean_url

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run on startup
    await database.init_db()
    yield
    # Run on shutdown
    pass

app = FastAPI(title="DocuHelper", version="1.0", lifespan=lifespan)

# --- 1. CORS CONFIGURATION ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. DATA MODELS ---
class AnalyzeRequest(BaseModel):
    url: str

class AnalyzeResponse(BaseModel):
    status: str
    message: str
    synced_links: list[str] = []
    unsynced_links: list[str] = []

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    url: str
    question: str
    history: list[ChatMessage] = []

class ChatResponse(BaseModel):
    answer: str
    citations: list[str] = []


# --- 4. ENDPOINTS ---

@app.get("/")
async def home():
    return {"message": "DocuHelper is running."}

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_policy(request: AnalyzeRequest, raw_req: Request, db: AsyncSession = Depends(get_async_db)):
    """
    1. Check Redis Lock. If locked -> return 'processing'
    2. Check Database. If not found -> return 'not_found'
    3. If found -> calculate synced/unsynced links and return 'indexed'
    """
    await check_rate_limit(extract_client_ip(raw_req), "analyze", cost=1, max_tokens=100)
    
    target_url = clean_url(request.url)
    redis_conn = get_async_redis_connection()
    active_key = f"active:{target_url}"
    
    # 1. Check if locked in Redis
    is_locked = await redis_conn.exists(active_key)
    if is_locked:
        return AnalyzeResponse(
            status="processing",
            message="Already in queue! Please wait."
        )

    # 2. Check if it's already in Postgres
    existing_scan = await scan_repository.get_scan_by_url_async(db, target_url)
    if not existing_scan or not existing_scan.policy_text:
        return AnalyzeResponse(
            status="not_found",
            message="URL not found in database."
        )
        
    # 3. Calculate synced vs unsynced links
    all_links = existing_scan.internal_links or []
    synced = []
    unsynced = []
    
    if all_links:
        # Check which internal links exist in the database using url_hash for O(log n) lookup
        hashed_links = [hashlib.md5(link.encode()).hexdigest() for link in all_links]
        result = await db.execute(select(ProcessedSite.url).filter(ProcessedSite.url_hash.in_(hashed_links)))
        synced_db_links = set(result.scalars().all())
        
        for link in all_links:
            if link in synced_db_links:
                synced.append(link)
            else:
                unsynced.append(link)

    return AnalyzeResponse(
        status="indexed",
        message="Already processed!",
        synced_links=synced,
        unsynced_links=unsynced
    )

from pydantic import Field

class SyncBulkRequest(BaseModel):
    urls: list[str] = Field(..., max_length=5, description="Maximum of 5 URLs per bulk sync request")

@app.post("/sync_bulk")
async def sync_bulk_urls(request: SyncBulkRequest, raw_req: Request, db: AsyncSession = Depends(get_async_db)):
    """
    Endpoint for Manual User-Driven Sync. 
    Accepts a list of URLs and drops them into the queue.
    Accurately deducts tokens based on the number of URLs requested.
    """
    url_count = len(request.urls)
    await check_rate_limit(extract_client_ip(raw_req), "analyze", cost=url_count, max_tokens=100)
    
    redis_conn = get_async_redis_connection()
    queued_count = 0
    
    for url in request.urls:
        target_url = clean_url(url)
        active_key = f"active:{target_url}"
        
        # Check cache
        existing_scan = await scan_repository.get_scan_by_url_async(db, target_url)
        if existing_scan and existing_scan.policy_text:
            continue
            
        # Check active lock and enqueue (6 hour Doomsday TTL)
        if await redis_conn.set(active_key, "1", nx=True, ex=21600):
            enqueue_scrape_task(target_url, base_url=target_url)
            queued_count += 1
            
    return {"status": "success", "message": f"Successfully queued {queued_count} new pages for sync."}

@app.post("/chat")
async def chat_policy(request: ChatRequest, raw_req: Request, db: AsyncSession = Depends(get_async_db)):
    """
    User asks a question about a specific URL.
    We load the context from Database and answer directly using Groq's context window.
    Server-Sent Events (SSE) to stream the response.
    """
    await check_rate_limit(extract_client_ip(raw_req), "chat", cost=1, max_tokens=100)
    
    target_url = clean_url(request.url)
    scan = await scan_repository.get_scan_by_url_async(db, target_url)
    
    if not scan or not scan.policy_text:
        raise HTTPException(status_code=404, detail="Policy not found. Please analyze the site first.")

    if scan.policy_text.startswith('{"status": "rejected"'):
        try:
            error_data = json.loads(scan.policy_text)
            similar = ", ".join(error_data.get("similar_sites", []))
            raise HTTPException(status_code=400, detail=f"Site Rejected: {error_data.get('reason')}. Matches found with: {similar}")
        except json.JSONDecodeError:
            pass

    # Convert Pydantic history models to dicts for ai_engine
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in request.history]

    # 1. Expand the user's question with synonyms using the LLM (condensing history if present)
    expanded_query = await ai_engine.expand_query_async(request.question, history=history_dicts)

    # 2. Embed the EXPANDED question to fetch relevant chunks
    query_embedding = ai_engine.embedding_model.embed_query(expanded_query)
    
    # 3. Query pgvector for a massive net of 30 chunks across the entire crawled domain
    relevant_chunks = await scan_repository.get_relevant_chunks_async(db, target_url, query_embedding, limit=30)
        
    if not relevant_chunks:
        raise HTTPException(status_code=500, detail="Error: No indexed chunks found for this policy. Please re-analyze the site.")
        
    # 4. Use Cohere Cross-Encoder to mathematically Re-Rank the 30 chunks down to the top 5
    raw_chunks = [{"text": chunk.parent_text or chunk.chunk_text, "url": chunk.site.url} for chunk in relevant_chunks]
    top_5_chunks = await ai_engine.rerank_chunks(expanded_query, raw_chunks, top_n=5)

    # 5. Combine the top 5 chunks into our RAG context and extract unique citations
    citations = []
    formatted_context_chunks = []
    seen_texts = set()
    
    for c in top_5_chunks:
        text = c["text"]
        if text in seen_texts:
            continue
        seen_texts.add(text)
        
        url = c["url"]
        if url not in citations:
            citations.append(url)
        
        # Determine the 1-indexed citation number
        citation_num = citations.index(url) + 1
        formatted_context_chunks.append(f"Source [{citation_num}] ({url}):\n{text}")

    context = "\n\n---\n\n".join(formatted_context_chunks)

    # 6. Generator for SSE
    async def event_generator():
        # First, send the citations
        yield f"data: {json.dumps({'type': 'citations', 'citations': citations})}\n\n"
        
        # Then, stream the LLM chunks
        async for chunk_text in ai_engine.chat_with_policy_async(request.question, context, history=history_dicts):
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk_text})}\n\n"
            
        # Finally, signify end of stream
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
 
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
