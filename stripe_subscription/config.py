# stripe_subscription/config.py
"""
Configuration management using Pydantic Settings.
All settings are validated at startup - the app fails fast if config is wrong.
"""

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    # JWT (for password reset)
    JWT_SECRET_KEY: str = Field(default="", description="Secret key for JWT tokens")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")

    # Stripe API
    STRIPE_SECRET_KEY: SecretStr = Field(default=SecretStr(""))
    STRIPE_PUBLISHABLE_KEY: str = Field(default="")
    STRIPE_WEBHOOK_SECRET: SecretStr = Field(default=SecretStr(""))
    STRIPE_API_VERSION: str = Field(default="2025-02-24.acacia")

    # Payment Links
    STRIPE_PRICE_BASIC_MONTHLY_LINK: str = Field(default="")
    STRIPE_PRICE_BASIC_YEARLY_LINK: str = Field(default="")
    STRIPE_PRICE_PRO_MONTHLY_LINK: str = Field(default="")
    STRIPE_PRICE_PRO_YEARLY_LINK: str = Field(default="")
    STRIPE_PRICE_ENTERPRISE_MONTHLY_LINK: str = Field(default="")
    STRIPE_PRICE_ENTERPRISE_YEARLY_LINK: str = Field(default="")

    # Price IDs
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

    # Rate Limiting
    RATE_LIMIT_MAX_REQUESTS: int = Field(
        default=10, description="Max requests per window"
    )
    RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=60, description="Rate limit window in seconds"
    )

    # Security
    MAX_TEXT_LENGTH: int = Field(
        default=5000, description="Maximum text length per TTS request"
    )
    BCRYPT_ROUNDS: int = Field(default=12, description="bcrypt work factor")

    # Email (for password reset)
    SMTP_HOST: str = Field(default="")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: SecretStr = Field(default=SecretStr(""))
    EMAIL_FROM: str = Field(default="noreply@example.com")
    FRONTEND_URL: str = Field(default="http://localhost:8000")

    @field_validator("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", mode="before")
    @classmethod
    def validate_secrets_not_empty(cls, v: str | SecretStr) -> SecretStr | str:
        if isinstance(v, str) and not v.strip():
            return v
        if isinstance(v, SecretStr) and not v.get_secret_value().strip():
            return v
        return v

    def get_stripe_secret_key(self) -> str:
        return self.STRIPE_SECRET_KEY.get_secret_value()

    def get_stripe_webhook_secret(self) -> str:
        return self.STRIPE_WEBHOOK_SECRET.get_secret_value()


settings = Settings()
