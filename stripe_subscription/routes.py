import logging
import secrets
import uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .dependencies import get_current_user
from .models import Subscription, User
from .stripe_utils import (
    cancel_subscription_at_period_end,
    create_customer_portal_session,
    get_or_create_stripe_customer,
    reset_usage,
    sync_subscription_from_stripe,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe", tags=["subscription"])


class RegisterRequest(BaseModel):
    email: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str


class CreateSubscriptionRequest(BaseModel):
    price_id: str


@router.post("/register")
async def register_user(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=req.email).first():
        raise HTTPException(400, "Email already registered")
    api_key = f"sk_{secrets.token_urlsafe(32)}"
    user = User(email=req.email, api_key=api_key)
    db.add(user)
    db.commit()
    try:
        customer = stripe.Customer.create(
            email=req.email, metadata={"user_id": str(user.id)}
        )
        user.stripe_customer_id = customer.id
        db.commit()
    except stripe.StripeError:
        pass
    return {"api_key": api_key, "user_id": user.id}


@router.post("/login")
async def login_user(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=req.email).first()
    if not user:
        raise HTTPException(404, "User not found")
    return {"api_key": user.api_key, "user_id": user.id}


@router.get("/user")
async def get_user_info(user: User = Depends(get_current_user)):
    return {"email": user.email, "id": user.id}


@router.get("/config")
async def get_config():
    prices = []
    fallback_prices = [
        {
            "id": settings.STRIPE_PRICE_BASIC,
            "name": "Basic",
            "amount": 500,
            "currency": "usd",
        },
        {
            "id": settings.STRIPE_PRICE_PRO,
            "name": "Pro",
            "amount": 1500,
            "currency": "usd",
        },
        {
            "id": settings.STRIPE_PRICE_ENTERPRISE,
            "name": "Enterprise",
            "amount": 5000,
            "currency": "usd",
        },
    ]

    for item in fallback_prices:
        price_id = item["id"]
        if not price_id:
            logger.warning(f"Price ID for {item['name']} is empty, skipping.")
            continue
        try:
            price = stripe.Price.retrieve(price_id)
            prices.append(
                {
                    "id": price.id,
                    "name": item["name"],
                    "amount": price.unit_amount,
                    "currency": price.currency,
                    "lookup_key": price.lookup_key,
                    "recurring": price.recurring,
                }
            )
        except stripe.InvalidRequestError as e:
            logger.error(f"Price ID {price_id} not found: {e}")
        except stripe.AuthenticationError as e:
            logger.error(f"Stripe authentication error: {e}")
        except stripe.StripeError as e:
            logger.error(f"Stripe error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

    if not prices:
        for item in fallback_prices:
            if item["id"]:
                prices.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "amount": item["amount"],
                        "currency": item["currency"],
                        "lookup_key": item["name"].lower(),
                        "recurring": {"interval": "month"},
                    }
                )
        logger.warning(
            "Using fallback price list because Stripe prices could not be retrieved."
        )

    return {
        "publishableKey": settings.STRIPE_PUBLISHABLE_KEY,
        "prices": prices,
    }


@router.post("/create-subscription")
async def create_subscription(
    req: CreateSubscriptionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    price_id = req.price_id
    customer_id = get_or_create_stripe_customer(user, db)
    idempotency_key = f"sub_create_{user.id}_{uuid.uuid4()}"

    try:
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id}],
            payment_behavior="default_incomplete",
            expand=["latest_invoice.confirmation_secret"],  # <-- Updated expand
            metadata={"user_id": str(user.id), "email": user.email or ""},
            idempotency_key=idempotency_key,
        )
        return {
            "subscriptionId": subscription.id,
            "clientSecret": subscription.latest_invoice.confirmation_secret.client_secret,  # <-- Fixed
        }
    except stripe.CardError as e:
        raise HTTPException(402, e.error.message or "Your card was declined.")
    except stripe.InvalidRequestError as e:
        raise HTTPException(400, e.error.message or "Invalid request.")
    except stripe.StripeError as e:
        raise HTTPException(500, f"Stripe error: {e.error.message}")


@router.get("/subscription")
async def get_subscription_details(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    sub = db.query(Subscription).filter_by(user_id=user.id).first()
    if not sub:
        return {"plan": None, "status": "none", "remaining_characters": 0}
    remaining = (sub.quota_limit - sub.characters_used) if sub.quota_limit else 0
    return {
        "plan": sub.plan_type,
        "status": sub.status,
        "current_period_end": (
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        "remaining_characters": max(remaining, 0),
    }


@router.post("/cancel-subscription")
async def cancel_subscription(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    sub = db.query(Subscription).filter_by(user_id=user.id, status="active").first()
    if not sub:
        raise HTTPException(400, "No active subscription")
    cancel_subscription_at_period_end(sub)
    return {"message": "Cancellation scheduled at period end"}


@router.get("/manage-billing")
async def billing_portal(user: User = Depends(get_current_user)):
    return {"portal_url": create_customer_portal_session(user)}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")
    data = event["data"]["object"]
    if event["type"] == "invoice.payment_succeeded":
        if data.get("billing_reason") == "subscription_create":
            subscription_id = data["subscription"]
            payment_intent_id = data.get("payment_intent")
            if payment_intent_id:
                if hasattr(payment_intent_id, "id"):
                    payment_intent_id = payment_intent_id.id
                try:
                    payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                    payment_method = payment_intent.payment_method
                    if payment_method:
                        payment_method_id = (
                            payment_method.id
                            if hasattr(payment_method, "id")
                            else payment_method
                        )
                        stripe.Subscription.modify(
                            subscription_id, default_payment_method=payment_method_id
                        )
                except stripe.StripeError:
                    pass
        if data.get("subscription"):
            reset_usage(data["subscription"], db)
    elif event["type"] in (
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        sync_subscription_from_stripe(data["id"], db)
    return {"status": "ok"}
