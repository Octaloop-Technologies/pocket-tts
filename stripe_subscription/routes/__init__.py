from fastapi import APIRouter

from .auth import router as auth_router
from .billing import router as billing_router
from .debug import router as debug_router
from .subscription import router as subscription_router
from .webhook import router as webhook_router

router = APIRouter(prefix="/stripe", tags=["subscription"])

router.include_router(auth_router)
router.include_router(subscription_router)
router.include_router(webhook_router)
router.include_router(billing_router)
router.include_router(debug_router)

__all__ = ["router"]
