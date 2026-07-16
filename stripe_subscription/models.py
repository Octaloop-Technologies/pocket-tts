from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    api_key: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # DEPRECATED: kept for compatibility
    reset_token_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reset_token_expiry: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reset_token_used: Mapped[bool] = mapped_column(Boolean, default=False)

    subscriptions: Mapped[list[Subscription]] = relationship(
        "Subscription", back_populates="user"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship("AuditLog", back_populates="user")
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        "PasswordResetToken", back_populates="user"
    )

    def __init__(
        self,
        email: str,
        password_hash: str,
        api_key: str,
        stripe_customer_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        last_login: Optional[datetime] = None,
        reset_token_hash: Optional[str] = None,
        reset_token_expiry: Optional[datetime] = None,
        reset_token_used: bool = False,
        **kwargs: Any,
    ) -> None:
        self.email = email
        self.password_hash = password_hash
        self.api_key = api_key
        self.stripe_customer_id = stripe_customer_id
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self.last_login = last_login
        self.reset_token_hash = reset_token_hash
        self.reset_token_expiry = reset_token_expiry
        self.reset_token_used = reset_token_used
        for k, v in kwargs.items():
            setattr(self, k, v)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False)
    monthly_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    yearly_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quota_limit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stripe_price_monthly: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_price_yearly: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    subscriptions: Mapped[list[Subscription]] = relationship(
        "Subscription", back_populates="plan"
    )

    def __init__(
        self,
        name: str,
        tier: str,
        quota_limit: int,
        monthly_price: Optional[int] = None,
        yearly_price: Optional[int] = None,
        stripe_price_monthly: Optional[str] = None,
        stripe_price_yearly: Optional[str] = None,
        is_active: bool = True,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.tier = tier
        self.quota_limit = quota_limit
        self.monthly_price = monthly_price
        self.yearly_price = yearly_price
        self.stripe_price_monthly = stripe_price_monthly
        self.stripe_price_yearly = stripe_price_yearly
        self.is_active = is_active
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        for k, v in kwargs.items():
            setattr(self, k, v)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plans.id"), nullable=False
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="inactive")
    start_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    characters_used: Mapped[int] = mapped_column(BigInteger, default=0)
    quota_limit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    interval: Mapped[str] = mapped_column(String, nullable=False, default="monthly")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    user: Mapped[User] = relationship("User", back_populates="subscriptions")
    plan: Mapped[Plan] = relationship("Plan", back_populates="subscriptions")

    def __init__(
        self,
        user_id: int,
        plan_id: int,
        quota_limit: int,
        interval: str = "monthly",
        stripe_subscription_id: Optional[str] = None,
        status: str = "inactive",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        characters_used: int = 0,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        **kwargs: Any,
    ) -> None:
        self.user_id = user_id
        self.plan_id = plan_id
        self.quota_limit = quota_limit
        self.interval = interval
        self.stripe_subscription_id = stripe_subscription_id
        self.status = status
        self.start_date = start_date
        self.end_date = end_date
        self.characters_used = characters_used
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        for k, v in kwargs.items():
            setattr(self, k, v)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc)
    )

    user: Mapped[Optional[User]] = relationship("User", back_populates="audit_logs")

    def __init__(
        self,
        action: str,
        user_id: Optional[int] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        created_at: Optional[datetime] = None,
        **kwargs: Any,
    ) -> None:
        self.user_id = user_id
        self.action = action
        self.details = details
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.created_at = created_at or datetime.now(timezone.utc)
        for k, v in kwargs.items():
            setattr(self, k, v)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (UniqueConstraint("hashed_jti", name="uq_reset_hashed_jti"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    hashed_jti: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_ua: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship("User", back_populates="password_reset_tokens")

    def __init__(
        self,
        user_id: int,
        hashed_jti: str,
        expires_at: datetime,
        used_at: Optional[datetime] = None,
        created_ip: Optional[str] = None,
        created_ua: Optional[str] = None,
        created_at: Optional[datetime] = None,
        **kwargs: Any,
    ) -> None:
        self.user_id = user_id
        self.hashed_jti = hashed_jti
        self.expires_at = expires_at
        self.used_at = used_at
        self.created_ip = created_ip
        self.created_ua = created_ua
        self.created_at = created_at or datetime.now(timezone.utc)
        for k, v in kwargs.items():
            setattr(self, k, v)
