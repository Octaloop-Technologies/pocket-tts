#!/usr/bin/env python3
"""
Debug: Check Stripe subscription details and find the correct mapping.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import stripe

from stripe_subscription.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

# The subscription ID that admin@admin.com has
subscription_id = "sub_1Tp7VW058295zxTz8LgmKqRs"

print(f"Fetching Stripe subscription: {subscription_id}")
sub = stripe.Subscription.retrieve(subscription_id)

print("\n📊 Subscription Details:")
print(f"   ID: {sub.id}")
print(f"   Status: {getattr(sub, 'status', 'N/A')}")
print(f"   Customer: {getattr(sub, 'customer', 'N/A')}")

print("\n💰 Items:")
items = getattr(sub, "items", {})
if hasattr(items, "data"):
    item_list = items.data
else:
    item_list = []

for item in item_list:
    price = getattr(item, "price", {})
    price_id = getattr(price, "id", "")
    product_id = getattr(price, "product", "")

    print(f"   Price ID: {price_id}")
    print(f"   Product ID: {product_id}")

    if price_id and product_id:
        try:
            product = stripe.Product.retrieve(product_id)
            print(f"   Product Name: {product.name}")
            amount = getattr(price, "unit_amount", 0)
            currency = getattr(price, "currency", "usd").upper()
            print(f"   Amount: {amount / 100:.2f} {currency}")

            recurring = getattr(price, "recurring", {})
            if recurring:
                interval = getattr(recurring, "interval", "")
                print(f"   Interval: {interval}")

            metadata = getattr(product, "metadata", {})
            print(f"   Metadata: {metadata}")
        except Exception as e:
            print(f"   Error fetching product: {e}")
    print()
