"""Security response headers middleware."""

from __future__ import annotations

import logging
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

org_id_var: ContextVar[str] = ContextVar("org_id", default="default")


class TenantRLSMiddleware(BaseHTTPMiddleware):
    """Extracts org_id from JWT payload to set up context for PostgreSQL RLS.

    The org_id is set by the auth dependency (get_current_user) after proper
    JWT verification. This middleware only initialises the context variable
    with a safe default.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        org_id = "default"

        token_ctx = org_id_var.set(org_id)
        try:
            return await call_next(request)
        finally:
            org_id_var.reset(token_ctx)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds recommended security headers to every response.

    Parameters
    ----------
    app:
        The ASGI application (injected automatically by Starlette).
    cors_origins:
        Allowed origins that should be included in the CSP ``connect-src``
        directive so that the browser permits XHR/fetch/WebSocket calls to
        those origins.
    csp_extra_sources:
        Space-separated additional sources appended to ``connect-src``
        (e.g. analytics or third-party API domains).
    """

    def __init__(
        self,
        app: object,
        *,
        cors_origins: list[str] | None = None,
        csp_extra_sources: str = "",
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._csp = self._build_csp(cors_origins or [], csp_extra_sources)

    # -- internals -------------------------------------------------------------

    @staticmethod
    def _build_csp(cors_origins: list[str], csp_extra_sources: str) -> str:
        """Build the Content-Security-Policy header value.

        ``connect-src`` includes ``'self'``, ``ws:`` and ``wss:`` (for
        WebSocket connections to Colyseus / event streams), every configured
        CORS origin, and any extra sources from the config.
        """
        connect_parts = ["'self'", "ws:", "wss:"]
        for origin in cors_origins:
            origin = origin.strip()
            if origin and origin not in connect_parts:
                connect_parts.append(origin)
        if csp_extra_sources:
            for src in csp_extra_sources.split():
                src = src.strip()
                if src and src not in connect_parts:
                    connect_parts.append(src)

        connect_src = " ".join(connect_parts)

        directives = [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            f"connect-src {connect_src}",
            "frame-src 'self' https:",
            "media-src 'self' blob:",
            "worker-src 'self' blob:",
        ]
        return "; ".join(directives)

    # -- middleware dispatch ---------------------------------------------------

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
        response.headers["Content-Security-Policy"] = self._csp
        return response
