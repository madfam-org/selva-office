"""``POST /mcp``: the HTTP edge of Selva's native MCP (RFC 0051 Phase A).

Order of checks, all before any tool runs:

1. ``SELVA_MCP_ENABLED`` off → 404 (before authentication: nothing answers).
2. A browser ``Origin`` header → 403 (MCP's DNS-rebinding rule; machine
   clients send none).
3. ``auth.verify_jwt``, the same Janua decode as every route (RS256 / JWKS,
   issuer, Selva's API audience ``JANUA_CLIENT_ID``, ``exp``) → 401. The worker
   shared secret is not a JWT and is refused here too.
4. A person's token, or a machine token without ``selva-cogs:read`` → 403.
5. A machine token not bound to an organization (no ``org_id``) → 403.
6. Per-client rate limit (``SELVA_MCP_RATE_PER_MINUTE``) → 429.

Each ``tools/call`` (and each refused-by-rate call) writes ONE audit line on
logger ``selva.mcp.audit``: client, tool, outcome, latency and the SHA-256 of
the canonical arguments. Never the arguments, the org or any result.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response

from ..auth import verify_jwt
from ..config import get_settings
from . import protocol
from .registry import ToolContext
from .tools import TOOLS

audit_logger = logging.getLogger("selva.mcp.audit")

#: Janua machine scope for Selva's COGS reads (RFC 0051 M2: one colon).
SELVA_COGS_READ_SCOPE = "selva-cogs:read"
#: Janua ``client_credentials`` subject prefix.
SERVICE_ACCOUNT_SUB_PREFIX = "service-account:"

try:
    from prometheus_client import Counter

    TOOL_CALLS: Any = Counter(
        "selva_mcp_tool_calls_total",
        "MCP tool calls by tool and outcome (ok, tool_error, invalid_arguments, "
        "unknown_tool, internal_error, rate_limited).",
        ["tool", "outcome"],
    )
except ImportError:  # pragma: no cover - prometheus_client ships with the instrumentator
    TOOL_CALLS = None

router = APIRouter(tags=["mcp"])


class ClientRateLimiter:
    """Fixed one-minute window per machine client, in this process.

    Per pod: with N replicas a client gets up to N x the limit. A shared
    (Redis) counter is a follow-up; the IP-level ``RateLimitMiddleware`` still
    applies in front of this.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[int, int]] = {}

    def allow(self, client: str, limit: int, now: float | None = None) -> bool:
        window = int((time.time() if now is None else now) // 60)
        with self._lock:
            if len(self._windows) > 10_000:  # bounded memory; stale windows only
                self._windows = {k: v for k, v in self._windows.items() if v[0] == window}
            seen_window, count = self._windows.get(client, (window, 0))
            count = count + 1 if seen_window == window else 1
            self._windows[client] = (window, count)
            return count <= limit

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


rate_limiter = ClientRateLimiter()


def audit(client: str, tool: str, outcome: str, latency_ms: int, digest: str = "") -> None:
    if TOOL_CALLS is not None:
        TOOL_CALLS.labels(tool or "-", outcome).inc()
    line = {
        "client": client,
        "tool": tool or "-",
        "outcome": outcome,
        "latency_ms": latency_ms,
        "args_sha256": digest,
    }
    audit_logger.info("mcp.call %s", json.dumps(line, sort_keys=True))


def _require_enabled() -> None:
    if not get_settings().selva_mcp_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


async def _machine_context(request: Request) -> ToolContext:
    """Verify the bearer token and return the caller's org and client id."""
    authorization = request.headers.get("authorization", "")
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = await verify_jwt(token, get_settings())
    sub = str(payload.get("sub") or "")
    if not sub.startswith(SERVICE_ACCOUNT_SUB_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Selva's MCP takes Janua machine tokens only for now (RFC 0051).",
        )
    if SELVA_COGS_READ_SCOPE not in str(payload.get("scope") or "").split():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Service token missing required scope '{SELVA_COGS_READ_SCOPE}'.",
        )
    org_id = str(payload.get("org_id") or "").strip()
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service client is not bound to an organization.",
        )
    return ToolContext(org_id=org_id, client_id=sub.removeprefix(SERVICE_ACCOUNT_SUB_PREFIX))


@router.post("/mcp", include_in_schema=False)
async def mcp_post(request: Request) -> Response:
    _require_enabled()
    if request.headers.get("origin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Browser origins are not accepted on this endpoint.",
        )
    context = await _machine_context(request)
    if not rate_limiter.allow(context.client_id, get_settings().selva_mcp_rate_per_minute):
        audit(context.client_id, "", "rate_limited", 0)
        return JSONResponse(
            {"detail": "Rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"}
        )
    version = request.headers.get("mcp-protocol-version", "").strip()
    if version and version not in protocol.SUPPORTED_VERSIONS:
        return JSONResponse(
            {"detail": f"Unsupported MCP-Protocol-Version {version[:32]}"}, status_code=400
        )
    started = time.monotonic()
    exchange = await protocol.handle(await request.body(), context, TOOLS)
    if exchange.method == "tools/call":
        latency_ms = int((time.monotonic() - started) * 1000)
        audit(
            context.client_id,
            exchange.tool,
            exchange.outcome or "invalid_params",
            latency_ms,
            exchange.args_sha256,
        )
    if exchange.body is None:
        return Response(status_code=202)
    return JSONResponse(exchange.body, status_code=exchange.status)


@router.api_route("/mcp", methods=["GET", "DELETE"], include_in_schema=False)
async def mcp_other(request: Request) -> Response:
    """Stateless server: no SSE stream to open and no session to end."""
    _require_enabled()
    return Response(status_code=405, headers={"Allow": "POST"})
