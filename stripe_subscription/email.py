import logging
import smtplib
import traceback
from email.mime.text import MIMEText

from .config import settings

logger = logging.getLogger(__name__)


def send_reset_email(email: str, token: str) -> bool:
    print(f"[DEBUG] send_reset_email called for {email}")  # <-- Always prints

    reset_link = f"{settings.FRONTEND_URL}/?token={token}"
    subject = "Pocket TTS - Password Reset"
    body = f"""
You requested a password reset for your Pocket TTS account.

Click the link below to set a new password (valid for 30 minutes):
{reset_link}

If you did not request this, please ignore this email.
"""

    print(f"[DEBUG] Reset link: {reset_link}")
    logger.info(f"Reset link for {email}: {reset_link}")

    # Check SMTP configuration
    print(f"[DEBUG] SMTP_HOST: {settings.SMTP_HOST}")
    print(f"[DEBUG] SMTP_PORT: {settings.SMTP_PORT}")
    print(f"[DEBUG] SMTP_USER: {settings.SMTP_USER}")
    print(f"[DEBUG] EMAIL_FROM: {settings.EMAIL_FROM}")

    if not settings.SMTP_HOST:
        print("[DEBUG] SMTP_HOST is empty, returning True (link logged only)")
        logger.warning("SMTP_HOST is empty - email not sent, but link is logged.")
        return True

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = email

    server = None
    try:
        print(
            f"[DEBUG] Attempting to connect to {settings.SMTP_HOST}:{settings.SMTP_PORT}"
        )
        logger.info(
            f"Attempting to send to {email} via {settings.SMTP_HOST}:{settings.SMTP_PORT}"
        )

        if settings.SMTP_PORT == 465:
            print("[DEBUG] Using SMTP_SSL")
            server = smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=30
            )
        elif settings.SMTP_PORT == 587:
            print("[DEBUG] Using STARTTLS")
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)
            server.starttls()
        else:
            raise ValueError(
                f"Unsupported SMTP port: {settings.SMTP_PORT}. Use 465 or 587."
            )

        print("[DEBUG] Connected successfully")

        if settings.SMTP_USER:
            print("[DEBUG] Logging in...")
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value())
            print("[DEBUG] Login successful")

        print("[DEBUG] Sending email...")
        failed = server.sendmail(settings.EMAIL_FROM, [email], msg.as_string())
        print(f"[DEBUG] sendmail returned: {failed}")

        if failed:
            logger.error(f"sendmail returned failures: {failed}")
            print(f"[DEBUG] sendmail failed: {failed}")
            return False

        logger.info(f"Email accepted by server for {email}")
        print("[DEBUG] Email accepted by server")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP auth failed: {e}")
        print(f"[DEBUG] SMTP Authentication Error: {e}")
        return False
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"Recipient refused: {e}")
        print(f"[DEBUG] Recipient Refused: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        print(f"[DEBUG] SMTP Exception: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())
        print(f"[DEBUG] Unexpected error: {e}")
        print(traceback.format_exc())
        return False
    finally:
        if server:
            try:
                server.quit()
                print("[DEBUG] Connection closed")
            except Exception as e:
                print(f"[DEBUG] Error during quit: {e}")
                pass
