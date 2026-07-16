import logging
import smtplib
import traceback
from email.mime.text import MIMEText

from .config import settings

logger = logging.getLogger(__name__)


def send_reset_email(email: str, token: str) -> bool:
    reset_link = f"{settings.FRONTEND_URL}/?token={token}"
    subject = "Pocket TTS - Password Reset"
    body = f"""
You requested a password reset for your Pocket TTS account.

Click the link below to set a new password (valid for 15 minutes):
{reset_link}

If you did not request this, please ignore this email.
"""

    logger.info(f"Reset link for {email}: {reset_link}")

    if not settings.SMTP_HOST:
        logger.warning("SMTP_HOST is empty - email not sent, but link is logged.")
        return True

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = email

    server: smtplib.SMTP_SSL | smtplib.SMTP | None = None
    try:
        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=30
            )
        elif settings.SMTP_PORT == 587:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)
            server.starttls()
        else:
            raise ValueError(
                f"Unsupported SMTP port: {settings.SMTP_PORT}. Use 465 or 587."
            )

        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value())

        failed = server.sendmail(settings.EMAIL_FROM, [email], msg.as_string())
        if failed:
            logger.error(f"sendmail returned failures: {failed}")
            return False

        logger.info(f"Email accepted by server for {email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        logger.error(traceback.format_exc())
        return False
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass
