"""
Security utilities: password hashing, API key generation, audit logging.
Uses bcrypt for password hashing (SOC2 compliant).
"""

import hashlib
import logging
import os
import secrets
from typing import Optional

import bcrypt
from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditLog

logger = logging.getLogger(__name__)


def hash_password(password: str, rounds: int = 12) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password
        rounds: bcrypt work factor (default: 12)

    Returns:
        bcrypt hash as string
    """
    try:
        salt = bcrypt.gensalt(rounds=rounds)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    except (ImportError, AttributeError) as e:
        logger.warning(f"bcrypt not available, falling back to SHA256: {e}")
        return _sha256_hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against a hash.
    Supports bcrypt and SHA256 fallback for backward compatibility.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Fallback for old SHA256 hashes
        return hash_password(password) == hashed


def _sha256_hash(password: str) -> str:
    """Legacy SHA256 hashing (fallback only)."""
    salt = os.getenv("PASSWORD_SALT", "pocket-tts-salt-2026").encode()
    hash_obj = hashlib.sha256()
    hash_obj.update(salt)
    hash_obj.update(password.encode())
    return hash_obj.hexdigest()


def generate_api_key() -> str:
    """Generate a secure API key using secrets.token_urlsafe."""
    return f"sk_{secrets.token_urlsafe(32)}"


def log_audit(
    db: Session,
    user_id: Optional[int],
    action: str,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """
    Log an audit trail entry for SOC2 compliance.

    Records: user_id, action, timestamp, IP, user-agent, details.
    """
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


def safe_get(obj, key, default=None):
    """Safely get a value from a Stripe object."""
    try:
        if hasattr(obj, "__getitem__"):
            return obj.get(key, default)
        return getattr(obj, key, default)
    except (KeyError, AttributeError, TypeError):
        return default
