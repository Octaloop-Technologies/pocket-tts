from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

import bcrypt
import starlette.requests
from fastapi import Request
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from stripe_subscription.models import AuditLog, User

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: starlette.requests.Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


def ensure_utc_aware(dt: Optional[datetime]) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hash_password(password: str, rounds: int = 12) -> str:
    try:
        salt = bcrypt.gensalt(rounds=rounds)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    except (ImportError, AttributeError) as e:
        logger.warning(f"bcrypt not available, falling back to SHA256: {e}")
        return _sha256_hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return hash_password(password) == hashed


def _sha256_hash(password: str) -> str:
    salt = os.getenv("PASSWORD_SALT", "pocket-tts-salt-2026").encode()
    hash_obj = hashlib.sha256()
    hash_obj.update(salt)
    hash_obj.update(password.encode())
    return hash_obj.hexdigest()


def generate_api_key() -> str:
    return f"sk_{secrets.token_urlsafe(32)}"


def log_audit(
    db: Session,
    user_id: Optional[int],
    action: str,
    details: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    ip = None
    ua = None
    if request:
        if hasattr(request, "client") and request.client:
            ip = request.client.host
        ua = request.headers.get("user-agent")

    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        details=str(details) if details else None,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(log_entry)
    db.commit()
    logger.info(f"AUDIT: user={user_id}, action={action}, ip={ip}")


def safe_get(obj: Any, key: str, default: Any = None) -> Any:
    try:
        if hasattr(obj, "__getitem__"):
            return obj.get(key, default)
        return getattr(obj, key, default)
    except (KeyError, AttributeError, TypeError):
        return default


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_reset_token(user: User, db: Session) -> str:
    token = generate_reset_token()
    token_hash = hash_token(token)
    user.reset_token_hash = token_hash
    user.reset_token_expiry = datetime.now(timezone.utc) + timedelta(minutes=30)
    user.reset_token_used = False
    db.commit()
    return token


def verify_reset_token(token: str, user: User) -> bool:
    if not user.reset_token_hash:
        return False
    if user.reset_token_used:
        return False
    expiry = ensure_utc_aware(user.reset_token_expiry)
    if expiry is None or expiry < datetime.now(timezone.utc):
        return False
    return secrets.compare_digest(hash_token(token), user.reset_token_hash)
