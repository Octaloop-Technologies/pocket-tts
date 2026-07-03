# Stripe Subscription Integration

This module adds subscription management with Stripe to your Kyutai Pocket TTS API.

## Installation

1. Install required packages:

   ```pwsh
   pip install fastapi sqlalchemy stripe python-multipart pydantic-settings
   ```

2. Set environment variables:

   ```text
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   STRIPE_PRICE_BASIC=price_...
   STRIPE_PRICE_PRO=price_...
   STRIPE_PRICE_ENTERPRISE=price_...
   STRIPE_CUSTOMER_PORTAL_URL=https://billing.stripe.com/...
   DATABASE_URL=sqlite:///./subscriptions.db # or PostgreSQL
   ```

3. Create database tables:

   ```python
   from strip_subscription.database import engine, Base
   Base.metadata.create_all(bind=engine)
   Integration with Your Existing TTS Endpoint
   Mount the router in your main FastAPI app:
   ```

   ```python
   from strip_subscription.routes import router as stripe_router
   app.include_router(stripe_router)
   Protect your /tts endpoint using the provided dependencies:
   ```

   ```python
   from strip_subscription.dependencies import get_current_user, get_active_subscription, check_quota

   @app.post("/tts")
   async def tts_endpoint(
       text: str = Form(...),
       voice_url: Optional[str] = Form(None),
       voice_wav: Optional[UploadFile] = File(None),
       user: User = Depends(get_current_user),
       sub: Subscription = Depends(get_active_subscription),
   ):
       # Check quota (optional, you can incorporate check inside)
       if sub.characters_used + len(text) > sub.quota_limit:
           raise HTTPException(429, "Monthly character limit exceeded")

       # Your TTS logic here...
       sub.characters_used += len(text)
       db.commit()
       return audio
   ```

Webhook endpoint is at /stripe/webhook – configure this URL in your Stripe Dashboard.

## Testing

Use Stripe test keys and test card

Test webhooks locally with Stripe CLI: stripe listen --forward-to localhost:8000/stripe/webhook.

---

## How to Use

1. Copy the entire `./strip_subscription/` folder into your project.
2. Follow the instructions in the `README.md` to set up environment variables, create tables, and mount the router.
3. The module provides a complete subscription workflow: checkout, webhook sync, customer portal, cancellation, and quota enforcement.
4. The `/tts` endpoint is now protected – only active subscribers with remaining quota can generate speech.

This is a production‑ready, self‑contained integration that respects your existing OpenAPI spec while adding monetization.
