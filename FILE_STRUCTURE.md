# Project Structure

This document outlines the file structure of the DocuHelp AI project and describes the purpose of each file and directory.

```text
DocuHelp/
├── docs/                        # Technical documentation (interview-ready)
│   ├── 00_overview.md           # Full architecture, flow diagrams, technology rationale
│   ├── 01_database.md           # Schema, all 5 indexes, pgvector vs Pinecone
│   ├── 02_api_gateway.md        # FastAPI endpoints, Doomsday Lock, SSE protocol
│   ├── 03_scraper_pipeline.md   # Playwright, domcontentloaded, network interception
│   ├── 04_parser_pipeline.md    # HTML cleaning, Parent-Child chunking, two ingestion paths
│   ├── 05_deduplication.md      # MinHash math, 256 perms, 90% threshold, LSH global deduplication
│   ├── 06_rag_retrieval.md      # Query expansion, Bi-Encoder vs Cross-Encoder, SSE format
│   ├── 07_merkle_sync.md        # Merkle tree build, diff algorithm, Sibling Update, Cron
│   └── 08_rate_limiter.md       # Sliding Window Log, Redis ZSET, IP header, token cost
│
├── rag/                         # Python RAG Engine
│   ├── main.py                  # FastAPI: /analyze, /sync_bulk, /chat
│   ├── database.py              # SQLAlchemy ORM, pgvector, 5-index init
│   ├── ai_engine.py             # clean_html, generate_chunks, embed, rerank, stream
│   ├── merkle_sync.py           # MerkleTree class + diff_trees function
│   ├── requirements.txt
│   │
│   ├── repository/
│   │   └── scan_repository.py   # All DB operations: MinHash gate, delta apply, stale query
│   │
│   ├── utils/
│   │   ├── minhash_provider.py  # generate_minhash (3-gram), get_lsh (Redis-backed)
│   │   ├── redis_provider.py    # Connection pools (sync + async), enqueue_scrape_task
│   │   ├── rabbitmq_provider.py # aio_pika publish/consume, durable queues
│   │   ├── rate_limiter.py      # check_rate_limit (Sliding Window Log), extract_client_ip
│   │   ├── url_utils.py         # clean_url (normalize, strip fragments, strip UTM params)
│   │   └── llm_provider.py      # Groq ChatGroq singleton (Llama 3.3-70b, temp=0.0)
│   │
│   └── workers/
│       ├── scraper_worker.py    # fetch_and_publish (Playwright + RabbitMQ publish)
│       ├── parser_worker.py     # aio_pika consumer (clean → chunk → dedup → embed → save)
│       ├── cron_worker.py       # Stale URL dispatcher with Redis lock guard
│       └── start_worker.py      # SimpleWorker (Windows-compatible, no os.fork())
│
├── frontend/                    # React Dashboard
├── extension/                   # Chrome Extension
├── docker-compose.yml           # PostgreSQL, Redis, RabbitMQ containers
└── run_all.ps1 / run_all.sh     # One-command startup scripts
```
