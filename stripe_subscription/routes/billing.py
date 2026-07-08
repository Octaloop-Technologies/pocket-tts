from fastapi import APIRouter, Depends, HTTPException

from stripe_subscription.config import settings
from stripe_subscription.dependencies import get_current_user
from stripe_subscription.models import User

router = APIRouter()


@router.get("/manage-billing")
async def manage_billing(user: User = Depends(get_current_user)):
    if not user.stripe_customer_id:  # type: ignore
        raise HTTPException(404, "No Stripe customer found for this user")
    portal_url = settings.STRIPE_CUSTOMER_PORTAL_URL
    if not portal_url:
        raise HTTPException(500, "Customer portal URL not configured")
    return {"portal_url": portal_url + "?prefilled_email=" + user.email}
