from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    api_key: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True
    )
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    subscription: Mapped[Optional["Subscription"]] = relationship(
        "Subscription", back_populates="user", uselist=False
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), unique=True, nullable=False
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="inactive")
    plan_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    current_period_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    characters_used: Mapped[int] = mapped_column(BigInteger, default=0)
    quota_limit: Mapped[int] = mapped_column(BigInteger, default=0)

    user: Mapped["User"] = relationship("User", back_populates="subscription")
