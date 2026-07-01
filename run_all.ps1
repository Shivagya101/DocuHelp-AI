# PrivaShield AI - Unified Run Script
# This script starts all components of the PrivaShield AI application in separate windows.
# Make sure Docker is running (for Redis, RabbitMQ, Postgres) before running this!

Write-Host "[PrivaShield] Starting Services..." -ForegroundColor Cyan

# 1. RAG Engine (Python FastAPI)
Write-Host "[1/5] Launching Python RAG Engine (Port 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd rag; if (Test-Path '.\venv\Scripts\Activate.ps1') { . '.\venv\Scripts\Activate.ps1' }; python main.py" -WindowStyle Normal

# 2. Scraper Worker (RQ + Playwright)
Write-Host "[2/5] Launching Scraper Worker..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd rag; if (Test-Path '.\venv\Scripts\Activate.ps1') { . '.\venv\Scripts\Activate.ps1' }; python -m workers.start_worker" -WindowStyle Normal

# 3. Parser Worker (RabbitMQ + Merkle Tree)
Write-Host "[3/5] Launching Parser Worker..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd rag; if (Test-Path '.\venv\Scripts\Activate.ps1') { . '.\venv\Scripts\Activate.ps1' }; python -u -m workers.parser_worker" -WindowStyle Normal

# 4. Cron Dispatcher
Write-Host "[4/5] Launching Cron Dispatcher..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd rag; if (Test-Path '.\venv\Scripts\Activate.ps1') { . '.\venv\Scripts\Activate.ps1' }; python -m workers.cron_worker" -WindowStyle Normal

# 5. Frontend Dashboard (React + Vite)
Write-Host "[5/5] Launching React Frontend Dashboard (Port 5173)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev" -WindowStyle Normal

Write-Host "[DONE] All services launched!" -ForegroundColor Green
Write-Host "Ensure you have started Docker Compose for Redis, RabbitMQ, and PostgreSQL!" -ForegroundColor White
Write-Host "Access the dashboard at: http://localhost:5173" -ForegroundColor White
