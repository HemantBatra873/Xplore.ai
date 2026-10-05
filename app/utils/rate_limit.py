import hashlib
import time
import uuid

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger

redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)


class RateLimiter:
    """
    Sliding-window rate limiter using a Redis ZSET.
    """

    def __init__(self, times: int, seconds: int):
        self.times = times
        self.seconds = seconds

    async def __call__(self, request: Request):
        # Prefer Authorization token hash or client IP as the rate-limit key
        auth_header = request.headers.get("Authorization")
        if auth_header:
            client_id = hashlib.sha256(auth_header.encode()).hexdigest()[:16]
        else:
            client_id = request.client.host if request.client else "unknown"

        key = f"rate_limit:{client_id}:{request.url.path}"

        current = time.time()
        window_start = current - self.seconds
        member_id = str(uuid.uuid4())

        try:
            async with redis_client.pipeline(transaction=True) as pipe:
                # Drop entries outside the window
                pipe.zremrangebyscore(key, 0, window_start)
                # Count requests in the current window
                pipe.zcard(key)
                # Record this request
                pipe.zadd(key, {member_id: current})
                # TTL on the key to limit memory use
                pipe.expire(key, self.seconds)
                results = await pipe.execute()

            request_count = results[1]

            if request_count >= self.times:
                logger.warning(f"Rate limit exceeded for {key}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                )
        except HTTPException:
            raise
        except Exception as e:
            # If Redis is down, fail open so core traffic is not blocked
            logger.error(f"Rate limit redis error: {e}")
