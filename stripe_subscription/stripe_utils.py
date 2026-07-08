"""
Stripe subscription synchronization utilities.
Handles fetching subscription data from Stripe and syncing to local DB.
"""

import logging
from datetime import datetime
from typing import Optional

import stripe
from sqlalchemy.orm import Session

from .config import settings
from .models import Plan, Subscription, User

logger = logging.getLogger(__name__)

# ── Fix: use raw string from SecretStr ──
stripe.api_version = settings.STRIPE_API_VERSION
stripe.api_key = settings.get_stripe_secret_key()  # ← extract raw value


def get_plan_by_price_id(price_id: str, db: Session) -> Optional[Plan]:
    """Find a plan by its Stripe Price ID (matches either monthly or yearly)."""
    return (
        db.query(Plan)
        .filter(
            (Plan.stripe_price_monthly == price_id)
            | (Plan.stripe_price_yearly == price_id)
        )
        .first()
    )


def sync_subscription_from_stripe(
    subscription_id: str, db: Session, user_id: Optional[int] = None
) -> None:
    """
    Fetch a subscription from Stripe and create/update it in the local database.
    """
    logger.info(f"Starting sync for subscription {subscription_id}")

    # 1. Retrieve Stripe subscription
    try:
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        logger.debug(
            f"Stripe subscription retrieved: {stripe_sub.id}, status={stripe_sub.status}"
        )
    except stripe.StripeError as e:
        logger.error(
            f"Stripe API error retrieving subscription {subscription_id}: {e}",
            exc_info=True,
        )
        raise

    # 2. Resolve local user if not provided
    if user_id is None:
        customer_id = getattr(stripe_sub, "customer", None)
        if not customer_id:
            logger.error(f"No customer ID in subscription {subscription_id}")
            raise ValueError("Missing customer ID")
        try:
            customer = stripe.Customer.retrieve(customer_id)
        except stripe.StripeError as e:
            logger.error(
                f"Failed to retrieve customer {customer_id}: {e}", exc_info=True
            )
            raise
        user = db.query(User).filter_by(stripe_customer_id=customer.id).first()
        if not user:
            logger.error(f"No local user found for Stripe customer {customer.id}")
            raise ValueError("Local user not found")
        user_id = user.id  # type: ignore
        logger.info(f"Resolved user_id={user_id} from customer {customer.id}")

    # 3. Extract price ID from subscription items
    items = getattr(stripe_sub, "items", None)
    if not items or not hasattr(items, "data") or not items.data:
        logger.error(f"No items found in subscription {subscription_id}")
        raise ValueError("Subscription has no items")

    price = getattr(items.data[0], "price", None)
    if not price:
        logger.error(f"No price in first item for subscription {subscription_id}")
        raise ValueError("No price in subscription item")
    price_id = getattr(price, "id", None)
    if not price_id:
        logger.error(f"No price ID in price object for subscription {subscription_id}")
        raise ValueError("Missing price ID")

    logger.info(f"Price ID: {price_id}")

    # 4. Find local plan
    plan = get_plan_by_price_id(price_id, db)
    if not plan:
        logger.error(f"No local plan found for price ID {price_id}")
        raise ValueError(f"Plan not found for price {price_id}")

    # 5. Determine interval
    recurring = getattr(price, "recurring", {})
    interval = getattr(recurring, "interval", "monthly")
    logger.info(f"Interval: {interval}")

    # 6. Extract period timestamps
    current_period_start = getattr(stripe_sub, "current_period_start", None)
    current_period_end = getattr(stripe_sub, "current_period_end", None)
    start_date = (
        datetime.fromtimestamp(current_period_start) if current_period_start else None
    )
    end_date = (
        datetime.fromtimestamp(current_period_end) if current_period_end else None
    )

    # 7. Look for existing local subscription
    local_sub = (
        db.query(Subscription).filter_by(stripe_subscription_id=subscription_id).first()
    )

    if local_sub:
        logger.info(
            f"Updating existing subscription {subscription_id} for user {local_sub.user_id}"
        )
        local_sub.status = getattr(stripe_sub, "status", "active")  # type: ignore
        local_sub.start_date = start_date  # type: ignore
        local_sub.end_date = end_date  # type: ignore
        if local_sub.status == "active":  # type: ignore
            local_sub.characters_used = 0  # type: ignore
    else:
        logger.info(f"Creating new subscription {subscription_id} for user {user_id}")
        local_sub = Subscription(
            user_id=user_id,
            plan_id=plan.id,
            stripe_subscription_id=subscription_id,
            status=getattr(stripe_sub, "status", "active"),
            start_date=start_date,
            end_date=end_date,
            quota_limit=plan.quota_limit,
            interval=interval,
            characters_used=0,
        )
        db.add(local_sub)

    # 8. Commit transaction
    try:
        db.commit()
        logger.info(
            f"Subscription {subscription_id} successfully synced for user {user_id}"
        )
    except Exception as e:
        logger.error(
            f"Database commit failed for subscription {subscription_id}: {e}",
            exc_info=True,
        )
        db.rollback()
        raise
