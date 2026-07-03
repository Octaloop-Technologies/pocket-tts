from datetime import datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import Subscription, User


def get_current_user(
    api_key: str = Header(..., alias=settings.API_KEY_HEADER),
    db: Session = Depends(get_db),
) -> User:
    user = db.query(User).filter_by(api_key=api_key).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user


def get_active_subscription(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Subscription:
    sub = db.query(Subscription).filter_by(user_id=user.id, status="active").first()
    if not sub:
        raise HTTPException(status_code=403, detail="No active subscription")
    # `sub.end_date` is Optional[datetime]; it can be None
    if sub.end_date is not None and sub.end_date < datetime.utcnow():
        sub.status = "expired"
        db.commit()
        raise HTTPException(status_code=403, detail="Subscription expired")
    return sub


def check_quota(
    sub: Subscription = Depends(get_active_subscription), text_length: int = 0
) -> Subscription:
    """Dependency to check quota; can be used directly or in endpoint."""
    if sub.characters_used + text_length > sub.quota_limit:
        raise HTTPException(status_code=429, detail="Monthly character limit exceeded")
    return sub
