"""
Authentication routes: registration and login.
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
        """Basic password strength validation."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        # Optional: add more checks (uppercase, number, special)
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
