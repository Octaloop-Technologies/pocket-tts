"""
Utility functions for subscription responses and Stripe helpers.
"""

from .models import Subscription


def format_subscription_response(sub: Subscription) -> dict:
    """Format subscription data for API responses."""
    plan = sub.plan
    remaining = max(sub.quota_limit - sub.characters_used, 0)
    return {
        "plan": plan.name if plan else "Unknown",
        "status": sub.status,
        "current_period_end": sub.end_date.isoformat() if sub.end_date else None,  # type: ignore
        "remaining_characters": remaining,
        "interval": sub.interval,
        "plan_tier": plan.tier if plan else None,
    }
