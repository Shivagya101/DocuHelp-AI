#!/bin/bash

# PrivaShield AI - Unified Run Script (Cross-Platform)
# This script starts all components of the PrivaShield AI application.

echo -e "\e[36m[PrivaShield] Starting Services...\e[0m"

# Handle graceful shutdown when pressing Ctrl+C
cleanup() {
    echo -e "\n\e[31m[PrivaShield] Stopping all services...\e[0m"
    # Kill all child processes started by this script
    kill 0
    exit 0
}
trap cleanup SIGINT SIGTERM

# 1. RAG Engine (Python FastAPI)
echo -e "\e[33m[1/5] Launching Python RAG Engine (Port 8000)...\e[0m"
(
    cd ../rag || exit
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi
    python main.py
) &

sleep 1

# 2. Scraper Worker (RQ)
echo -e "\e[33m[2/5] Launching Scraper Worker...\e[0m"
(
    cd ../rag || exit
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi
    python -m workers.start_worker
) &

sleep 1

# 3. Parser Worker (RabbitMQ)
echo -e "\e[33m[3/5] Launching Parser Worker...\e[0m"
(
    cd ../rag || exit
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi
    python -u -m workers.parser_worker
) &

sleep 1

# 4. Cron Dispatcher
echo -e "\e[33m[4/5] Launching Cron Dispatcher...\e[0m"
(
    cd ../rag || exit
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi
    python -m workers.cron_worker
) &

sleep 1

# 5. Frontend Dashboard (React + Vite)
echo -e "\e[33m[5/5] Launching React Frontend Dashboard (Port 5173)...\e[0m"
(
    cd ../frontend || exit
    npm run dev
) &

echo -e "\e[32m[DONE] All services launched!\e[0m"
echo -e "\e[37mAccess the dashboard at: http://localhost:5173\e[0m"
echo -e "\e[37mPress Ctrl+C to stop all services.\e[0m"

# Wait for all background processes to keep script running
wait
