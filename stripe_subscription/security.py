from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from fastapi import Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from stripe_subscription.middlewares.security import ensure_utc_aware

from .models import AuditLog, PasswordResetToken, User

logger = logging.getLogger(__name__)


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


class JWTService:
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm

    def create_reset_token(
        self, user_id: int, expires_minutes: int = 15
    ) -> tuple[str, str]:
        jti = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=expires_minutes)
        payload = {
            "sub": str(user_id),
            "jti": jti,
            "purpose": "password_reset",
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
        }
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token, jti

    def verify_reset_token(self, token: str) -> dict[str, Any]:
        payload = jwt.decode(
            token,
            self.secret_key,
            algorithms=[self.algorithm],
            options={"require": ["exp", "sub", "jti", "purpose"]},
        )
        if payload.get("purpose") != "password_reset":
            raise JWTError("Invalid purpose")
        return payload


class PasswordResetService:
    def __init__(self, jwt_service: JWTService):
        self.jwt_service = jwt_service

    @staticmethod
    def _hash_jti(jti: str) -> str:
        return hashlib.sha256(jti.encode()).hexdigest()

    def create_reset_request(
        self,
        db: Session,
        user: User,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> str:
        token, jti = self.jwt_service.create_reset_token(user.id)
        hashed_jti = self._hash_jti(jti)

        reset_token = PasswordResetToken(
            user_id=user.id,
            hashed_jti=hashed_jti,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            created_ip=ip,
            created_ua=user_agent,
        )
        db.add(reset_token)
        db.flush()
        return token

    def validate_reset_token(
        self, db: Session, token: str
    ) -> tuple[User, PasswordResetToken] | None:
        try:
            payload = self.jwt_service.verify_reset_token(token)
        except JWTError:
            return None

        user_id = int(payload["sub"])
        hashed_jti = self._hash_jti(payload["jti"])

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        token_record = (
            db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.hashed_jti == hashed_jti,
            )
            .first()
        )
        if not token_record:
            return None

        if token_record.used_at is not None:
            return None

        if ensure_utc_aware(token_record.expires_at) < datetime.now(timezone.utc):
            return None

        return user, token_record

    def reset_password(
        self,
        db: Session,
        token: str,
        new_password: str,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        result = self.validate_reset_token(db, token)
        if not result:
            return False

        user, token_record = result

        user.password_hash = hash_password(new_password)
        token_record.used_at = datetime.now(timezone.utc)

        log_audit(
            db,
            user.id,
            "password_reset_success",
            details={"ip": ip, "user_agent": user_agent},
            request=None,
        )
        db.commit()
        return True
