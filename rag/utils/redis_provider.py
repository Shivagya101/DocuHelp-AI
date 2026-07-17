import os
from redis import Redis
import redis.asyncio as aioredis
from rq import Queue, Retry

# Initialize global connection pools (Best Practice)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_sync_pool = Redis.from_url(REDIS_URL)
_async_pool = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)

def get_redis_connection():
    """
    Returns the globally pooled synchronous Redis connection.
    """
    return _sync_pool

def get_async_redis_connection():
    """
    Returns the globally pooled asynchronous Redis connection.
    """
    return _async_pool

def get_scrape_queue():
    """
    Returns the RQ queue for scrape tasks.
    """
    redis_conn = get_redis_connection()
    return Queue("scrape_tasks", connection=redis_conn)

def enqueue_scrape_task(url: str, base_url: str = None, is_cron_update: bool = False):
    """
    Enqueues a scraping task into Redis.
    """
    if base_url is None:
        base_url = url
    queue = get_scrape_queue()
    queue.enqueue(
        "workers.scraper_worker.fetch_and_publish", 
        url, base_url, is_cron_update,
        retry=Retry(max=3)
    )
