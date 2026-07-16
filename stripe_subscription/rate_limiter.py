from __future__ import annotations

import time
from collections import defaultdict
from functools import wraps
from typing import Any, Callable, Optional, Protocol

from fastapi import HTTPException, Request


class RateLimitBackend(Protocol):
    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool: ...


class InMemoryRateLimiter:
    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        timestamps = self._requests[key]
        timestamps = [t for t in timestamps if now - t < window_seconds]

        if len(timestamps) >= max_requests:
            return False

        timestamps.append(now)
        self._requests[key] = timestamps
        return True


class RedisRateLimiter:
    def __init__(self, redis_client: Any):
        self.redis = redis_client
        self._prefix = "rate_limit:"

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        redis_key = f"{self._prefix}{key}"
        window_start = now - window_seconds

        self.redis.zremrangebyscore(redis_key, 0, window_start)
        count = self.redis.zcard(redis_key)

        if count >= max_requests:
            return False

        self.redis.zadd(redis_key, {str(now): now})
        self.redis.expire(redis_key, window_seconds + 10)
        return True


_rate_limiter: Optional[RateLimitBackend] = None


def get_rate_limiter() -> RateLimitBackend:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = InMemoryRateLimiter()
    return _rate_limiter


def set_rate_limiter(limiter: RateLimitBackend) -> None:
    global _rate_limiter
    _rate_limiter = limiter


def rate_limit_decorator(
    limit: int = 10,
    window: int = 60,
    key_func: Optional[Callable[..., str]] = None,
) -> Callable:
    """
    Rate-limit a FastAPI endpoint.

    Args:
        limit: Maximum number of requests per window.
        window: Time window in seconds.
        key_func: Optional callable that receives (request, *args, **kwargs)
                  and returns a string key for rate limiting.
                  If not provided, uses the client's IP address.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            limiter = get_rate_limiter()
            if key_func:
                # Pass all arguments so the lambda can access body, db, etc.
                key = key_func(request, *args, **kwargs)
            else:
                key = request.client.host if request.client else "unknown"

            if not limiter.is_allowed(key, limit, window):
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Maximum {limit} requests per {window} seconds.",
                )
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
