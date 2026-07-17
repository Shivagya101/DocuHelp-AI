# DocuHelp AI — Interview Script

> **How to use this document:**
> This is your personal narration guide for technical interviews. It is structured in five progressive layers — from the 2-minute elevator pitch all the way to deep-dive technical battles.
> Start with the **Opening** and **Overview**. Then let the interviewer guide the depth. If they look engaged, move to the deep dives. If they want to move on, wrap up with the **Closing**.
> Always speak in first person ("I designed...", "I chose..."). Own every decision.

---

## Layer 1: The 2-Minute Elevator Pitch
*(Use this when the interviewer says: "Tell me about this project.")*

> "I built DocuHelp AI — a production-grade, distributed RAG engine that can ingest any software documentation website and let developers ask natural-language questions with citation-backed, streaming answers in real time.
>
> The core problem I was solving is one that every developer faces: you open a documentation site, you need one specific answer, and you end up spending 20 minutes searching through 40 pages that are only 10% relevant. I wanted to build something that would let you just ask it a question — like you would ask a senior engineer — and get a precise, contextual answer with the exact source chunk it came from.
>
> At a high level, the system has three phases. First, a user submits a documentation URL. A distributed pipeline scrapes it using a headless browser, cleans the HTML, chunks the text semantically, and stores vector embeddings in PostgreSQL. Second, when a user asks a question, a RAG pipeline retrieves the most relevant chunks using a two-stage retrieval system — vector search plus AI re-ranking — and streams the answer token by token. Third, a cron worker periodically re-checks all indexed URLs, runs a Merkle Tree diff, and only re-embeds the exact paragraphs that changed — which cuts embedding API costs by about 99% on small updates."

---

## Layer 2: The Architecture Overview
*(Use this when the interviewer follows up: "Walk me through the architecture.")*

> "The architecture is a fully distributed, event-driven pipeline. I will walk you through it left to right.
>
> A user submits a URL through the FastAPI gateway. FastAPI immediately checks two things: first, is this URL already being processed? And second, has the rate limit for this IP been exceeded? Both of these checks happen in Redis in under a millisecond.
>
> If the URL passes both checks, FastAPI enqueues a lightweight job — just the URL string, around 50 bytes — into a Redis RQ queue. A separate Scraper Worker picks it up, boots a headless Playwright Chromium browser, and fetches the fully rendered HTML. I deliberately chose Playwright over a simple `requests.get()` because most modern documentation sites are built with React or Next.js, and plain HTTP requests return an empty shell with no content.
>
> Once the HTML is scraped, the Scraper publishes the full HTML payload — which can be up to 5 megabytes — into a RabbitMQ queue. I used RabbitMQ here instead of Redis for this specific handoff because RabbitMQ persists messages to disk. If the Parser Worker crashes mid-processing, the HTML is not lost. Redis is in-memory only.
>
> The Parser Worker picks up the HTML asynchronously, cleans it, chunks it using a semantic Parent-Child strategy, checks for duplicates via MinHash LSH, generates vector embeddings using Cohere, and stores everything in PostgreSQL with pgvector.
>
> On the query side, when a user asks a question, the FastAPI chat endpoint runs a three-step retrieval: first, it rewrites the query using an LLM to add synonyms and handle typos. Then it runs a vector similarity search using the HNSW index in PostgreSQL to fetch 30 candidates. Finally, a Cohere Cross-Encoder re-ranks those 30 down to the top 5 most semantically relevant chunks. The answer is then streamed back token by token via Server-Sent Events."

---

## Layer 3: Key Technical Decisions
*(Use this when the interviewer asks: "Why did you choose X over Y?" or "Walk me through a design decision.")*

### Decision 1 — Why PostgreSQL and not a dedicated Vector DB like Pinecone?

> "Most RAG tutorials recommend Pinecone or Weaviate for vector storage, and I seriously evaluated them. But I chose to keep everything in PostgreSQL for one critical architectural reason: I need both relational queries and vector queries in the same transaction.
>
> For example, when a user submits a URL, I need to first check if it exists in the `processed_sites` table. If it does, I retrieve all its associated chunks from `policy_chunks`. Then I build the Merkle Tree from those chunks, run the diff, and only update the specific chunks that changed — all in one atomic database transaction. If I split this across PostgreSQL and Pinecone, I would have to manage consistency between two different databases. If one write succeeds and the other fails, I end up with partial data.
>
> PostgreSQL with pgvector's HNSW index achieves around 95% recall at sub-linear query time, which is more than sufficient for this use case. The single-database approach also eliminates an entire class of infrastructure bugs."

### Decision 2 — Why sync Playwright with RQ, not async Playwright?

> "My entire API and parsing pipeline is fully asynchronous using FastAPI and asyncio. So the obvious choice for the scraper would seem to be `async_playwright`. But I deliberately chose not to, for two reasons.
>
> First, booting a Chromium browser is not an I/O-bound task — it is CPU-intensive. It renders JavaScript, computes CSS layouts, and builds a DOM tree. If I ran that on my main asyncio event loop, it would cause CPU starvation and freeze incoming API requests for other users during a heavy scrape.
>
> Second, on Windows — which is my development environment — Playwright's async mode uses asyncio subprocesses that crash with the default `SelectorEventLoop`. You can see the workaround right at the top of my scraper file. By running `sync_playwright` inside an isolated RQ worker process, the browser crash stays contained. If it runs out of memory, it only kills that one worker process, not the main API server."

### Decision 3 — Why MinHash + LSH instead of a database unique constraint?

> "A simple unique constraint in the database would catch exact duplicates. But the problem I was solving was a more subtle one: what about documentation sites that are essentially thin wrappers — two competing SaaS companies with privacy policies that are 95% identical because one copied the other? A unique constraint would index both of them, wasting embedding storage and causing confusing, duplicated answers.
>
> MinHash approximates Jaccard similarity. I run 256 hash functions over the 3-gram shingles of the document, which compresses the entire multi-page policy down to an array of 256 integers. Then the LSH layer splits that array into bands and hashes each band into a Redis bucket. If two documents share even one bucket, they become candidates for a duplicate check.
>
> The mathematical property that makes this work is that if two documents are 90% similar, the probability of at least one band collision is over 96%. But if two documents are only 50% similar, the probability of any band collision drops to about 0.02%. So the false positive rate is essentially zero, and the lookup is O(1) regardless of how many documents are in the database."

### Decision 4 — Why a Merkle Tree for incremental updates?

> "Privacy policies change all the time — but usually, a company changes only one section. Maybe they update their data retention clause, or they add a new paragraph about GDPR. Without a Merkle Tree, my cron worker would have to re-scrape, re-chunk, and re-embed the entire document every 30 days — even if 99% of it was unchanged. Embedding is expensive and slow.
>
> My Merkle Tree is a 3-level structure: child chunk hashes at the leaf level, parent section hashes at the branch level computed from the heading string plus the sorted child hashes, and a root hash at the top representing the entire document.
>
> When the cron worker re-scrapes a URL, I build a fresh Merkle Tree and compare just the root hashes in O(1) time. If they match, the document has not changed and I stop immediately — no API calls, no database writes. If the root differs, I walk down to the branch level and identify exactly which sections changed. Then I drill down to the leaf level to find the exact child chunks that were added or deleted, and I only re-embed those specific chunks."

---

## Layer 4: The Hard Parts
*(Use this when the interviewer asks: "What was the most challenging part?" or "Tell me about a bug you had to fix.")*

### Hard Part 1 — The MinHash Signature Drift Bug

> "One of the more subtle bugs I encountered was around MinHash LSH and the Merkle Tree working together. Here is the problem: when the cron worker processes a URL update, the Merkle Tree correctly identifies the changed chunks and surgically updates them in the database. But the MinHash signature in Redis was computed from the *original* document at first-index time and was never refreshed.
>
> So if a document changed significantly over 30 days — say 20% of it was rewritten — the MinHash signature in Redis was now stale. It still represented the old version of the document. This meant that if a very similar, slightly newer version of the document was submitted, the LSH lookup would compare it against an outdated fingerprint and potentially miss the duplicate.
>
> The fix was to rebuild and re-insert the MinHash signature into Redis immediately after applying any Merkle delta update. The new signature is computed from all the current chunks in the database for that site, ensuring the deduplication index always reflects the actual current state of the document."

### Hard Part 2 — The `networkidle` Trap

> "Early in development, I was using Playwright's `networkidle` trigger, which tells the browser to wait until there are no more network requests for 500ms before extracting the HTML. This sounds perfect in theory.
>
> The problem is enterprise documentation sites. Stripe, AWS, Cloudflare-protected sites — they all maintain permanent open WebSocket connections for telemetry, analytics, or live chat widgets. `networkidle` would wait for these connections to close... which they never do. Every single scrape of a Stripe docs page would time out after 30 seconds and crash.
>
> The fix was switching to `domcontentloaded`. This fires the moment the HTML is parsed and the main JavaScript is executed — which is all we need for content extraction. We do not care about background telemetry sockets. I also added an explicit 1-second wait after the page load and a full-page auto-scroll to force any lazy-loaded content sections to render before we extract the HTML."

---

## Layer 5: Tradeoffs and What I Would Do Differently
*(Use this when the interviewer asks: "What would you improve?" or "What are the limitations?")*

> "If I were taking this to production at scale, there are three things I would change.
>
> First, I would replace the sync Playwright RQ worker with an async implementation using ARQ or a unified RabbitMQ consumer. The dual-queue setup — Redis RQ for scraping, RabbitMQ for parsing — works, but it adds operational complexity. A single unified async queue would simplify monitoring and deployment.
>
> Second, I would replace the APScheduler-based cron worker with a Kubernetes CronJob. Currently, the cron worker is a Python script that runs a `while True` loop. If the server restarts on Day 29 of a 30-day cycle, the loop resets and the sync is delayed. A Kubernetes CronJob is entirely managed by the cluster scheduler — it is not coupled to any running process, so it fires reliably even after node restarts.
>
> Third, I would add an evaluation framework like RAGAS to quantitatively measure retrieval quality. Right now, the chunk sizes, re-ranking cutoffs, and similarity thresholds were determined through systematic engineering reasoning and manual testing. In a production system, I would want automated metrics for faithfulness, context precision, and answer relevance so I could tune those numbers with real data."

---

## Closing Sentence
*(Always end with this when you wrap up any layer of the explanation.)*

> "I am happy to go deeper into any specific component — the vector retrieval pipeline, the rate limiter architecture, the Merkle Tree diff algorithm, or any of the infrastructure decisions. Where would you like to dig in?"
