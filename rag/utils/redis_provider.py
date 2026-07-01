import os
from redis import Redis
import redis.asyncio as aioredis
from rq import Queue, Retry

def get_redis_connection():
    """
    Initializes and returns a centralized Redis connection.
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return Redis.from_url(redis_url)

def get_async_redis_connection():
    """
    Initializes and returns an asynchronous Redis connection for FastAPI endpoints.
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return aioredis.Redis.from_url(redis_url, decode_responses=True)

def get_scrape_queue():
    """
    Returns the RQ queue for scrape tasks.
    """
    redis_conn = get_redis_connection()
    return Queue("scrape_tasks", connection=redis_conn)

def enqueue_scrape_task(url: str, base_url: str = None, current_depth: int = 0, max_depth: int = 2, is_cron_update: bool = False):
    """
    Enqueues a scraping task into Redis.
    """
    if base_url is None:
        base_url = url
    queue = get_scrape_queue()
    queue.enqueue(
        "workers.scraper_worker.fetch_and_publish", 
        url, base_url, current_depth, max_depth, is_cron_update,
        retry=Retry(max=3)
    )
