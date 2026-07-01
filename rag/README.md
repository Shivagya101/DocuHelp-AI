---
title: DocuHelp RAG
emoji: 🛡️
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
app_port: 8000
---

# DocuHelp — RAG Engine

FastAPI-based documentation analysis service powering the DocuHelp platform.

## Endpoints
- `GET /` — Health check
- `POST /analyze` — Submits a documentation URL for processing, or returns cached status and internal links.
- `POST /sync_bulk` — Accepts an array of internal links and queues them for scraping.
- `POST /chat` — SSE streaming endpoint to chat with the ingested documentation.

## Environment Variables
- `GROQ_API_KEY` — Your Groq API key for LLM inference
- `COHERE_API_KEY` — Your Cohere API key for vector embeddings and reranking
- `DATABASE_URL` — PostgreSQL connection string (must have pgvector and pg_trgm extensions)
- `REDIS_URL` — Redis connection string for background task queues
- `RABBITMQ_URL` — RabbitMQ connection string for chunking/parsing queues
