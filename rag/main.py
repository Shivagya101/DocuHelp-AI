from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse
import json
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import database
from database import get_async_db
from repository import scan_repository
from utils.redis_provider import enqueue_scrape_task
import ai_engine
from utils.rate_limiter import RateLimiter

from fastapi import FastAPI, HTTPException, Depends
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
    internal_links: list[str] = []

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
async def analyze_policy(request: AnalyzeRequest, db: AsyncSession = Depends(get_async_db), _=Depends(RateLimiter("analyze", max_requests=100, window_seconds=86400))):
    """
    1. Checks if we already have a scan for this URL in Database.
    2. If YES: the user can chat, and we return the discovered internal_links for manual sync.
    3. If NO: Drops a ticket into Redis and tells the user to refresh later.
    """
    # Normalize URL by removing trailing slashes
    target_url = request.url.rstrip("/")

    # 1. Check if it's already in Postgres
    existing_scan = await scan_repository.get_scan_by_url_async(db, target_url)
    if existing_scan and existing_scan.policy_text:
        return AnalyzeResponse(
            status="cached",
            message="Already processed!",
            internal_links=existing_scan.internal_links or []
        )
        
    # 2. Use Redis Atomic Lock to prevent duplicate scraping
    from utils.redis_provider import get_async_redis_connection
    redis_conn = get_async_redis_connection()
    active_key = f"active:{target_url}"
    
    # Try to set an active lock. Returns True if successful, False if already exists.
    is_fresh_request = await redis_conn.set(active_key, "1", nx=True, ex=1800)
    
    if not is_fresh_request:
        return AnalyzeResponse(
            status="processing",
            message="Already in queue! Please wait."
        )

    # 2. PROCESS NEW SCAN (Async via Redis)
    print(f"Enqueueing scrape task for {target_url}")
    # We no longer pass max_depth > 0, as we only scrape the single requested page.
    enqueue_scrape_task(target_url, base_url=target_url, current_depth=0, max_depth=0)
    
    await redis_conn.close()

    return AnalyzeResponse(
        status="processing",
        message="Your link has been queued for scraping. Please check back soon."
    )

from pydantic import BaseModel, Field

class SyncBulkRequest(BaseModel):
    urls: list[str] = Field(..., max_length=5, description="Maximum of 5 URLs per bulk sync request")

@app.post("/sync_bulk")
async def sync_bulk_urls(request: SyncBulkRequest, db: AsyncSession = Depends(get_async_db), _=Depends(RateLimiter("analyze", max_requests=100, window_seconds=86400))):
    """
    Endpoint for Manual User-Driven Sync. 
    Accepts a list of URLs and drops them into the queue.
    Uses the same 'analyze' rate limit to prevent abuse.
    """
    from utils.redis_provider import get_async_redis_connection
    redis_conn = get_async_redis_connection()
    
    queued_count = 0
    for url in request.urls:
        target_url = url.rstrip("/")
        active_key = f"active:{target_url}"
        
        # Check cache
        existing_scan = await scan_repository.get_scan_by_url_async(db, target_url)
        if existing_scan and existing_scan.policy_text:
            continue
            
        # Check active lock
        if await redis_conn.set(active_key, "1", nx=True, ex=1800):
            enqueue_scrape_task(target_url, base_url=target_url, current_depth=0, max_depth=0)
            queued_count += 1
            
    await redis_conn.close()
    return {"status": "success", "message": f"Successfully queued {queued_count} new pages for sync."}

@app.post("/chat")
async def chat_policy(request: ChatRequest, db: AsyncSession = Depends(get_async_db), _=Depends(RateLimiter("chat", max_requests=100, window_seconds=86400))):
    """
    User asks a question about a specific URL.
    We load the context from Database and answer directly using Groq's context window.
    Server-Sent Events (SSE) to stream the response.
    """
    # Normalize URL by removing trailing slashes
    target_url = request.url.rstrip("/")

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
    relevant_chunks = await scan_repository.get_relevant_chunks_async(db, request.url, query_embedding, limit=30)
        
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
