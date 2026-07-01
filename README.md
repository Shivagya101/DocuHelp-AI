# 🛡️ DocuHelp (Documentation Engine)

### An Intelligent Software Documentation & API Reference Assistant

DocuHelp is an intelligent middleware designed to ingest, monitor, deduplicate, and semantically query massive volumes of **software documentation**, **API references**, and **developer guides**. It tracks documentation changes over time using structural diffing and allows developers to chat with their ecosystem documentation via an advanced RAG (Retrieval-Augmented Generation) pipeline.

---

## 🚀 Features

| Feature | Description |
|---------|-------------|
| **Smart Ingestion Pipeline** | Uses Playwright (Headless Browser) running in background RQ workers to dynamically crawl modern documentation sites (React, Vue, SPAs). |
| **Two-Stage Deduplication** | Employs exact text-matching (`pg_trgm`) and semantic vector thresholding (`pgvector` distance < 0.10) to aggressively block duplicate context from polluting the vector space. |
| **Merkle Tree Structural Diffing** | Compares the hierarchical heading structure (H1-H6) of incoming document updates against the existing database, calculating precise patch sets to insert, update, or delete chunks. |
| **Hybrid Search (In Progress)** | Combines exact keyword matching (BM25) with semantic vector search, dynamically re-ranking results using Reciprocal Rank Fusion (RRF). |
| **RAG Chatbot** | Ask questions about any ingested documentation in natural language powered by Groq and Cohere embeddings. |

---

## 🏗️ Architecture

```
User (Dashboard / API)
        ↓
  Python RAG Engine (FastAPI)
        │
        ├─▶ Cronjob Dispatcher (Detects stale documentation)
        │       ↓ (Redis Queue)
        ├─▶ Scraper Worker (Playwright / BeautifulSoup)
        │       ↓ (RabbitMQ Queue)
        └─▶ Parser Worker (Merkle Tree Diffing / Chunking)
                ↓
  ┌──────────────────────────────────────────────┐
  │  PostgreSQL (pgvector, pg_trgm)              │
  │  Two-Stage Deduplication Gate                │
  │  Cohere Embeddings                           │
  │  Groq (LLM Inference)                        │
  └──────────────────────────────────────────────┘
```

---

## 📂 Project Structure

```
DocuHelp/
├── frontend/               # React Dashboard (TBD)
├── backend/                # Node.js API Gateway (Legacy)
├── extension/              # Chrome Extension (Legacy)
│
├── rag/                    # Python RAG & Ingestion Engine
│   ├── main.py             # FastAPI backend interface
│   ├── database.py         # SQLAlchemy Setup (PostgreSQL)
│   ├── ai_engine.py        # Embeddings (Cohere), Chunking (LangChain), LLM (Groq)
│   ├── merkle_sync.py      # Merkle Tree structural diffing logic
│   ├── run_workers.ps1     # Unified launcher for background workers
│   │
│   ├── repository/         # Database persistence layers
│   │   └── scan_repository.py  # `pg_trgm` and `pgvector` Two-Stage logic
│   │
│   └── workers/            # Background Processors
│       ├── cron_worker.py      # Dispatches stale documentation updates
│       ├── start_worker.py     # RQ Worker (Playwright Scraper)
│       └── parser_worker.py    # RabbitMQ Consumer (Merkle Diff Engine)
│
└── README.md
```

---

## 🛠️ Setup & Execution

### 1. Database & Brokers (Docker)
Ensure you have the core infrastructure running via Docker:
- **PostgreSQL** (with `pgvector` and `pg_trgm` enabled) on port `5432`
- **Redis** on port `6379` (For RQ Task Queue)
- **RabbitMQ** on port `5672` (For Parser Queue)

### 2. Environment Variables
Create a `.env` file in the `rag/` directory:
```
DATABASE_URL=postgresql://user:password@localhost:5432/docuhelp
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
COHERE_API_KEY=your_key
GROQ_API_KEY=your_key
```

### 3. Running the RAG Engine & Workers
Activate your virtual environment, then start the background pipeline:

```bash
cd rag
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install

# Terminal 1: Start the Scraper Worker (RQ)
python -m workers.start_worker

# Terminal 2: Start the Parser Worker (RabbitMQ)
python -u -m workers.parser_worker

# Terminal 3: Fire the Cron Dispatcher (or run it on a schedule)
python -m workers.cron_worker
```

---

## 🧠 Deep Dive: Ingestion Engine

1. **Detection** — The `cron_worker` scans the PostgreSQL `processed_sites` table for URLs that haven't been updated in X days. It pushes a task to Redis.
2. **Dynamic Scraping** — The `start_worker` uses Playwright to fully render JavaScript-heavy documentation pages, extracts the HTML, and pushes a payload to RabbitMQ.
3. **Chunking** — The `parser_worker` consumes the HTML. It cleans the text and uses a `MarkdownHeaderTextSplitter` combined with a `RecursiveCharacterTextSplitter` to create structural, overlapping chunks.
4. **Merkle Diffing** — A hierarchical Merkle Tree is built from the new chunks and compared against the existing tree in the database, yielding precise `to_add` and `to_delete` batches.
5. **Two-Stage Deduplication** — Before new chunks are blindly inserted, they pass through a strict Postgres gate:
    - **Stage 1 (Text):** `pg_trgm` drops any chunk that shares 90% literal text similarity with an existing chunk.
    - **Stage 2 (Vector):** Cohere embeds the surviving chunks. `pgvector` drops any chunk with a cosine distance `< 0.10` compared to existing chunks.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Core RAG Engine** | Python, FastAPI |
| **Background Tasks** | Redis Queue (RQ), RabbitMQ |
| **Dynamic Scraper** | Playwright, BeautifulSoup |
| **Vector DB** | PostgreSQL (`pgvector`, `pg_trgm`) |
| **Embeddings** | Cohere |
| **AI / LLM** | Groq |
| **Text Processing** | LangChain |

---

## 👥 Team

Built by the DocuHelp Team — **NIT Jamshedpur**
- **Shivagya**  

## 📄 License

This project is developed for academic purposes at NIT Jamshedpur.
