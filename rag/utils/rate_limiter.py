import time
from fastapi import Request, HTTPException
from utils.redis_provider import get_async_redis_connection

def RateLimiter(endpoint_name: str, max_requests: int, window_seconds: int):
    """
    FastAPI Dependency that implements a Sliding Window Log Rate Limiter using Redis.
    """
    async def dependency(request: Request):
        # 1. Get Client IP.
        # X-Forwarded-For is necessary when sitting behind an API Gateway proxy like Express/Nginx.
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            # Proxies often append multiple IPs in a comma-separated list. The first one is the original client.
            client_ip = x_forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host
            
        redis_conn = get_async_redis_connection()
        key = f"ratelimit:{endpoint_name}:{client_ip}"
        
        now = time.time()
        window_start = now - window_seconds
        
        # 2. Redis Pipeline (Execute all 3 commands atomically and fast)
        async with redis_conn.pipeline(transaction=True) as pipeline:
            # A. Remove all timestamps older than our window
            pipeline.zremrangebyscore(key, 0, window_start)
            
            # B. Count the remaining valid timestamps in the set
            pipeline.zcard(key)
            
            # Execute the pipeline
            results = await pipeline.execute()
            
        current_count = results[1]  # The result of zcard
        
        # 3. Enforce the limit
        if current_count >= max_requests:
            await redis_conn.close()
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit exceeded. Maximum {max_requests} requests allowed per {window_seconds} seconds."
            )
            
        # 4. If allowed, record the new timestamp and reset expiration
        async with redis_conn.pipeline(transaction=True) as pipeline:
            # Redis ZADD signature is mapping={value: score}. Value must be unique (use timestamp string).
            pipeline.zadd(key, {str(now): now})
            # Set a TTL so inactive keys automatically drop off to save memory
            pipeline.expire(key, window_seconds)
            await pipeline.execute()
            
        await redis_conn.close()

    return dependency
