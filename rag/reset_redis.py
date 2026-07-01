from utils.redis_provider import get_redis_connection

redis_conn = get_redis_connection()
redis_conn.flushdb()
print("Redis database flushed! All rate limits and active locks have been cleared.")
