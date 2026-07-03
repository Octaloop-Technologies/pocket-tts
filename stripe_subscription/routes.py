from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .dependencies import get_current_user
from .logging import logger
from .models import AuditLog, Plan, Subscription, User
from .stripe_utils import sync_subscription_from_stripe
from .utils import generate_api_key, hash_password, verify_password

router = APIRouter(prefix="/stripe", tags=["subscription"])


# ----- Request Models -----
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class PaymentLinkRequest(BaseModel):
    plan: str  # 'basic', 'pro', 'enterprise'
    interval: str  # 'monthly', 'yearly'


# ----- Helper: Audit logging -----
def log_audit(
    db: Session,
    user_id: int | None,
    action: str,
    details: dict = None,
    request: Request = None,
):
    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        details=str(details) if details else None,
        ip_address=request.client.host if request else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(log_entry)
    db.commit()
    logger.info(f"Audit: user={user_id}, action={action}")


# ----- Endpoints -----
@router.post("/register")
async def register_user(
    req: RegisterRequest, request: Request, db: Session = Depends(get_db)
):
    logger.info(f"Registration attempt for email: {req.email}")
    try:
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
        log_audit(db, user.id, "register", {"email": req.email}, request)
        logger.info(f"User registered: {user.id} ({req.email})")
        return {"api_key": api_key, "user_id": user.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        raise HTTPException(500, "Internal server error")


@router.post("/login")
async def login_user(
    req: LoginRequest, request: Request, db: Session = Depends(get_db)
):
    logger.info(f"Login attempt for email: {req.email}")
    try:
        user = db.query(User).filter_by(email=req.email).first()
        if not user or not verify_password(req.password, user.password_hash):
            logger.warning(f"Invalid credentials for {req.email}")
            raise HTTPException(401, "Invalid credentials")
        user.last_login = datetime.utcnow()
        db.commit()
        log_audit(db, user.id, "login", None, request)
        logger.info(f"User logged in: {user.id} ({req.email})")
        return {"api_key": user.api_key, "user_id": user.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        raise HTTPException(500, "Internal server error")


@router.get("/subscription")
async def get_subscription(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    try:
        # Extract user ID for safer typing
        user_id = int(user.id) if hasattr(user.id, "__int__") else user.id

        # First, check local database for subscription
        local_sub = db.query(Subscription).filter_by(user_id=user_id).first()
        logger.info(
            f"Checking subscription for user {user_id}: found local_sub={local_sub is not None}"
        )

        # If user has stripe_customer_id, verify active subscription from Stripe
        stripe_customer_id = getattr(user, "stripe_customer_id", None)
        logger.info(f"User {user_id} stripe_customer_id: {stripe_customer_id}")

        if stripe_customer_id is not None and stripe_customer_id:
            try:
                logger.info(
                    f"Querying Stripe for active subscriptions for customer {stripe_customer_id}"
                )
                stripe_subs = stripe.Subscription.list(
                    customer=stripe_customer_id, status="active", limit=1
                )
                logger.info(
                    f"Stripe returned {len(stripe_subs.data)} active subscriptions"
                )

                if stripe_subs.data:
                    # Found active subscription on Stripe
                    stripe_sub = stripe_subs.data[0]
                    logger.info(f"Found active Stripe subscription: {stripe_sub.id}")

                    # Sync it to local database
                    from .stripe_utils import sync_subscription_from_stripe

                    sync_subscription_from_stripe(stripe_sub.id, db, user_id=user_id)
                    # Refresh local_sub after sync
                    local_sub = (
                        db.query(Subscription).filter_by(user_id=user_id).first()
                    )
                    logger.info(
                        f"Synced active subscription from Stripe for user {user_id}: {local_sub is not None}"
                    )
                else:
                    logger.info(
                        f"No active Stripe subscriptions found for customer {stripe_customer_id}"
                    )
            except Exception as e:
                logger.warning(
                    f"Error checking Stripe for user {user_id}: {str(e)}", exc_info=True
                )
                # Continue with local database info if Stripe check fails

        if not local_sub:
            logger.info(f"No subscription found for user {user_id}")
            return {"plan": None, "status": "none", "remaining_characters": 0}

        # Extract values safely from ORM object
        status = getattr(local_sub, "status", "unknown")
        quota_limit = getattr(local_sub, "quota_limit", 0)
        characters_used = getattr(local_sub, "characters_used", 0)
        end_date = getattr(local_sub, "end_date", None)
        interval = getattr(local_sub, "interval", "unknown")
        plan = getattr(local_sub, "plan", None)

        remaining = max(quota_limit - characters_used, 0)
        plan_name = plan.name if plan else "Unknown"
        plan_tier = plan.tier if plan else None

        logger.info(
            f"User {user_id} subscription: status={status}, plan={plan_name}, remaining={remaining}"
        )

        return {
            "plan": plan_name,
            "status": status,
            "current_period_end": (end_date.isoformat() if end_date else None),
            "remaining_characters": remaining,
            "interval": interval,
            "plan_tier": plan_tier,
        }
    except Exception as e:
        logger.error(
            f"Error fetching subscription for user {user.id}: {str(e)}", exc_info=True
        )
        raise HTTPException(500, "Failed to fetch subscription")


@router.get("/plans")
async def get_plans(db: Session = Depends(get_db)):
    """Fetch all available plans with their pricing."""
    try:
        plans = db.query(Plan).filter_by(is_active=True).all()
        result = []
        for plan in plans:
            result.append(
                {
                    "tier": plan.tier,
                    "name": plan.name,
                    "monthly_price": plan.monthly_price,
                    "yearly_price": plan.yearly_price,
                    "quota_limit": plan.quota_limit,
                }
            )
        logger.info(f"Returned {len(result)} plans")
        return {"plans": result}
    except Exception as e:
        logger.error(f"Error fetching plans: {str(e)}", exc_info=True)
        raise HTTPException(500, "Failed to fetch plans")


@router.get("/payment-link")
async def get_payment_link(
    plan: str,
    interval: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logger.info(
        f"Payment link requested: plan={plan}, interval={interval}, user={user.id}"
    )
    try:
        # Build env key matching the .env format: STRIPE_PRICE_BASIC_MONTHLY
        key = f"STRIPE_PRICE_{plan.upper()}_{interval.upper()}"
        link = getattr(settings, key, None)
        if not link:
            logger.error(f"Payment link not configured for {plan}/{interval}")
            raise HTTPException(404, "Payment link not found")
        # Add client_reference_id and prefill email
        parsed = urlparse(link)
        query = parse_qs(parsed.query)
        query["client_reference_id"] = [str(user.id)]
        query["prefilled_email"] = [user.email]
        new_query = urlencode(query, doseq=True)
        new_link = urlunparse(parsed._replace(query=new_query))
        logger.info(f"Generated payment link for user {user.id}: {new_link}")
        return {"url": new_link}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating payment link: {str(e)}", exc_info=True)
        raise HTTPException(500, "Failed to generate payment link")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    logger.info("Webhook received")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(400, "Invalid payload")
    except stripe.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(400, "Invalid signature")
    # Process event
    try:
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            user_id = session.get("client_reference_id")
            if user_id:
                user = db.query(User).filter_by(id=int(user_id)).first()
                if user:
                    stripe_sub_id = session["subscription"]
                    stripe_customer_id = session.get("customer")
                    user_int_id = (
                        int(user.id) if hasattr(user.id, "__int__") else user.id
                    )

                    # Store stripe_customer_id on user for future lookups
                    if stripe_customer_id:
                        user_stripe_cust_id = getattr(user, "stripe_customer_id", None)
                        if not user_stripe_cust_id:
                            user.stripe_customer_id = stripe_customer_id
                            db.commit()
                            logger.info(
                                f"Stored stripe_customer_id for user {user_int_id}: {stripe_customer_id}"
                            )
                        else:
                            logger.info(
                                f"User {user_int_id} already has stripe_customer_id: {user_stripe_cust_id}"
                            )

                    sync_subscription_from_stripe(
                        stripe_sub_id, db, user_id=user_int_id
                    )
                    log_audit(
                        db,
                        user_int_id,
                        "payment_success",
                        {"session_id": session["id"], "subscription": stripe_sub_id},
                        request,
                    )
                    logger.info(f"Payment success for user {user_int_id}")
                else:
                    logger.warning(f"User not found for client_reference_id: {user_id}")
            else:
                logger.warning("No client_reference_id in checkout session")
        elif event["type"] in (
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            stripe_sub_id = event["data"]["object"]["id"]
            sync_subscription_from_stripe(stripe_sub_id, db)
        else:
            logger.info(f"Unhandled event type: {event['type']}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}", exc_info=True)
        raise HTTPException(500, "Webhook processing failed")


# DEBUG: Manual webhook retry endpoint (for testing webhook failures)
@router.post("/debug/sync-from-stripe")
async def debug_sync_from_stripe(email: str, db: Session = Depends(get_db)):
    """DEBUG ONLY: Manually sync user subscriptions from Stripe by email.

    This helps recover from webhook failures. Should be removed in production.
    Usage: POST /stripe/debug/sync-from-stripe?email=user@example.com
    """
    logger.warning(f"DEBUG: Manual sync requested for {email}")

    user = db.query(User).filter_by(email=email).first()
    if not user:
        raise HTTPException(404, f"User {email} not found")

    user_id = int(user.id) if hasattr(user.id, "__int__") else user.id
    logger.info(f"DEBUG: Manual sync for user {user_id} ({email})")

    # Query all subscriptions from Stripe for this email
    # (without stripe_customer_id, we search by email in checkout sessions)
    try:
        # List all customers with this email
        customers = stripe.Customer.list(email=email, limit=10)
        logger.info(
            f"DEBUG: Found {len(customers.data)} Stripe customers with email {email}"
        )

        synced_count = 0
        for customer in customers.data:
            stripe_customer_id = customer.id
            logger.info(f"DEBUG: Checking customer {stripe_customer_id}")

            # Store stripe_customer_id on user
            if not getattr(user, "stripe_customer_id", None):
                user.stripe_customer_id = stripe_customer_id
                db.commit()
                logger.info(f"DEBUG: Stored stripe_customer_id on user {user_id}")

            # Get active subscriptions for this customer
            subs = stripe.Subscription.list(
                customer=stripe_customer_id, status="active", limit=10
            )
            logger.info(f"DEBUG: Found {len(subs.data)} active subscriptions")

            for stripe_sub in subs.data:
                logger.info(f"DEBUG: Syncing subscription {stripe_sub.id}")
                sync_subscription_from_stripe(stripe_sub.id, db, user_id=user_id)
                synced_count += 1

        return {
            "status": "ok",
            "email": email,
            "user_id": user_id,
            "stripe_customer_id": getattr(user, "stripe_customer_id", None),
            "subscriptions_synced": synced_count,
        }
    except Exception as e:
        logger.error(f"DEBUG: Error syncing from Stripe: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Sync failed: {str(e)}")
