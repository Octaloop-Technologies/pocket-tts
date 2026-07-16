import smtplib
from email.mime.text import MIMEText

from stripe_subscription.config import settings


def test():
    smtp_host = settings.SMTP_HOST
    smtp_port = settings.SMTP_PORT
    username = settings.SMTP_USER
    password = settings.SMTP_PASSWORD.get_secret_value()
    from_addr = settings.SMTP_USER
    to_addr = "ali.hussain.abid.246@outlook.com"

    msg = MIMEText("Test email from Pocket TTS")
    msg["Subject"] = "Test"
    msg["From"] = from_addr
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(username, password)
            failed = server.sendmail(from_addr, [to_addr], msg.as_string())
            print(f"Send result: {failed}")
            if not failed:
                print("Email sent successfully.")
            else:
                print(f"Failures: {failed}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test()
