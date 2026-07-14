import logging
import smtplib
from email.mime.text import MIMEText

from .config import settings

logger = logging.getLogger(__name__)


def send_reset_email(email: str, token: str) -> bool:
    """Send a password reset email with a one‑time token."""
    reset_link = f"{settings.FRONTEND_URL}/?token={token}"
    subject = "Pocket TTS - Password Reset"
    body = f"""
You requested a password reset for your Pocket TTS account.

Click the link below to set a new password (valid for 30 minutes):
{reset_link}

If you did not request this, please ignore this email.
"""

    if not settings.SMTP_HOST:
        # Log the link for development (visible in server logs)
        logger.info(f"SMTP not configured. Reset link for {email}: {reset_link}")
        return True

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = email

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USER:
                server.starttls()
                server.login(
                    settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value()
                )
            server.sendmail(settings.EMAIL_FROM, [email], msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Failed to send reset email: {e}")
        return False
