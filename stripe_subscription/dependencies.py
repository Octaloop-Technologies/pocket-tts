"""
FastAPI dependencies for authentication, subscription, and rate limiting.
"""

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from stripe_subscription.middlewares.security import ensure_utc_aware

from .config import settings
from .database import get_db
from .models import Subscription, User
from .rate_limiter import get_rate_limiter


def get_current_user(
    api_key: str = Header(..., alias=settings.API_KEY_HEADER),
    db: Session = Depends(get_db),
) -> User:
    """Validate API key and return the authenticated user."""
    user = db.query(User).filter_by(api_key=api_key).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return user


def get_active_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Subscription:
    """Get the user's active subscription or raise 403."""
    sub = db.query(Subscription).filter_by(user_id=user.id, status="active").first()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active subscription",
        )

    # Check expiration – ensure end_date is UTC-aware
    end_date = ensure_utc_aware(sub.end_date)  # type: ignore
    if end_date is not None and end_date < datetime.now(timezone.utc):
        sub.status = "expired"  # type: ignore
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription expired",
        )
    return sub


def check_quota(
    sub: Subscription = Depends(get_active_subscription),
    text_length: int = 0,
) -> Subscription:
    """Check if user has remaining quota."""
    if sub.characters_used + text_length > sub.quota_limit:  # type: ignore
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Monthly character limit exceeded",
        )
    return sub


def rate_limit_dependency(
    request: Request,
    api_key: str = Header(..., alias=settings.API_KEY_HEADER),
) -> None:
    """
    Rate limit by API key.
    Returns 429 if rate limit is exceeded.
    """
    limiter = get_rate_limiter()
    if not limiter.is_allowed(
        key=api_key,
        max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {settings.RATE_LIMIT_MAX_REQUESTS} requests per {settings.RATE_LIMIT_WINDOW_SECONDS} seconds.",
        )
