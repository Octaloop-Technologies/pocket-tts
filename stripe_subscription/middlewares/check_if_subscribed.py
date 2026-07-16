"""
Subscription check middleware.
Intercepts POST /tts to verify active subscription before processing.
"""

from datetime import datetime, timezone

from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from stripe_subscription.config import settings
from stripe_subscription.database import get_db
from stripe_subscription.middlewares.security import ensure_utc_aware
from stripe_subscription.models import Subscription, User


class SubscriptionMiddleware(BaseHTTPMiddleware):
    """Middleware that checks for active subscription on POST /tts."""

    async def dispatch(self, request: Request, call_next):
        # Only intercept POST /tts
        if request.method == "POST" and request.url.path == "/tts":
            api_key = request.headers.get(settings.API_KEY_HEADER)

            if not api_key:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Missing API key", "redirect": "/"},
                )

            db: Session = next(get_db())
            try:
                user = db.query(User).filter_by(api_key=api_key).first()
                if not user:
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "Invalid API key", "redirect": "/"},
                    )

                sub = (
                    db.query(Subscription)
                    .filter_by(user_id=user.id, status="active")
                    .first()
                )

                if not sub:
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            "detail": "Active subscription required",
                            "redirect": "/",
                        },
                    )

                end_date = ensure_utc_aware(sub.end_date)  # type: ignore
                if end_date is not None and end_date < datetime.now(timezone.utc):
                    sub.status = "expired"  # type: ignore
                    db.commit()
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Subscription expired", "redirect": "/"},
                    )

            finally:
                db.close()

        return await call_next(request)
