#!/usr/bin/env python3
"""
Fix: Update plan records with correct Stripe price IDs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import stripe
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from stripe_subscription.config import settings
from stripe_subscription.models import Plan

stripe.api_key = settings.STRIPE_SECRET_KEY
DATABASE_URL = settings.DATABASE_URL
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def update_price_ids():
    """Update plans with correct Stripe price IDs."""
    db = SessionLocal()

    try:
        # Get all prices from Stripe
        print("🔍 Fetching prices from Stripe...")
        prices = stripe.Price.list(limit=100, active=True)

        price_map = {}
        for price in prices.data:
            # Extract metadata to understand plan tier and interval
            product = stripe.Product.retrieve(price.product)
            metadata = product.get("metadata", {})
            tier = metadata.get("tier", "").lower()

            if not tier:
                continue

            interval = price.recurring.get("interval", "") if price.recurring else ""

            key = f"{tier}_{interval}"
            price_map[key] = price.id
            print(f"   {key}: {price.id}")

        print(f"\n📊 Found price IDs: {len(price_map)}")

        # Update plans
        plans = (
            db.query(Plan).filter(Plan.tier.in_(["basic", "pro", "enterprise"])).all()
        )

        print(f"\n📝 Updating {len(plans)} plans...")
        for plan in plans:
            tier = plan.tier.lower()

            # Look for monthly and yearly prices
            monthly_key = f"{tier}_month"
            yearly_key = f"{tier}_year"

            if monthly_key in price_map:
                plan.stripe_price_monthly = price_map[monthly_key]
                print(f"   {tier}: monthly = {price_map[monthly_key]}")

            if yearly_key in price_map:
                plan.stripe_price_yearly = price_map[yearly_key]
                print(f"   {tier}: yearly = {price_map[yearly_key]}")

        db.commit()
        print("\n✅ Updated all plans!")

        # Show final state
        print("\n📊 Final plan configuration:")
        for plan in db.query(Plan).all():
            print(f"   {plan.name}:")
            print(f"      Monthly: {plan.stripe_price_monthly}")
            print(f"      Yearly: {plan.stripe_price_yearly}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    update_price_ids()
