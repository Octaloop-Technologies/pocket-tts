from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from stripe_subscription.config import settings
from stripe_subscription.database import get_db
from stripe_subscription.email import send_reset_email
from stripe_subscription.models import User
from stripe_subscription.security import (
    JWTService,
    PasswordResetService,
    generate_api_key,
    hash_password,
    log_audit,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    name: str = Field(default="", max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    api_key: str
    user_id: int


@router.post("/register", response_model=AuthResponse)
async def register_user(
    req: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    logger.info(f"Registration attempt for email: {req.email}")

    existing = db.query(User).filter_by(email=req.email).first()
    if existing:
        logger.warning(f"Registration failed - email already registered: {req.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    api_key = generate_api_key()
    password_hash = hash_password(req.password, rounds=12)

    user = User(
        email=req.email,
        password_hash=password_hash,
        api_key=api_key,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_audit(db, user.id, "register", {"email": req.email}, request)

    logger.info(f"User registered: {user.id} ({req.email})")
    return AuthResponse(api_key=api_key, user_id=user.id)


@router.post("/login", response_model=AuthResponse)
async def login_user(
    req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    logger.info(f"Login attempt for email: {req.email}")

    user = db.query(User).filter_by(email=req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        logger.warning(f"Login failed - invalid credentials: {req.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    log_audit(db, user.id, "login", None, request)
    logger.info(f"User logged in: {user.id} ({req.email})")

    return AuthResponse(api_key=user.api_key, user_id=user.id)


class ResetRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    csrf_token: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("confirm_password")
    @classmethod
    def validate_confirm(cls, v: str, info: Any) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


# ---------- Key function for rate limiting ----------
def reset_key_func(request: Request, *args: Any, **kwargs: Any) -> str:
    """
    Extract a unique key for rate limiting: IP + email (if available).
    The first positional argument after `request` is the Pydantic body (ResetRequest).
    """
    ip = request.client.host if request.client else "unknown"
    email = "unknown"
    if args and hasattr(args[0], "email"):
        email = args[0].email
    return f"{ip}:{email}"


# ---------- UPDATED ENDPOINT ----------
@router.post("/request-password-reset")
async def request_password_reset(
    req: ResetRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    logger.info(f"Password reset requested for email: {req.email}")

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    user = db.query(User).filter_by(email=req.email).first()

    if user:
        jwt_service = JWTService(settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
        reset_service = PasswordResetService(jwt_service)
        token = reset_service.create_reset_request(db, user, ip, ua)
        db.commit()

        sent = send_reset_email(req.email, token)
        if not sent:
            logger.error(f"Failed to send reset email to {req.email}")
            log_audit(
                db,
                user.id,
                "reset_request_failed",
                {"reason": "send_failed"},
                request,
            )
        else:
            log_audit(db, user.id, "reset_requested", {"email": req.email}, request)

    return {"message": "If that email exists, a reset link has been sent."}


@router.get("/reset-password")
async def validate_reset_token(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    jwt_service = JWTService(settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
    reset_service = PasswordResetService(jwt_service)
    result = reset_service.validate_reset_token(db, token)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user, _ = result
    csrf_token = secrets.token_urlsafe(32)
    response = {
        "email": user.email,
        "csrf_token": csrf_token,
        "token": token,
    }
    resp = JSONResponse(content=response)
    resp.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=False,
        samesite="lax",
        max_age=600,
    )
    return resp


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    csrf_cookie = request.cookies.get("csrf_token")
    if not csrf_cookie or req.csrf_token != csrf_cookie:
        raise HTTPException(status_code=400, detail="CSRF validation failed")

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    jwt_service = JWTService(settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
    reset_service = PasswordResetService(jwt_service)
    success = reset_service.reset_password(db, req.token, req.new_password, ip, ua)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    resp = JSONResponse(
        content={"message": "Password reset successfully. You can now login."}
    )
    resp.delete_cookie("csrf_token")
    return resp
