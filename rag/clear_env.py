import asyncio
import os
from database import async_engine, Base
from utils.redis_provider import get_redis_connection
import aio_pika

async def clear_all():
    print("1. Clearing PostgreSQL database...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("PostgreSQL cleared.")

    print("2. Clearing Redis...")
    redis = get_redis_connection()
    redis.flushall()
    print("Redis cleared.")

    print("3. Clearing RabbitMQ queue...")
    try:
        RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            # Purge the queue
            queue = await channel.declare_queue("parse_tasks", durable=True)
            await queue.purge()
        print("RabbitMQ queue 'parse_tasks' cleared.")
    except Exception as e:
        print(f"Could not clear RabbitMQ (might be empty or down): {e}")

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(clear_all())
