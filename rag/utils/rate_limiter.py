import time
from fastapi import Request, HTTPException
from utils.redis_provider import get_async_redis_connection

def extract_client_ip(request: Request) -> str:
    """Helper to extract the true client IP, respecting proxy headers."""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.client.host

async def check_rate_limit(client_ip: str, endpoint_name: str, cost: int, max_tokens: int, window_seconds: int = 86400):
    """
    Token Bucket / Sliding Window Log rate limiter.
    Deducts `cost` amount of tokens from the bucket.
    """
    redis_conn = get_async_redis_connection()
    key = f"ratelimit:{endpoint_name}:{client_ip}"
    
    now = time.time()
    window_start = now - window_seconds
    
    # 1. Clean up old tokens and get current count
    async with redis_conn.pipeline(transaction=True) as pipeline:
        pipeline.zremrangebyscore(key, 0, window_start)
        pipeline.zcard(key)
        results = await pipeline.execute()
        
    current_count = results[1]
    
    # 2. Enforce the limit based on the cost
    if (current_count + cost) > max_tokens:
        remaining = max(0, max_tokens - current_count)
        raise HTTPException(
            status_code=429, 
            detail=f"Rate limit exceeded. Request costs {cost} tokens. You have {remaining} tokens remaining for the next {window_seconds} seconds."
        )
        
    # 3. If allowed, record `cost` number of timestamps to deduct the tokens
    async with redis_conn.pipeline(transaction=True) as pipeline:
        mapping = {}
        for i in range(cost):
            # Add an index offset to the timestamp string so values are strictly unique in the Redis ZSET
            unique_ts_str = f"{now}_{i}"
            mapping[unique_ts_str] = now
            
        pipeline.zadd(key, mapping)
        pipeline.expire(key, window_seconds)
        await pipeline.execute()
