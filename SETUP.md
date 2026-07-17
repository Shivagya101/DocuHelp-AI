# Setup & Running

This document explains how to configure, install, and run the DocuHelp AI platform locally. It covers environment variables, database containers, and the necessary worker processes.

## Prerequisites
- **Docker** (used for running the infrastructure layer)
- **Python 3.11+**
- **API Keys**: Cohere, Groq

## 1. Start Infrastructure (Databases & Brokers)
Run the following command in the root directory to start the backing services via Docker Compose:
```bash
docker compose up -d
```
This single command spins up three distinct background services:
* **PostgreSQL (with pgvector)**: Running on port `5432`
* **Redis (Caching & Locks)**: Running on port `6379`
* **RabbitMQ (Message Queue)**: Running on port `5672`

## 2. Configure Environment Variables
Create a file named `.env` inside the `rag/` directory with the following contents:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/docuhelp
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
COHERE_API_KEY=your_cohere_key
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile
```

## 3. Install Dependencies
Set up your Python virtual environment and install all dependencies:
```bash
cd rag
python -m venv venv

# Activate on Windows:
venv\Scripts\activate
# Activate on Linux/macOS:
# source venv/bin/activate

pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

## 4. Start Servers and Workers (Requires 3 Terminals)
You must run the API server and the two background workers simultaneously. Open 3 separate terminal windows, ensure you are in the `rag/` directory, and activate the virtual environment in all three.

**Terminal 1: FastAPI Gateway**
Runs the main web API.
* **Port**: `8000` (http://localhost:8000)
```bash
python -m uvicorn main:app --port 8000 --reload
```

**Terminal 2: Scraper Worker (RQ)**
Runs the synchronous Playwright web scraper. It listens to the Redis queue for incoming URLs.
* **Connects to**: Redis on port `6379`
```bash
python -m workers.start_worker
```

**Terminal 3: Parser Worker (RabbitMQ consumer)**
Runs the asynchronous HTML parsing and vector embedding pipeline. It listens to RabbitMQ for raw HTML chunks.
* **Connects to**: RabbitMQ on port `5672`
```bash
python -u -m workers.parser_worker
```

## 5. Submit a Documentation URL (Usage Examples)
Once everything is running, you can interact with the API on port `8000`:
