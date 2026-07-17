import asyncio
import os
import sys

from database import async_engine, Base
from utils.redis_provider import get_async_redis_connection, get_redis_connection
from utils.minhash_provider import get_lsh

async def reset_dbs():
    print("Flushing Redis...")
    try:
        # Async redis
        async_conn = get_async_redis_connection()
        await async_conn.flushall()
        # Sync redis
        sync_conn = get_redis_connection()
        sync_conn.flushall()
        print("Redis Flushed.")
    except Exception as e:
        print(f"Error flushing redis: {e}")

    print("Dropping PostgreSQL tables...")
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        print("PostgreSQL tables dropped.")
    except Exception as e:
        print(f"Error dropping PG tables: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(reset_dbs())
