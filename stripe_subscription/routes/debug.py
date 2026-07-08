import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from stripe_subscription.database import get_db
from stripe_subscription.models import User
from stripe_subscription.stripe_utils import sync_subscription_from_stripe

router = APIRouter()


@router.post("/debug/sync")
async def debug_sync_subscription(email: str, db: Session = Depends(get_db)):
    logging.getLogger(__name__).warning(f"DEBUG: Manual sync requested for {email}")
    user = db.query(User).filter_by(email=email).first()
    if not user:
        raise HTTPException(404, f"User {email} not found")

    customers = stripe.Customer.list(email=email, limit=1)
    if not customers.data:
        return {"status": "error", "message": "No Stripe customer found"}
    customer = customers.data[0]
    user.stripe_customer_id = customer.id  # type: ignore
    db.commit()

    subs = stripe.Subscription.list(customer=customer.id, status="active", limit=1)
    if not subs.data:
        return {"status": "ok", "message": "No active subscriptions"}
    sync_subscription_from_stripe(subs.data[0].id, db, user_id=user.id)  # type: ignore
    return {"status": "ok", "message": f"Synced for user {user.id}"}
