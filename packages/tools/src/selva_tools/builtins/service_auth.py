"""Service credentials for tools that call MADFAM ecosystem APIs.

Every request a tool sends to Yantra4D, Cotiza or Pravara-MES carries a bearer
token (``Authorization: Bearer`` plus ``X-Service-Actor: selva-agent``), and a
tool sends nothing when it has no credential.

Yantra4D and Pravara-MES are machine edges. Each accepts a short-lived Janua
``client_credentials`` token that carries its scope (``yantra4d:render``,
``pravara-mes:read``), and Janua issues those tokens for an hour, so a token
stored in the environment cannot serve production. For a machine edge Selva
holds the confidential client's id and secret instead (``SELVA_YANTRA4D_CLIENT_ID``
/ ``SELVA_YANTRA4D_CLIENT_SECRET``, ``SELVA_PRAVARA_CLIENT_ID`` /
``SELVA_PRAVARA_CLIENT_SECRET``), exchanges them at Janua's token endpoint
(``JANUA_ISSUER_URL`` + ``/api/v1/oauth/token``) for a token with the edge's
scope, and reuses that token until 60 seconds before it expires.

An edge with no client credentials falls back to a static token read from its
token variables, in order. Cotiza is not a machine edge: it only uses its
static token.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..base import ToolResult

logger = logging.getLogger(__name__)

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

#: Janua's OAuth token endpoint, relative to its issuer URL.
JANUA_TOKEN_PATH = "/api/v1/oauth/token"
#: A cached machine token is replaced this many seconds before it expires.
TOKEN_REFRESH_MARGIN_S = 60.0
_MINT_TIMEOUT_S = 10.0
#: Hosts the token endpoint may be reached on over plain http (local development).
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class MachineEdge:
    """A Janua ``client_credentials`` edge: one client, one scope."""

    service: str
    scope: str
    client_id_env: str
    client_secret_env: str
    token_env: tuple[str, ...]


YANTRA4D_EDGE = MachineEdge(
    service="Yantra4D",
    scope="yantra4d:render",
    client_id_env="SELVA_YANTRA4D_CLIENT_ID",
    client_secret_env="SELVA_YANTRA4D_CLIENT_SECRET",
    token_env=YANTRA4D_TOKEN_ENV,
)
PRAVARA_EDGE = MachineEdge(
    service="Pravara-MES",
    scope="pravara-mes:read",
    client_id_env="SELVA_PRAVARA_CLIENT_ID",
    client_secret_env="SELVA_PRAVARA_CLIENT_SECRET",
    token_env=PRAVARA_TOKEN_ENV,
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


def missing_credentials(edge: MachineEdge) -> ToolResult:
    """Result returned when a machine edge has neither client credentials nor a token."""
    return ToolResult(
        success=False,
        error=(
            f"{edge.service} service token not configured (set {edge.client_id_env} and "
            f"{edge.client_secret_env}, or {' or '.join(edge.token_env)}); no request was sent."
        ),
    )


def machine_token_unavailable(edge: MachineEdge, reason: str) -> ToolResult:
    """Result returned when a machine edge is configured but yields no token."""
    return ToolResult(
        success=False,
        error=f"{edge.service} machine token unavailable: {reason}; no request was sent.",
    )


class TokenMintError(Exception):
    """Janua issued no token. The message never carries a credential or a token."""


class ClientCredentialsTokenProvider:
    """Mints Janua ``client_credentials`` tokens for one edge and caches them.

    The cached token is reused until ``TOKEN_REFRESH_MARGIN_S`` before it
    expires: the sooner of the response's ``expires_in`` and the token's own
    ``exp``. A token whose lifetime cannot be read is used once and not cached.

    Concurrent callers on one event loop wait for a single mint (an
    ``asyncio.Lock`` per loop, since workers run tools on several loops). A
    failed mint caches nothing, so the next call tries again.
    """

    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._clock = clock
        self._wall_clock = wall_clock
        #: (token, monotonic time from which it must be replaced)
        self._cached: tuple[str, float] | None = None
        self._locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
            weakref.WeakKeyDictionary()
        )
        self._locks_guard = threading.Lock()

    def __repr__(self) -> str:
        # Never the client secret or a token.
        return f"ClientCredentialsTokenProvider(scope={self._scope!r}, url={self._token_url!r})"

    def uses(self, token_url: str, client_id: str, client_secret: str) -> bool:
        """Whether this provider was built from exactly these settings."""
        return (self._token_url, self._client_id, self._client_secret) == (
            token_url,
            client_id,
            client_secret,
        )

    async def get_token(self) -> str:
        """Return a token for this edge, minting one when none is cached.

        Raises ``TokenMintError`` when Janua does not issue one.
        """
        token = self._fresh_token()
        if token is not None:
            return token
        async with self._loop_lock():
            token = self._fresh_token()
            if token is not None:
                return token
            self._cached = None
            token, lifetime = await self._mint()
            reusable_for = 0.0 if lifetime is None else lifetime - TOKEN_REFRESH_MARGIN_S
            self._cached = (token, self._clock() + max(reusable_for, 0.0))
            return token

    def _fresh_token(self) -> str | None:
        cached = self._cached
        if cached is not None and self._clock() < cached[1]:
            return cached[0]
        return None

    def _loop_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        with self._locks_guard:
            lock = self._locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[loop] = lock
        return lock

    async def _mint(self) -> tuple[str, float | None]:
        try:
            async with httpx.AsyncClient(timeout=_MINT_TIMEOUT_S) as client:
                response = await client.post(
                    self._token_url,
                    data={"grant_type": "client_credentials", "scope": self._scope},
                    auth=httpx.BasicAuth(self._client_id, self._client_secret),
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            # The exception holds the request, and the request holds the
            # credentials: report only its type, and do not chain it.
            raise TokenMintError(
                f"Janua token endpoint unreachable ({exc.__class__.__name__})"
            ) from None
        if not response.is_success:
            code = _oauth_error_code(response)
            suffix = f" ({code})" if code else ""
            raise TokenMintError(
                f"Janua token endpoint answered HTTP {response.status_code}{suffix}"
            )
        try:
            payload = response.json()
        except ValueError:
            raise TokenMintError("Janua token response is not JSON") from None
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise TokenMintError("Janua token response carried no access_token")
        token = token.strip()
        return token, _token_lifetime(payload, token, self._wall_clock())


def _oauth_error_code(response: httpx.Response) -> str:
    """The OAuth error code in a Janua error body (``invalid_client``), else ``""``.

    Only the code before the first colon is kept: it is enough to act on and
    cannot echo anything the request carried.
    """
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    for key in ("error", "detail"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            code = value.strip().split(":", 1)[0].strip()
            if code.replace("_", "").isalnum():
                return code[:64]
    return ""


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _jwt_exp(token: str) -> float | None:
    """The ``exp`` claim of a JWT, read unverified and used only to time the cache."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    segment = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(segment))
    except ValueError:
        return None
    return _seconds(claims.get("exp")) if isinstance(claims, dict) else None


def _token_lifetime(payload: dict[str, Any], token: str, now: float) -> float | None:
    """Seconds the token stays valid: the sooner of ``expires_in`` and ``exp``."""
    lifetimes: list[float] = []
    expires_in = _seconds(payload.get("expires_in"))
    if expires_in is not None:
        lifetimes.append(expires_in)
    exp = _jwt_exp(token)
    if exp is not None:
        lifetimes.append(exp - now)
    return min(lifetimes) if lifetimes else None


def janua_token_url() -> tuple[str, str]:
    """Janua's token endpoint from ``JANUA_ISSUER_URL``, as ``(url, problem)``.

    Exactly one of the two is non-empty. The endpoint must be https; plain
    http is accepted only on a loopback host, for local development.
    """
    issuer = os.environ.get("JANUA_ISSUER_URL", "").strip().rstrip("/")
    if not issuer:
        return "", "JANUA_ISSUER_URL is not set"
    parts = urlsplit(issuer)
    if parts.hostname and (
        parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS)
    ):
        return issuer + JANUA_TOKEN_PATH, ""
    return "", "JANUA_ISSUER_URL must be an https URL"


_PROVIDERS: dict[MachineEdge, ClientCredentialsTokenProvider] = {}
_PROVIDERS_GUARD = threading.Lock()


def reset_token_cache() -> None:
    """Forget every cached machine token and provider."""
    with _PROVIDERS_GUARD:
        _PROVIDERS.clear()


def _provider_for(
    edge: MachineEdge, token_url: str, client_id: str, client_secret: str
) -> ClientCredentialsTokenProvider:
    with _PROVIDERS_GUARD:
        provider = _PROVIDERS.get(edge)
        if provider is None or not provider.uses(token_url, client_id, client_secret):
            provider = ClientCredentialsTokenProvider(
                token_url=token_url,
                client_id=client_id,
                client_secret=client_secret,
                scope=edge.scope,
            )
            _PROVIDERS[edge] = provider
        return provider


async def machine_auth_headers(
    edge: MachineEdge, static_token: str | None = None
) -> tuple[dict[str, str], ToolResult | None]:
    """Headers for one request over ``edge``, or the result to return instead.

    With both of the edge's client credentials set, the bearer is a Janua
    machine token minted (or reused from the cache) for the edge's scope.
    With neither set, it is the static token: ``static_token`` when given,
    else the first of the edge's token variables. Returns ``({}, result)``
    when there is no usable credential; the caller must send nothing.
    """
    client_id = os.environ.get(edge.client_id_env, "").strip()
    client_secret = os.environ.get(edge.client_secret_env, "").strip()
    if not client_id and not client_secret:
        token = first_env(edge.token_env) if static_token is None else static_token
        headers = service_auth_headers(token)
        return (headers, None) if headers else ({}, missing_credentials(edge))
    if not client_id or not client_secret:
        absent = edge.client_secret_env if client_id else edge.client_id_env
        return {}, machine_token_unavailable(edge, f"{absent} is not set")

    token_url, problem = janua_token_url()
    if problem:
        return {}, machine_token_unavailable(edge, problem)

    provider = _provider_for(edge, token_url, client_id, client_secret)
    try:
        token = await provider.get_token()
    except TokenMintError as exc:
        logger.warning(
            "Janua machine token not issued for %s (scope %s): %s", edge.service, edge.scope, exc
        )
        return {}, machine_token_unavailable(edge, str(exc))
    return service_auth_headers(token), None


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
