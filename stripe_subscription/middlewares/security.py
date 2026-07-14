"""
Security middleware for SOC2 compliance.
Adds OWASP-recommended security headers to all responses.
Skips documentation endpoints to allow Swagger UI to render.
"""

from fastapi import Request
from secure import Secure
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all responses except /docs, /openapi.json, /redoc.
    Uses the 'secure' library with balanced defaults.
    """

    def __init__(self, app):
        super().__init__(app)
        self.secure_headers = Secure.with_default_headers()

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Skip security headers for documentation routes
        if request.url.path in ("/docs", "/openapi.json", "/redoc"):
            return response

        if isinstance(response, Response):
            self.secure_headers.set_headers(response)

        return response
