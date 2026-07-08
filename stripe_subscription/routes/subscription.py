import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from stripe_subscription.config import settings
from stripe_subscription.database import get_db
from stripe_subscription.dependencies import get_current_user
from stripe_subscription.models import Plan, Subscription, User
from stripe_subscription.stripe_utils import sync_subscription_from_stripe
from stripe_subscription.utils import format_subscription_response

router = APIRouter()


@router.get("/subscription")
async def get_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the user's current subscription status."""
    user_id = int(user.id)  # type: ignore
    local_sub = db.query(Subscription).filter_by(user_id=user_id).first()

    if local_sub and local_sub.status == "active":  # type: ignore
        return format_subscription_response(local_sub)

    # Try to find via Stripe by email
    stripe_customer_id = getattr(user, "stripe_customer_id", None)
    if not stripe_customer_id:
        customers = stripe.Customer.list(email=user.email, limit=1)  # type: ignore
        if customers.data:
            customer = customers.data[0]
            user.stripe_customer_id = customer.id  # type: ignore
            stripe_customer_id = customer.id
            db.commit()
            logging.getLogger(__name__).info(
                f"Stored stripe_customer_id for user {user_id}: {stripe_customer_id}"
            )

    if stripe_customer_id:
        stripe_subs = stripe.Subscription.list(
            customer=stripe_customer_id, status="active", limit=1
        )
        if stripe_subs.data:
            stripe_sub = stripe_subs.data[0]
            sync_subscription_from_stripe(stripe_sub.id, db, user_id=user_id)
            local_sub = db.query(Subscription).filter_by(user_id=user_id).first()
            if local_sub:
                return format_subscription_response(local_sub)

    return {"plan": None, "status": "none", "remaining_characters": 0}


@router.get("/plans")
async def get_plans(db: Session = Depends(get_db)):
    """Get all available plans."""
    plans = db.query(Plan).filter_by(is_active=True).all()
    return {
        "plans": [
            {
                "tier": p.tier,
                "name": p.name,
                "monthly_price": p.monthly_price,
                "yearly_price": p.yearly_price,
                "quota_limit": p.quota_limit,
            }
            for p in plans
        ]
    }


@router.get("/payment-link")
async def get_payment_link(
    plan: str,
    interval: str,
    user: User = Depends(get_current_user),
):
    """Generate a personalized Stripe payment link."""
    key = f"STRIPE_PRICE_{plan.upper()}_{interval.upper()}_LINK"
    payment_link = getattr(settings, key, None)

    if not payment_link:
        raise HTTPException(
            status_code=404,
            detail=f"No payment link configured for {plan}/{interval}.",
        )

    parsed = urlparse(payment_link)
    query = parse_qs(parsed.query)

    query["client_reference_id"] = [str(user.id)]
    query["prefilled_email"] = [user.email]

    if getattr(settings, "STRIPE_PAYMENT_SUCCESS_URL", None):
        query["redirect_url"] = [settings.STRIPE_PAYMENT_SUCCESS_URL]

    payment_link = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    logging.getLogger(__name__).info(
        "Generated payment link for user %s (%s %s)",
        user.id,
        plan,
        interval,
    )

    return {"url": payment_link}
