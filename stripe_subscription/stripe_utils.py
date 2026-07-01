from datetime import datetime

import stripe
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .config import PLAN_PRICE_MAP, PLAN_QUOTAS, settings
from .models import Subscription, User

# Set API version from environment variable
stripe.api_version = settings.STRIPE_API_VERSION
stripe.api_key = settings.STRIPE_SECRET_KEY


def get_or_create_stripe_customer(user: User, db: Session) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email or f"user_{user.id}@example.com",
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


def create_customer_portal_session(user: User) -> str:
    if not user.stripe_customer_id:
        raise HTTPException(400, "No Stripe customer found")
    return stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=settings.STRIPE_CUSTOMER_PORTAL_URL,
    ).url


def cancel_subscription_at_period_end(subscription: Subscription) -> None:
    if not subscription.stripe_subscription_id:
        raise HTTPException(400, "No active Stripe subscription")
    stripe.Subscription.modify(
        subscription.stripe_subscription_id, cancel_at_period_end=True
    )


def sync_subscription_from_stripe(subscription_id: str, db: Session) -> None:
    stripe_sub = stripe.Subscription.retrieve(subscription_id)
    local_sub = (
        db.query(Subscription).filter_by(stripe_subscription_id=subscription_id).first()
    )
    if not local_sub:
        return
    local_sub.status = stripe_sub.status
    local_sub.current_period_start = datetime.fromtimestamp(
        stripe_sub.current_period_start
    )
    local_sub.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)
    if stripe_sub.status == "active":
        for item in stripe_sub["items"]["data"]:
            price_id = item["price"]["id"]
            for plan, pid in PLAN_PRICE_MAP.items():
                if pid == price_id:
                    local_sub.plan_type = plan
                    local_sub.quota_limit = PLAN_QUOTAS[plan]
                    break
    db.commit()


def reset_usage(subscription_id: str, db: Session) -> None:
    sub = (
        db.query(Subscription).filter_by(stripe_subscription_id=subscription_id).first()
    )
    if sub:
        sub.characters_used = 0
        db.commit()
