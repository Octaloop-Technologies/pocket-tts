from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Stripe API
    STRIPE_SECRET_KEY: str = Field(default="")
    STRIPE_PUBLISHABLE_KEY: str = Field(default="")
    STRIPE_WEBHOOK_SECRET: str = Field(default="")
    STRIPE_API_VERSION: str = Field(default="2025-02-24.acacia")

    # Payment Links (frontend)
    STRIPE_PRICE_BASIC_MONTHLY_LINK: str = Field(default="")
    STRIPE_PRICE_BASIC_YEARLY_LINK: str = Field(default="")
    STRIPE_PRICE_PRO_MONTHLY_LINK: str = Field(default="")
    STRIPE_PRICE_PRO_YEARLY_LINK: str = Field(default="")
    STRIPE_PRICE_ENTERPRISE_MONTHLY_LINK: str = Field(default="")
    STRIPE_PRICE_ENTERPRISE_YEARLY_LINK: str = Field(default="")

    # Price IDs (backend mapping)
    STRIPE_PRICE_BASIC_MONTHLY_ID: str = Field(default="")
    STRIPE_PRICE_BASIC_YEARLY_ID: str = Field(default="")
    STRIPE_PRICE_PRO_MONTHLY_ID: str = Field(default="")
    STRIPE_PRICE_PRO_YEARLY_ID: str = Field(default="")
    STRIPE_PRICE_ENTERPRISE_MONTHLY_ID: str = Field(default="")
    STRIPE_PRICE_ENTERPRISE_YEARLY_ID: str = Field(default="")

    # Customer Portal
    STRIPE_CUSTOMER_PORTAL_URL: str = Field(default="")

    # Redirect URLs
    STRIPE_PAYMENT_SUCCESS_URL: str = Field(
        default="http://localhost:8000/?success=true"
    )
    STRIPE_PAYMENT_CANCEL_URL: str = Field(default="http://localhost:8000/")

    # Database
    DATABASE_URL: str = Field(default="sqlite:///./subscriptions.db")

    # App
    API_KEY_HEADER: str = Field(default="X-API-Key")


settings = Settings()
