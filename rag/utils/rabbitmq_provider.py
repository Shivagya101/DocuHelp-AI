import os
import json
import aio_pika
from dotenv import load_dotenv

load_dotenv()

async def get_rabbitmq_connection():
    """
    Initializes and returns a centralized Async RabbitMQ connection.
    """
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    connection = await aio_pika.connect_robust(rabbitmq_url)
    return connection

async def publish_to_queue(queue_name: str, payload: dict):
    """
    Standardizes publishing to a RabbitMQ queue asynchronously.
    """
    connection = await get_rabbitmq_connection()
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(queue_name, durable=True)
        
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=queue_name
        )

async def consume_from_queue(queue_name: str, callback_func):
    """
    Standardizes consuming from a RabbitMQ queue asynchronously.
    callback_func must be an async function that accepts an aio_pika.abc.AbstractIncomingMessage.
    """
    connection = await get_rabbitmq_connection()
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    
    queue = await channel.declare_queue(queue_name, durable=True)
    
    print(f"[*] Waiting for messages in '{queue_name}'. To exit press CTRL+C")
    
    await queue.consume(callback_func)
    
    return connection
