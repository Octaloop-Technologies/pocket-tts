"""
Utility functions for subscription responses and Stripe helpers.
"""

from typing import Any

from .models import Subscription


def format_subscription_response(sub: Subscription) -> dict[str, Any]:
    """Format subscription data for API responses."""
    plan = sub.plan
    quota = sub.quota_limit
    used = sub.characters_used
    remaining = max(quota - used, 0)
    return {
        "plan": plan.name if plan else "Unknown",
        "status": sub.status,
        "current_period_end": (
            sub.end_date.isoformat() if sub.end_date is not None else None
        ),
        "remaining_characters": remaining,
        "interval": sub.interval,
        "plan_tier": plan.tier if plan else None,
    }
