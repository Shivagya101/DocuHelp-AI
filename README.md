# DocuHelp AI — Intelligent Documentation Assistant

> A production-grade, distributed RAG (Retrieval-Augmented Generation) engine that ingests any software documentation website and lets developers ask natural-language questions with citation-backed, streaming answers.

---

## Features

| Feature | Description |
|---|---|
| **Dynamic JavaScript Scraping** | Playwright headless Chromium renders SPAs (React, Next.js, Vue) correctly. `requests.get()` would return an empty shell. |
| **domcontentloaded Trigger** | Avoids the `networkidle` trap on enterprise sites (Stripe, AWS) that maintain permanent WebSocket connections. |
| **Network Interception** | Blocks images, CSS, and fonts at the browser level — cutting page scrape time from 10–15s to 1–3s. |
| **MinHash + LSH Global Deduplication** | Detects "Thin Wrapper" plagiarism (≥90% similar content) in sub-linear O(1) time using Redis-backed Locality Sensitive Hashing. |
| **Semantic Merkle Tree Delta Sync** | Re-embeds only changed chunks on cron updates, reducing embedding API cost by ~99% for small documentation updates. |
| **Parent-Child Chunking** | 400-char child chunks for precise vector retrieval; 2000-char parent sections sent to the LLM for full context. |
| **HNSW Vector Index** | Approximate nearest-neighbor search in sub-linear time — millisecond-scale queries across millions of embeddings. |
| **Query Expansion + Re-Ranking** | LLM rewrites user questions with synonyms. Cohere Cross-Encoder re-ranks 30 vector candidates → top 5. |
| **SSE Streaming** | LLM response streamed token-by-token via Server-Sent Events. Citations sent first, answer follows in real-time. |
| **Redis Distributed Locking** | Doomsday Lock (`nx=True, ex=21600`) prevents concurrent duplicate scraping across all worker processes. |
| **Sliding Window Rate Limiter** | Redis ZSET-based precise per-IP token bucket. Variable cost per request (bulk = cost × URL count). |
| **Cron Worker with Lock Guard** | 30-day automatic re-sync with Redis lock check to prevent race conditions with manual user syncs. |

---

## Architecture

```
User (Browser / Extension)
        │
        ▼ HTTP POST /sync_bulk
┌──────────────────────────────────────────────────────┐
│           FastAPI Gateway (main.py)                  │
│                                                      │
│  /analyze  → Check Redis lock + DB → return status  │
│  /sync_bulk → Set Doomsday Lock → Enqueue to RQ     │
│  /chat     → Full RAG pipeline → Stream SSE         │
│                                                      │
│  Rate Limiter: Sliding Window Log (Redis ZSET)       │
└──────────┬────────────────────────────┬──────────────┘
           │ Enqueue job (URL ~50 bytes) │ Read from DB
           ▼                            ▼
    Redis RQ Queue             PostgreSQL + pgvector
    "scrape_tasks"             ┌────────────────────┐
    Doomsday Locks             │ processed_sites    │
    Visited URL Sets           │   - url_hash (PK)  │
    Rate Limit ZSETs           │   - internal_links │
    MinHash LSH Index          │   - created_at     │
           │                   │ policy_chunks      │
           ▼                   │   - chunk_text     │
   Scraper Worker              │   - parent_text    │
   scraper_worker.py           │   - Vector(1024)   │
   ┌─────────────────┐         └────────────────────┘
   │ Playwright      │         Indexes: HNSW, GIN,
   │ domcontentloaded│         B-tree text_pattern_ops
   │ Block images/CSS│
   │ Auto-scroll     │
   │ 1s JS settle    │
   │ Extract links   │
   └────────┬────────┘
            │ Publish HTML + links (500KB–5MB)
            ▼
     RabbitMQ Queue
     "parse_tasks"
     durable=True + PERSISTENT messages
            │
            ▼
   Parser Worker (parser_worker.py + ai_engine.py)
   ┌────────────────────────────────────────────┐
   │ 1. clean_html() — BS4 + markdownify        │
   │ 2. generate_chunks() — Header → Parent →   │
   │    Child (400 chars, Language.MARKDOWN)     │
   │ 3. MinHash Global Dedup Check (Redis LSH)  │
   │ 4. Batch embed (Cohere) → pgvector insert  │
   │    OR: Merkle diff → surgical delta update │
   │ 5. Release Doomsday Lock (always, finally) │
   └────────────────────────────────────────────┘
            ▲
   Dispatches every 30 days
   Cron Worker (cron_worker.py)
   - Queries DB for created_at < 30 days ago
   - Checks Redis lock before enqueuing
   - Sets is_cron_update=True flag
```

---

## Key Design Decisions & Trade-offs

### Why MinHash for global deduplication?
Standard exact matching fails if a single word is changed. MinHash + LSH answers "is this similar to ANY existing document?" in O(1) time regardless of database size. We use Redis-backed `datasketch` MinHashLSH with 256 permutations (~6.25% error rate) at a 90% similarity threshold.

### Why `domcontentloaded` and not `networkidle`?
Enterprise sites (Stripe, Cloudflare-protected sites) maintain permanent WebSocket and telemetry connections. `networkidle` waits for all connections to close, which never happens — causing a 30-second timeout crash. `domcontentloaded` fires when the HTML and main JS are parsed, which is all we need for content extraction.

### Why PostgreSQL and not Pinecone/Weaviate?
Single database for both relational data and vectors eliminates sync complexity. PostgreSQL's HNSW index (via pgvector) achieves ~95%+ recall at sub-linear query time. We also need standard SQL for joins and filtering — features dedicated vector databases don't offer.

### Why Parent-Child chunking?
Small chunks (400 chars) produce focused, precise vector embeddings. Large parent sections (2000 chars) provide full context to the LLM. Embedding large sections produces diluted vectors; sending small chunks to the LLM produces answers without context. Parent-Child gives us precision in retrieval and context in generation.

---

## Project Structure

Please refer to [FILE_STRUCTURE.md](FILE_STRUCTURE.md) for a detailed breakdown of the codebase and technical documentation files.

---

## Setup & Running

Please refer to [SETUP.md](SETUP.md) for detailed instructions on configuring environment variables, starting the infrastructure, and running the background workers.

---

## Technology Stack

| Layer | Technology | Key Reason |
|---|---|---|
| API Framework | FastAPI + asyncio | Native async, Pydantic validation, SSE streaming |
| Web Scraping | Playwright Chromium | Executes JavaScript — required for SPAs |
| Scrape Queue | Redis + RQ | Fast in-memory dispatch, built-in `Retry(max=3)` |
| Parse Queue | RabbitMQ + aio_pika | Durable disk-backed transport for large HTML payloads |
| Database | PostgreSQL + pgvector | Single DB for relational + vector; ACID guarantees |
| Vector Index | HNSW (pgvector) | Sub-linear ANN search, ~95%+ recall |
| Embeddings | Cohere embed-english-v3.0 | 1024-dim, strong retrieval, cheaper than OpenAI |
| Re-Ranking | Cohere rerank-english-v3.0 | Cross-Encoder — understands negation, synonymy, context |
| LLM Inference | Groq (Llama 3.3-70b) | 500+ tokens/sec — real-time SSE streaming feels instant |
| Deduplication | MinHash + LSH (datasketch) | O(1) global similarity search via Redis |
| Delta Sync | Semantic Merkle Tree (custom) | O(1) root check, surgical leaf-level diff |
| Rate Limiting | Redis ZSET Sliding Window Log | Precise per-IP, per-endpoint, variable token cost |
| ORM | SQLAlchemy (async) | Type-safe, async-compatible, migration-ready |

---

Built at **NIT Jamshedpur** by Shivagya.
