"""Request ID propagation middleware with structlog context binding."""

from __future__ import annotations

import uuid

import structlog.contextvars
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generates a unique X-Request-ID for each request.

    If the incoming request already carries an ``X-Request-ID`` header the
    existing value is preserved.  The ID is stored on ``request.state``,
    echoed in the response headers, and bound to structlog contextvars
    for automatic inclusion in all log events during the request.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Bind to structlog contextvars so all logs in this request include request_id.
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        # Clear contextvars after response to prevent leaking between requests.
        structlog.contextvars.clear_contextvars()

        return response
