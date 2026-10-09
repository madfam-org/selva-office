"""Service-token helpers for tools that call MADFAM ecosystem APIs.

Every request a tool sends to Yantra4D, Cotiza or Pravara-MES carries Selva's
service token (``Authorization: Bearer`` plus ``X-Service-Actor:
selva-agent``). Tools resolve the token from the variables below, in order,
and send nothing when none is set.
"""

from __future__ import annotations

import os

import httpx

from ..base import ToolResult

YANTRA4D_TOKEN_ENV: tuple[str, ...] = (
    "YANTRA4D_API_TOKEN",
    "SELVA_YANTRA4D_SERVICE_TOKEN",
    "SELVA_SERVICE_TOKEN",
)
COTIZA_TOKEN_ENV: tuple[str, ...] = (
    "COTIZA_API_TOKEN",
    "SELVA_COTIZA_SERVICE_TOKEN",
    "SELVA_SERVICE_TOKEN",
)
PRAVARA_TOKEN_ENV: tuple[str, ...] = (
    "PRAVARA_MES_API_TOKEN",
    "SELVA_PRAVARA_SERVICE_TOKEN",
    "SELVA_SERVICE_TOKEN",
)


def first_env(names: tuple[str, ...]) -> str:
    """Return the first non-empty environment variable among ``names``."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def service_auth_headers(token: str) -> dict[str, str]:
    """Headers for a service call, or ``{}`` when there is no token."""
    token = str(token or "").strip()
    if not token:
        return {}
    return {
        "Authorization": f"Bearer {token}",
        "X-Service-Actor": "selva-agent",
    }


def missing_token(service: str, env_names: tuple[str, ...]) -> ToolResult:
    """Result returned instead of sending a request without a token."""
    return ToolResult(
        success=False,
        error=(
            f"{service} service token not configured (set {' or '.join(env_names)}); "
            "no request was sent."
        ),
    )


def http_error_detail(exc: httpx.HTTPError) -> str:
    """Describe an HTTP failure, using the service's own error text when present."""
    if not isinstance(exc, httpx.HTTPStatusError):
        return str(exc) or exc.__class__.__name__
    response = exc.response
    try:
        body = response.json()
    except ValueError:
        body = None
    messages: list[str] = []
    if isinstance(body, dict):
        for key in ("error", "message", "detail"):
            value = body.get(key)
            if value and str(value) not in messages:
                messages.append(str(value))
    if not messages and response.text:
        messages.append(response.text[:300])
    detail = " - ".join(messages)
    return f"HTTP {response.status_code}: {detail}" if detail else f"HTTP {response.status_code}"
