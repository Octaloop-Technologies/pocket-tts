"""
Rate limiter for API protection (SOC2 Availability).
Supports in-memory (single instance) and Redis (distributed) backends.
"""

import time
from collections import defaultdict
from typing import Optional, Protocol


class RateLimitBackend(Protocol):
    """Protocol for rate limit backends."""

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Return True if request is allowed, False if rate limited."""
        ...


class InMemoryRateLimiter:
    """In-memory rate limiter using sliding window with token bucket."""

    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if request is allowed within the rate limit."""
        now = time.time()
        timestamps = self._requests[key]

        # Remove timestamps outside the window
        timestamps = [t for t in timestamps if now - t < window_seconds]

        if len(timestamps) >= max_requests:
            return False

        timestamps.append(now)
        self._requests[key] = timestamps
        return True


class RedisRateLimiter:
    """Redis-backed rate limiter for distributed deployments."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self._prefix = "rate_limit:"

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check rate limit using Redis sorted sets."""
        now = time.time()
        redis_key = f"{self._prefix}{key}"
        window_start = now - window_seconds

        # Remove old entries
        self.redis.zremrangebyscore(redis_key, 0, window_start)

        # Count current requests
        count = self.redis.zcard(redis_key)

        if count >= max_requests:
            return False

        # Add current request
        self.redis.zadd(redis_key, {str(now): now})
        self.redis.expire(redis_key, window_seconds + 10)
        return True


# Singleton instance (in-memory by default, can be replaced with Redis)
_rate_limiter: Optional[RateLimitBackend]


def get_rate_limiter() -> RateLimitBackend:
    """Get the rate limiter instance (singleton)."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = InMemoryRateLimiter()
    return _rate_limiter


def set_rate_limiter(limiter: RateLimitBackend) -> None:
    """Replace the rate limiter with a custom implementation (e.g., Redis)."""
    global _rate_limiter
    _rate_limiter = limiter
