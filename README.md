# DocuHelp AI

> A distributed RAG engine for querying software documentation.

---

## Core Features (Interview Highlights)

| Feature | Description |
|---|---|
| **Parent-Child Chunking with Headers** | Embeds small child chunks (400 chars) for precise vector retrieval, while retaining the parent section's context and markdown headers. We send the large parent block (2000 chars) to the LLM to prevent context loss. |
| **Redis Doomsday Lock (Ticketing)** | Drops a temporary "ticket" (`nx=True`, 6-hour TTL) into Redis when a user requests a URL scrape. This prevents race conditions and duplicate processing across all workers. |
| **RabbitMQ Asynchronous Processing** | Heavy HTML payloads (up to 5MB) are passed to RabbitMQ for durable, persistent message queuing, ensuring no data loss during the parsing and chunking phases. |
| **Embeddings & Cross-Encoder Re-Ranking** | Uses Cohere to generate 1024-dim embeddings stored in PostgreSQL (`pgvector` HNSW index). We retrieve 30 candidates, then use a Cross-Encoder to re-rank and return the absolute top 5 chunks. |
| **Sliding Window Rate Limiter** | A precise, per-IP token bucket implemented using Redis ZSETs to prevent API abuse and handle variable request costs. |

---

## Advanced Features

| Feature | Description |
|---|---|
| **MinHash Global Deduplication** | Fast O(1) detection of plagiarized or deeply similar content using Redis-backed Locality Sensitive Hashing. |
| **Semantic Merkle Tree Delta Sync** | Re-embeds only modified chunks during cron updates, saving significant embedding API costs. |

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

### Why Parent-Child chunking?
Small chunks (400 chars) produce focused, precise vector embeddings. Large parent sections (2000 chars) provide full context to the LLM. Furthermore, we explicitly inject the markdown headers into the child chunks so the vector search understands the topic. Embedding large sections produces diluted vectors; sending small chunks to the LLM produces answers without context. Parent-Child gives us precision in retrieval and context in generation.

### Why Redis and RabbitMQ together?
Redis is exceptionally fast for lightweight coordination. We use it for the "Doomsday Lock" (preventing race conditions) and the Sliding Window Rate Limiter. However, Redis can struggle with massive payloads. When the scraper extracts 5MB of HTML, we drop that into RabbitMQ (`durable=True`). RabbitMQ is designed for large, persistent payloads and guarantees the parser won't lose the data if a worker crashes.

### Why PostgreSQL (pgvector) over Pinecone?
Using a single database for both relational data (URLs, timestamps) and vectors eliminates sync complexity. PostgreSQL's HNSW index achieves ~95%+ recall at sub-linear query time while allowing us to write standard SQL joins.

### Why Re-Ranking?
Standard cosine similarity searches often retrieve superficially similar chunks. By retrieving 30 initial candidates and passing them through a Cohere Cross-Encoder, the model actively scores the semantic relationship between the query and the chunk, pushing the most accurately contextual answers to the top 5.

---

## Experimental Optimizations (Bottom)

### MinHash Global Deduplication
Standard exact matching fails if a single word is changed. MinHash + LSH answers "is this similar to ANY existing document?" in O(1) time regardless of database size. We use Redis-backed `datasketch` MinHashLSH with 256 permutations.

### Semantic Merkle Tree
Instead of flushing the database on a cron update, we generate 256-bit hash signatures for every chunk. We compare the new Merkle Tree against the old one and only send the "dirty" chunks to the embedding API, saving substantial compute cost.

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
