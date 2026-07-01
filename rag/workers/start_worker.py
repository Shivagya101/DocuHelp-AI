import os
from utils.redis_provider import get_redis_connection
from rq.worker import SimpleWorker

def main():
    # Connect to local Redis using our centralized provider
    redis_conn = get_redis_connection()

    print("Starting Windows-compatible RQ Worker (SimpleWorker)...")
    print("Listening on queue: scrape_tasks")
    
    # SimpleWorker does NOT use os.fork(), making it safe for Windows
    worker = SimpleWorker(['scrape_tasks'], connection=redis_conn)
    worker.work()

if __name__ == '__main__':
    main()
