import hashlib
import os
import secrets

# Temporary: using SHA-256 with a static salt (not for production)
# This avoids bcrypt dependency. We'll replace with proper bcrypt later.
_SALT = os.getenv("PASSWORD_SALT", "pocket-tts-salt-2026").encode()


def hash_password(password: str) -> str:
    """Hash password using SHA-256 with a static salt (temporary)."""
    hash_obj = hashlib.sha256()
    hash_obj.update(_SALT)
    hash_obj.update(password.encode())
    return hash_obj.hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored hash."""
    return hash_password(password) == hashed


def generate_api_key() -> str:
    return f"sk_{secrets.token_urlsafe(32)}"
