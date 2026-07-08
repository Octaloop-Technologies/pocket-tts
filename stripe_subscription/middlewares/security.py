"""
Security middleware for SOC2 compliance.
Adds OWASP-recommended security headers to all responses.
"""

from fastapi import Request
from secure import Secure
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all responses.
    Uses the 'secure' library with balanced defaults.[reference:9]
    """

    def __init__(self, app):
        super().__init__(app)
        self.secure_headers = Secure.with_default_headers()

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Apply security headers
        if isinstance(response, Response):
            self.secure_headers.set_headers(response)

        return response


# Alternative: Direct integration with SecureASGIMiddleware
# from secure.middleware import SecureASGIMiddleware
# app.add_middleware(SecureASGIMiddleware, secure=Secure.with_default_headers())
