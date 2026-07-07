"""
Stripe subscription API routes.
Includes authentication, plan selection, payment links, webhooks, and billing portal.
"""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .dependencies import get_current_user
from .models import AuditLog, Plan, Subscription, User
from .stripe_utils import sync_subscription_from_stripe
from .utils import generate_api_key, hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe", tags=["subscription"])


# ----- Helpers -----
def safe_get(obj, key, default=None):
    """Safely get a value from a Stripe object (handles missing .get() method)."""
    try:
        return obj[key] if hasattr(obj, "__getitem__") else getattr(obj, key, default)
    except (KeyError, AttributeError, TypeError):
        return default


def log_audit_safe(
    db: Session,
    user_id: Optional[int],
    action: str,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Log an audit entry safely, handling missing request attributes."""
    ip = (
        request.client.host
        if request and hasattr(request, "client") and request.client
        else None
    )
    ua = request.headers.get("user-agent") if request else None
    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        details=str(details) if details else None,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(log_entry)
    db.commit()
    logger.info(f"Audit: user={user_id}, action={action}")


def format_subscription_response(sub: Subscription) -> dict:
    """Format subscription data for API responses."""
    plan = sub.plan
    remaining = max(sub.quota_limit - sub.characters_used, 0)
    return {
        "plan": plan.name if plan else "Unknown",
        "status": sub.status,
        "current_period_end": sub.end_date.isoformat() if sub.end_date else None,
        "remaining_characters": remaining,
        "interval": sub.interval,
        "plan_tier": plan.tier if plan else None,
    }


# ----- Request Models -----
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


# ----- Auth Endpoints -----
@router.post("/register")
async def register_user(
    req: RegisterRequest, request: Request, db: Session = Depends(get_db)
):
    logger.info(f"Registration attempt for email: {req.email}")
    existing = db.query(User).filter_by(email=req.email).first()
    if existing:
        logger.warning(f"Email already registered: {req.email}")
        raise HTTPException(400, "Email already registered")

    api_key = generate_api_key()
    password_hash = hash_password(req.password)
    user = User(
        email=req.email,
        password_hash=password_hash,
        api_key=api_key,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_audit_safe(db, user.id, "register", {"email": req.email}, request)
    logger.info(f"User registered: {user.id} ({req.email})")
    return {"api_key": api_key, "user_id": user.id}


@router.post("/login")
async def login_user(
    req: LoginRequest, request: Request, db: Session = Depends(get_db)
):
    logger.info(f"Login attempt for email: {req.email}")
    user = db.query(User).filter_by(email=req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        logger.warning(f"Invalid credentials for {req.email}")
        raise HTTPException(401, "Invalid credentials")

    user.last_login = datetime.utcnow()
    db.commit()
    log_audit_safe(db, user.id, "login", None, request)
    logger.info(f"User logged in: {user.id} ({req.email})")
    return {"api_key": user.api_key, "user_id": user.id}


# ----- Subscription Endpoints -----
@router.get("/subscription")
async def get_subscription(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    user_id = int(user.id) if hasattr(user.id, "__int__") else user.id
    local_sub = db.query(Subscription).filter_by(user_id=user_id).first()

    if local_sub and local_sub.status == "active":
        return format_subscription_response(local_sub)

    # Try to find via Stripe by email
    stripe_customer_id = getattr(user, "stripe_customer_id", None)
    if not stripe_customer_id:
        customers = stripe.Customer.list(email=user.email, limit=1)
        if customers.data:
            customer = customers.data[0]
            user.stripe_customer_id = customer.id
            stripe_customer_id = customer.id
            db.commit()
            logger.info(
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
    """
    Return a Stripe Payment Link for the requested plan.

    The link includes:
      - client_reference_id
      - prefilled_email
      - redirect back to the application after payment
    """

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

    #
    # Your frontend route after successful payment.
    #
    # Example:
    #   http://localhost:3000/tts
    #   https://yourdomain.com/tts
    #
    if getattr(settings, "STRIPE_PAYMENT_SUCCESS_URL", None):
        query["redirect_url"] = [settings.STRIPE_PAYMENT_SUCCESS_URL]

    payment_link = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    logger.info(
        "Generated payment link for user %s (%s %s)",
        user.id,
        plan,
        interval,
    )

    return {"url": payment_link}


# ----- Webhook Handlers (Refactored with getattr) -----
def handle_checkout_completed(
    data,
    db: Session,
    request: Request,
) -> None:
    """
    Handle checkout.session.completed.

    This webhook links the Stripe customer to the local user,
    synchronizes the subscription and records an audit event.
    """

    logger.info("Processing checkout.session.completed")

    user_id = safe_get(data, "client_reference_id")
    if not user_id:
        logger.warning("Checkout session missing client_reference_id.")
        return

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        logger.warning("User %s not found.", user_id)
        return

    stripe_subscription_id = safe_get(data, "subscription")
    if not stripe_subscription_id:
        logger.warning("Checkout session missing subscription id.")
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
        logger.exception(
            "Failed syncing subscription %s",
            stripe_subscription_id,
        )
        raise

    try:
        log_audit_safe(
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
        logger.exception("Failed writing audit log.")

    logger.info(
        "Checkout completed successfully for user %s",
        user.id,
    )

    return


def handle_subscription_updated(
    data,
    db: Session,
    request: Request,
) -> None:
    """
    Synchronize an updated Stripe subscription.
    """

    del request

    stripe_subscription_id = safe_get(data, "id")
    if not stripe_subscription_id:
        logger.warning("subscription.updated missing id.")
        return

    try:
        sync_subscription_from_stripe(
            stripe_subscription_id,
            db,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "Unable to synchronize subscription %s",
            stripe_subscription_id,
        )
        raise


def handle_subscription_deleted(
    data,
    db: Session,
    request: Request,
) -> None:
    """
    Synchronize a deleted Stripe subscription.
    """

    del request

    stripe_subscription_id = safe_get(data, "id")
    if not stripe_subscription_id:
        logger.warning("subscription.deleted missing id.")
        return

    try:
        sync_subscription_from_stripe(
            stripe_subscription_id,
            db,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "Unable to synchronize deleted subscription %s",
            stripe_subscription_id,
        )
        raise


# Map event types to handlers
WEBHOOK_HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        logger.exception("Invalid Stripe webhook payload.")
        raise HTTPException(400, "Invalid payload")

    except stripe.SignatureVerificationError:
        logger.exception("Invalid Stripe webhook signature.")
        raise HTTPException(400, "Invalid signature")

    event_type = event["type"]
    handler = WEBHOOK_HANDLERS.get(event_type)

    if handler is None:
        logger.debug("Ignoring event %s", event_type)
        return {"status": "ignored"}

    logger.info(
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
        logger.exception(
            "Webhook handler failed for %s",
            event_type,
        )
        raise HTTPException(
            status_code=500,
            detail="Webhook processing failed",
        )

    return {"status": "ok"}


# ----- Billing Portal -----
@router.get("/manage-billing")
async def manage_billing(user: User = Depends(get_current_user)):
    if not user.stripe_customer_id:
        raise HTTPException(404, "No Stripe customer found for this user")
    portal_url = settings.STRIPE_CUSTOMER_PORTAL_URL
    if not portal_url:
        raise HTTPException(500, "Customer portal URL not configured")
    return {"portal_url": portal_url + "?prefilled_email=" + user.email}


# ----- Debug -----
@router.post("/debug/sync")
async def debug_sync_subscription(email: str, db: Session = Depends(get_db)):
    logger.warning(f"DEBUG: Manual sync requested for {email}")
    user = db.query(User).filter_by(email=email).first()
    if not user:
        raise HTTPException(404, f"User {email} not found")

    customers = stripe.Customer.list(email=email, limit=1)
    if not customers.data:
        return {"status": "error", "message": "No Stripe customer found"}
    customer = customers.data[0]
    user.stripe_customer_id = customer.id
    db.commit()

    subs = stripe.Subscription.list(customer=customer.id, status="active", limit=1)
    if not subs.data:
        return {"status": "ok", "message": "No active subscriptions"}
    sync_subscription_from_stripe(subs.data[0].id, db, user_id=user.id)
    return {"status": "ok", "message": f"Synced for user {user.id}"}
