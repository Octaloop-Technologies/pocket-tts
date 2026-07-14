"""
Authentication routes: registration, login, and password reset.
Uses bcrypt for password hashing (SOC2 compliant).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from stripe_subscription.database import get_db
from stripe_subscription.models import User
from stripe_subscription.security import (
    generate_api_key,
    hash_password,
    log_audit,
    verify_password,
    create_reset_token,
    verify_reset_token,
    hash_token,
)
from stripe_subscription.email import send_reset_email

logger = logging.getLogger(__name__)

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    name: str = Field(default="", max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Basic password strength validation."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    api_key: str
    user_id: int


class ResetRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


@router.post("/register", response_model=AuthResponse)
async def register_user(
    req: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Register a new user. Returns API key for authentication."""
    logger.info(f"Registration attempt for email: {req.email}")

    # Check for existing user
    existing = db.query(User).filter_by(email=req.email).first()
    if existing:
        logger.warning(f"Registration failed - email already registered: {req.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
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

    # Audit log
    log_audit(db, user.id, "register", {"email": req.email}, request)  # type: ignore

    logger.info(f"User registered: {user.id} ({req.email})")
    return AuthResponse(api_key=api_key, user_id=user.id)  # type: ignore


@router.post("/login", response_model=AuthResponse)
async def login_user(
    req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login existing user. Returns API key."""
    logger.info(f"Login attempt for email: {req.email}")

    user = db.query(User).filter_by(email=req.email).first()
    if not user or not verify_password(req.password, user.password_hash):  # type: ignore
        logger.warning(f"Login failed - invalid credentials: {req.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    user.last_login = datetime.now(timezone.utc)  # type: ignore
    db.commit()

    log_audit(db, user.id, "login", None, request)  # type: ignore
    logger.info(f"User logged in: {user.id} ({req.email})")

    return AuthResponse(api_key=user.api_key, user_id=user.id)  # type: ignore


@router.post("/request-password-reset")
async def request_password_reset(
    req: ResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Request a password reset email."""
    user = db.query(User).filter_by(email=req.email).first()
    if not user:
        # Do not reveal if email exists; just return success
        return {"message": "If that email exists, a reset link has been sent."}

    token = create_reset_token(user, db)
    sent = send_reset_email(req.email, token)
    if not sent:
        log_audit(db, user.id, "reset_request_failed", {"email": req.email}, request)  # type: ignore
        raise HTTPException(500, "Could not send reset email. Try again later.")
    log_audit(db, user.id, "reset_requested", {"email": req.email}, request)  # type: ignore
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Reset password using a valid one‑time token."""
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # Find user by token hash (inefficient but acceptable for small DB)
    token_hash = hash_token(req.token)
    user = db.query(User).filter_by(reset_token_hash=token_hash).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    if not verify_reset_token(req.token, user):
        # Token may be expired or already used; clear it to prevent reuse attempts
        user.reset_token_hash = None  # type: ignore
        user.reset_token_expiry = None  # type: ignore
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Update password
    user.password_hash = hash_password(req.new_password)  # type: ignore
    # Invalidate token (one‑time use)
    user.reset_token_hash = None  # type: ignore
    user.reset_token_expiry = None  # type: ignore
    user.reset_token_used = True  # type: ignore
    db.commit()

    log_audit(db, user.id, "reset_password_success", None, request)  # type: ignore
    return {"message": "Password reset successfully. You can now login."}
