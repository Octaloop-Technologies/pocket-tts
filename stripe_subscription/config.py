import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    # Stripe
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_API_VERSION: str = os.getenv("STRIPE_API_VERSION", "2025-02-24.acacia")
    STRIPE_PRICE_BASIC: str = os.getenv("STRIPE_PRICE_BASIC", "")
    STRIPE_PRICE_PRO: str = os.getenv("STRIPE_PRICE_PRO", "")
    STRIPE_PRICE_ENTERPRISE: str = os.getenv("STRIPE_PRICE_ENTERPRISE", "")
    STRIPE_CUSTOMER_PORTAL_URL: str = os.getenv(
        "STRIPE_CUSTOMER_PORTAL_URL", "https://billing.stripe.com/..."
    )

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./subscriptions.db")

    # App
    API_KEY_HEADER: str = "X-API-Key"


settings = Settings()

# Map plan names to Stripe Price IDs
PLAN_PRICE_MAP = {
    "basic": settings.STRIPE_PRICE_BASIC,
    "pro": settings.STRIPE_PRICE_PRO,
    "enterprise": settings.STRIPE_PRICE_ENTERPRISE,
}

# Character quotas per plan (per billing period)
PLAN_QUOTAS = {
    "basic": 50_000,
    "pro": 250_000,
    "enterprise": 1_500_000,
}
