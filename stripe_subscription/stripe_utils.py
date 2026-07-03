from datetime import datetime

import stripe
from sqlalchemy.orm import Session

from .config import settings
from .logging import logger
from .models import Plan, Subscription, User

stripe.api_version = settings.STRIPE_API_VERSION
stripe.api_key = settings.STRIPE_SECRET_KEY  # ensure this is set in env


def get_plan_by_price_id(price_id: str, db: Session) -> Plan | None:
    # Query Plan by stored price ids
    plan = (
        db.query(Plan)
        .filter(
            (Plan.stripe_price_monthly == price_id)
            | (Plan.stripe_price_yearly == price_id)
        )
        .first()
    )
    if not plan:
        # Fallback: try to infer from environment (if you stored mapping)
        # For now, log and return None
        logger.warning(f"No plan found for price_id: {price_id}")
    return plan


def sync_subscription_from_stripe(
    subscription_id: str, db: Session, user_id: int | None = None
):
    try:
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        local_sub = (
            db.query(Subscription)
            .filter_by(stripe_subscription_id=subscription_id)
            .first()
        )

        # Extract timestamps safely
        current_period_start = getattr(stripe_sub, "current_period_start", None)
        current_period_end = getattr(stripe_sub, "current_period_end", None)

        if not local_sub:
            # If user_id not given, try to find via customer
            if not user_id:
                customer = stripe.Customer.retrieve(stripe_sub.customer)
                user = db.query(User).filter_by(stripe_customer_id=customer.id).first()
                if not user:
                    logger.error(f"Cannot find user for subscription {subscription_id}")
                    return
                user_id = int(user.id) if hasattr(user.id, "__int__") else user.id

            # Determine plan from price
            items_data = (
                stripe_sub.get("items", {}).get("data", [])
                if hasattr(stripe_sub, "get")
                else getattr(stripe_sub, "items", {})
            )
            if hasattr(items_data, "data"):
                items_data = items_data.data

            if not items_data:
                logger.error(f"No items found for subscription {subscription_id}")
                return

            price = (
                items_data[0].get("price")
                if hasattr(items_data[0], "get")
                else getattr(items_data[0], "price", {})
            )
            price_id = (
                price.get("id") if hasattr(price, "get") else getattr(price, "id", "")
            )

            plan = get_plan_by_price_id(price_id, db)
            if not plan:
                logger.error(f"Plan not found for price {price_id}")
                return

            # Get interval
            recurring = (
                price.get("recurring")
                if hasattr(price, "get")
                else getattr(price, "recurring", {})
            )
            interval = (
                recurring.get("interval")
                if hasattr(recurring, "get")
                else getattr(recurring, "interval", "month")
            )

            local_sub = Subscription(
                user_id=user_id,
                plan_id=plan.id,
                stripe_subscription_id=subscription_id,
                status=getattr(stripe_sub, "status", "active"),
                start_date=(
                    datetime.fromtimestamp(current_period_start)
                    if current_period_start
                    else None
                ),
                end_date=(
                    datetime.fromtimestamp(current_period_end)
                    if current_period_end
                    else None
                ),
                quota_limit=plan.quota_limit,
                interval=interval,
                characters_used=0,
            )
            db.add(local_sub)
            logger.info(
                f"Created new subscription {subscription_id} for user {user_id}"
            )
        else:
            # Update existing subscription
            local_sub.status = getattr(stripe_sub, "status", "active")
            if current_period_start:
                local_sub.start_date = datetime.fromtimestamp(current_period_start)
            if current_period_end:
                local_sub.end_date = datetime.fromtimestamp(current_period_end)
            if (
                local_sub.status == "active"
                and getattr(local_sub, "status", "") != "active"
            ):
                local_sub.characters_used = 0  # reset usage on renewal
            logger.info(
                f"Updated subscription {subscription_id} for user {local_sub.user_id}"
            )

        db.commit()
        logger.info(f"Subscription {subscription_id} synced successfully")
    except Exception as e:
        logger.error(
            f"Error syncing subscription {subscription_id}: {str(e)}", exc_info=True
        )
        raise
