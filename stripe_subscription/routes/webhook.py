from __future__ import annotations

import logging
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from stripe_subscription.config import settings
from stripe_subscription.database import get_db
from stripe_subscription.models import User
from stripe_subscription.security import log_audit, safe_get
from stripe_subscription.stripe_utils import sync_subscription_from_stripe

router = APIRouter()


def handle_checkout_completed(
    data: dict[str, Any],
    db: Session,
    request: Request,
) -> None:
    logging.getLogger(__name__).info("Processing checkout.session.completed")

    user_id = safe_get(data, "client_reference_id")
    if not user_id:
        logging.getLogger(__name__).warning(
            "Checkout session missing client_reference_id."
        )
        return

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        logging.getLogger(__name__).warning("User %s not found.", user_id)
        return

    stripe_subscription_id = safe_get(data, "subscription")
    if not stripe_subscription_id:
        logging.getLogger(__name__).warning("Checkout session missing subscription id.")
        return

    stripe_customer_id = safe_get(data, "customer")
    if stripe_customer_id and user.stripe_customer_id != stripe_customer_id:
        user.stripe_customer_id = stripe_customer_id

    try:
        sync_subscription_from_stripe(
            stripe_subscription_id,
            db,
            user_id=user.id,
        )
        db.commit()
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception(
            "Failed syncing subscription %s",
            stripe_subscription_id,
        )
        raise

    try:
        log_audit(
            db=db,
            user_id=user.id,
            action="payment_success",
            details={
                "subscription": stripe_subscription_id,
                "session": safe_get(data, "id"),
            },
            request=request,
        )
    except Exception:
        logging.getLogger(__name__).exception("Failed writing audit log.")

    logging.getLogger(__name__).info(
        "Checkout completed successfully for user %s",
        user.id,
    )


def handle_subscription_updated(
    data: dict[str, Any],
    db: Session,
    request: Request,
) -> None:
    stripe_subscription_id = safe_get(data, "id")
    if not stripe_subscription_id:
        logging.getLogger(__name__).warning("subscription.updated missing id.")
        return

    try:
        sync_subscription_from_stripe(
            stripe_subscription_id,
            db,
        )
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception(
            "Unable to synchronize subscription %s",
            stripe_subscription_id,
        )
        raise


def handle_subscription_deleted(
    data: dict[str, Any],
    db: Session,
    request: Request,
) -> None:
    stripe_subscription_id = safe_get(data, "id")
    if not stripe_subscription_id:
        logging.getLogger(__name__).warning("subscription.deleted missing id.")
        return

    try:
        sync_subscription_from_stripe(
            stripe_subscription_id,
            db,
        )
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception(
            "Unable to synchronize deleted subscription %s",
            stripe_subscription_id,
        )
        raise


WEBHOOK_HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    webhook_secret = settings.get_stripe_webhook_secret()

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=webhook_secret,
        )
    except ValueError:
        logging.getLogger(__name__).exception("Invalid Stripe webhook payload.")
        raise HTTPException(400, "Invalid payload")
    except stripe.SignatureVerificationError:
        logging.getLogger(__name__).exception("Invalid Stripe webhook signature.")
        raise HTTPException(400, "Invalid signature")

    event_type = event["type"]
    handler = WEBHOOK_HANDLERS.get(event_type)

    if handler is None:
        logging.getLogger(__name__).debug("Ignoring event %s", event_type)
        return {"status": "ignored"}

    logging.getLogger(__name__).info(
        "Received Stripe event %s (%s)",
        event_type,
        event["id"],
    )

    try:
        handler(
            event["data"]["object"],
            db,
            request,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Webhook handler failed for %s",
            event_type,
        )
        raise HTTPException(
            status_code=500,
            detail="Webhook processing failed",
        )

    return {"status": "ok"}
