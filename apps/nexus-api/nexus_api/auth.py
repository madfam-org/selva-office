"""Janua OIDC JWT verification and FastAPI authentication dependencies."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidKeyError, InvalidTokenError, PyJWTError

from .config import Settings, get_settings
from .middleware.security import org_id_var

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer()

# In-memory JWKS cache with TTL-based expiration.
# Thread-safety note: This module runs inside a single-process ASGI server
# (uvicorn) with a single-threaded asyncio event loop.  Global dict/float
# assignments are atomic under CPython's GIL, so no lock is needed.  If
# running under a multi-threaded ASGI server, wrap _fetch_jwks() with an
# asyncio.Lock.
_jwks_cache: dict[str, Any] | None = None
_jwks_cache_time: float | None = None
_JWKS_TTL_SECONDS = 3600.0
# httpx timeout for the JWKS well-known fetch. Janua usually responds in
# <100ms; the generous 10s window protects against cold-start CDN misses
# without blocking the whole verify path on a hung issuer.
_JWKS_FETCH_TIMEOUT_S: float = 10.0
# Janua rotates its signing key with a hard cut (no overlap window), so a token
# naming a `kid` that is not in the cached set triggers one JWKS refetch before
# it is rejected. The refetch is rate-limited process-wide, so tokens with
# forged `kid` values cannot turn into a stream of requests to Janua.
_JWKS_FORCED_REFRESH_MIN_INTERVAL_S = 60.0
_jwks_forced_refresh_time: float | None = None

# Janua signs access tokens with RS256 and names the signing key in the `kid`
# header (see docs/reference/ISSUER_AND_JWKS.md in madfam-org/janua). The
# allow-list is fixed here and never derived from the token header or the
# JWKS, so `none` and HMAC algorithms (key confusion with the public JWK) can
# never verify.
_JANUA_ALGORITHMS = ["RS256"]

# Clock-skew tolerance between Janua and this pod, applied to exp/nbf/iat.
# PyJWT rejects an `iat` in the future (python-jose did not), so a token minted
# by a Janua pod whose clock runs slightly ahead needs this to verify.
_JANUA_LEEWAY_SECONDS = 30

# Claims every Janua access token carries. python-jose accepted a token with no
# `exp` (it never expired) and skipped the audience check when `aud` was
# absent; requiring them closes both gaps. `iss` was already enforced.
_JANUA_REQUIRED_CLAIMS = ["exp", "iss", "aud"]

# Janua application role that grants Selva platform administration. Janua only
# publishes `<app>:<role>` strings under `roles` from an application-role grant
# (organization role names of that shape are dropped), so this string is an
# explicit grant. The admin console (`apps/admin`) honours the same role.
SELVA_ADMIN_APP_ROLE = "selva:admin"

# Janua claim carrying the user's role in the organization named by `org_id`.
ORG_ROLES_CLAIM = "madfam_org_roles"

# Organization role that administers the token's own organization.
ORG_ADMIN_ROLE = "admin"

# Role names that belong to the internal service credential (the worker shared
# secret below). They are never read from a bearer token's `roles` claim.
_SERVICE_CREDENTIAL_ROLES = frozenset({"service", "worker", "platform"})


class _UnknownKeyIdError(InvalidTokenError):
    """The token's ``kid`` is not in the JWKS (possibly a key rotation)."""


async def _fetch_jwks(issuer_url: str, *, force: bool = False) -> dict[str, Any]:
    """Fetch the JSON Web Key Set from the Janua OIDC well-known endpoint.

    Results are cached in-module with a 1-hour TTL.  After the TTL expires
    the next request will refresh the cache.  ``force=True`` bypasses the
    cache (used once per unknown ``kid``, see ``_claim_forced_refresh``).
    """
    global _jwks_cache, _jwks_cache_time  # noqa: PLW0603

    now = time.monotonic()
    if (
        not force
        and _jwks_cache is not None
        and _jwks_cache_time is not None
        and (now - _jwks_cache_time) < _JWKS_TTL_SECONDS
    ):
        return _jwks_cache

    jwks_url = f"{issuer_url.rstrip('/')}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=_JWKS_FETCH_TIMEOUT_S) as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_cache_time = now
        return _jwks_cache


def _claim_forced_refresh() -> bool:
    """Return True when a forced JWKS refetch is allowed now, and record it.

    At most one forced refetch per ``_JWKS_FORCED_REFRESH_MIN_INTERVAL_S``.
    """
    global _jwks_forced_refresh_time  # noqa: PLW0603

    now = time.monotonic()
    if (
        _jwks_forced_refresh_time is not None
        and (now - _jwks_forced_refresh_time) < _JWKS_FORCED_REFRESH_MIN_INTERVAL_S
    ):
        return False
    _jwks_forced_refresh_time = now
    return True


def _get_signing_key(jwks: dict[str, Any], token: str) -> dict[str, Any]:
    """Extract the correct signing key from the JWKS based on the token's ``kid`` header.

    Raises:
        jwt.PyJWTError: on a malformed token header, a missing ``kid`` or a
            ``kid`` that is not in the JWKS.
    """
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    if kid is None:
        raise InvalidTokenError("Token header missing 'kid' claim")

    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    raise _UnknownKeyIdError(f"Signing key '{kid}' not found in JWKS")


def _verification_key(jwk: dict[str, Any]) -> jwt.PyJWK:
    """Bind the selected JWK to the RS256 algorithm.

    A JWK that declares another ``alg`` or a non-signature ``use``, or that is
    not an RSA key, is rejected rather than verified.

    Raises:
        jwt.PyJWTError: when the JWK cannot verify an RS256 signature.
    """
    if jwk.get("alg") not in (None, *_JANUA_ALGORITHMS):
        raise InvalidKeyError(f"JWKS key alg {jwk.get('alg')!r} is not allowed")
    if jwk.get("use") not in (None, "sig"):
        raise InvalidKeyError(f"JWKS key use {jwk.get('use')!r} is not 'sig'")
    return jwt.PyJWK(jwk, algorithm=_JANUA_ALGORITHMS[0])


async def verify_jwt(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Decode and validate a Janua-issued RS256 JWT.

    Validates (PyJWT):
      - signature, with the JWKS key named by the token's ``kid``; an unknown
        ``kid`` refetches the JWKS once (rate-limited) before it is rejected;
      - algorithm, against the fixed ``["RS256"]`` allow-list;
      - ``exp`` (required), ``nbf`` and ``iat``, with a 30 s clock-skew leeway;
      - ``iss`` (required) equals ``janua_issuer_url``;
      - ``aud`` (required) contains ``janua_client_id``.

    Returns the full decoded payload on success.

    Raises:
        HTTPException(401): On any verification failure.
    """
    if settings is None:
        settings = get_settings()

    try:
        jwks = await _fetch_jwks(settings.janua_issuer_url)
        try:
            signing_key = _get_signing_key(jwks, token)
        except _UnknownKeyIdError:
            if not _claim_forced_refresh():
                raise
            logger.info("Token kid not in cached JWKS; refetching once (key rotation)")
            jwks = await _fetch_jwks(settings.janua_issuer_url, force=True)
            signing_key = _get_signing_key(jwks, token)

        payload: dict[str, Any] = jwt.decode(
            token,
            _verification_key(signing_key),
            algorithms=_JANUA_ALGORITHMS,
            audience=settings.janua_client_id,
            issuer=settings.janua_issuer_url,
            leeway=_JANUA_LEEWAY_SECONDS,
            options={"require": _JANUA_REQUIRED_CLAIMS},
        )
        return payload

    except PyJWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch JWKS: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """FastAPI dependency that extracts and verifies the Bearer token.

    Returns a user dict containing at minimum ``sub``, ``roles``, and
    ``org_id`` from the JWT claims.

    For worker/gateway shared-secret tokens, the target tenant org_id
    MUST be declared via the ``X-Selva-Tenant-Org`` request header.
    Calls without that header resolve to ``org_id="platform"`` and the
    receiving endpoint is expected to enforce the ``service`` role.
    """
    if settings.environment == "development" and settings.dev_auth_bypass:
        org_id_var.set("dev-org")
        return {
            "sub": "dev-user-00000000",
            "roles": ["admin", "tactician", "enterprise-cleanroom"],
            "org_id": "dev-org",
            "email": "dev@selva.local",
            "is_admin": True,
            "org_roles": ["admin"],
        }

    # Reject hardcoded dev token in production
    if settings.environment == "production" and credentials.credentials == "dev-bypass":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token for production environment",
        )

    # Worker/gateway service token (shared secret, not a JWT)
    if (
        settings.worker_api_token
        and settings.worker_api_token != "dev-bypass"
        and credentials.credentials == settings.worker_api_token
    ):
        # Worker token holders MUST declare their target tenant via header.
        # Falls back to "platform" only for cross-tenant maintenance ops
        # (those endpoints check for the "service" role explicitly).
        tenant_org = request.headers.get("X-Selva-Tenant-Org", "").strip()
        if not tenant_org:
            # Platform-scoped service call (e.g. /metrics, audit-log writers).
            # The endpoint itself must verify "service" role for safety.
            tenant_org = "platform"
        org_id_var.set(tenant_org)
        return {
            "sub": "service:worker",
            "roles": ["service", "worker"],
            "org_id": tenant_org,
            "email": "worker@selva.internal",
            "is_admin": False,
            "org_roles": [],
        }

    payload = await verify_jwt(credentials.credentials, settings)

    # Set the verified org_id in the context variable for RLS middleware
    org_id_var.set(payload.get("org_id", "default"))

    return {
        "sub": payload.get("sub"),
        "roles": _bearer_roles(payload.get("roles", [])),
        "org_id": payload.get("org_id"),
        "email": payload.get("email"),
        # Platform administrator: only the verified `is_admin` claim, exactly True.
        "is_admin": payload.get("is_admin") is True,
        # The user's role in the organization named by `org_id`.
        "org_roles": _string_list(payload.get(ORG_ROLES_CLAIM)),
    }


def _string_list(value: Any) -> list[str]:
    """A claim value as a list of strings (a bare string becomes one item)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple):
        return [item for item in value if isinstance(item, str)]
    return []


def _bearer_roles(value: Any) -> list[str]:
    """The `roles` claim of a bearer token, without service-credential role names."""
    return [role for role in _string_list(value) if role not in _SERVICE_CREDENTIAL_ROLES]


def is_platform_admin(user: dict[str, Any]) -> bool:
    """Whether the caller is a Selva platform administrator.

    True for the verified token's ``is_admin`` claim (exactly ``True``) or the
    ``selva:admin`` application role. A bare role name such as ``admin`` is an
    organization membership role in Janua tokens and never counts here.
    """
    if user.get("is_admin") is True:
        return True
    return SELVA_ADMIN_APP_ROLE in (user.get("roles") or [])


def is_org_admin(user: dict[str, Any]) -> bool:
    """Whether the caller administers the organization named by its own ``org_id``.

    Reads the role Janua stamps for that organization (``madfam_org_roles``),
    not the ``roles`` list, which merges roles from every organization the user
    belongs to.
    """
    if not user.get("org_id"):
        return False
    return ORG_ADMIN_ROLE in (user.get("org_roles") or [])


async def require_platform_admin(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Dependency for platform-level administration routes."""
    if not is_platform_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access required",
        )
    return user


def require_platform_admin_or_roles(roles: list[str]):
    """Dependency factory: a platform administrator, or ANY of ``roles``."""
    _reject_admin_role_name(roles)

    async def _checker(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        if is_platform_admin(user):
            return user
        user_roles = user.get("roles", [])
        if not any(r in user_roles for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Platform administrator or one of roles {roles} is required",
            )
        return user

    return _checker


async def require_org_admin(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Dependency for actions on the caller's OWN organization (``org_id``).

    Admits an administrator of that organization, or a platform administrator.
    Routes using it must act only on ``user["org_id"]``.
    """
    if is_platform_admin(user) or is_org_admin(user):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Organization administrator access required",
    )


def _reject_admin_role_name(roles: list[str]) -> None:
    """Refuse to build a role gate on the bare ``admin`` name.

    Use ``require_platform_admin`` or ``require_org_admin`` instead.
    """
    if ORG_ADMIN_ROLE in roles:
        raise ValueError(
            "Gate admin access with require_platform_admin or require_org_admin, "
            "not a bare role name"
        )


def require_role(role: str):
    """Dependency factory that enforces a specific role on the authenticated user.

    Usage::

        @router.post("/cleanroom", dependencies=[Depends(require_role("enterprise-cleanroom"))])
        async def cleanroom_endpoint(): ...

    For administration use ``require_platform_admin`` or ``require_org_admin``.
    """
    _reject_admin_role_name([role])

    async def _role_checker(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        if role not in user.get("roles", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is required",
            )
        return user

    return _role_checker


async def require_non_guest(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Reject guest users from performing write/privileged operations.

    Applied per-endpoint (not router-level) to preserve GET access for guests.
    """
    if "guest" in user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest users cannot perform this action",
        )
    return user


async def require_non_demo(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Block demo users from performing real actions."""
    if "demo" in user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo users cannot perform this action",
        )
    return user


async def require_a2a_caller(
    user: dict[str, Any] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Admit a verified caller to the A2A task routes while intake is enabled.

    The agent card stays public; ``tasks/*`` need a verified bearer token and
    ``A2A_INBOUND_ENABLED``. Guest and demo accounts cannot submit tasks.
    """
    if not settings.a2a_inbound_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A2A task intake is not enabled",
        )
    roles = user.get("roles", [])
    if "guest" in roles or "demo" in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account cannot submit A2A tasks",
        )
    return user


def bearer_token_from_request(request: Request) -> str | None:
    """Extract the raw Bearer token from an Authorization header, if present."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return token or None


def delegatable_user_jwt(
    request: Request,
    user: dict[str, Any],
    settings: Settings | None = None,
) -> str | None:
    """Return a user JWT safe to forward to workers for Coupler delegation.

    Skips service tokens, dev bypass, and worker shared-secret auth so
    workers never treat infrastructure credentials as end-user identity.
    """
    token = bearer_token_from_request(request)
    if not token:
        return None
    settings = settings or get_settings()
    if token == "dev-bypass":
        return None
    if settings.worker_api_token and token == settings.worker_api_token:
        return None
    sub = str(user.get("sub") or "")
    if sub.startswith("service:"):
        return None
    return token


# ---------------------------------------------------------------------------
# Type alias & multi-role factory used by Wave 4 routers
# ---------------------------------------------------------------------------

#: Type alias for the user dict returned by all auth dependencies.
CurrentUser = dict[str, Any]


def require_roles(roles: list[str]):
    """Dependency factory that enforces ANY of the given roles.

    Usage::

        @router.get("/cleanroom")
        async def endpoint(
            user: CurrentUser = Depends(require_roles(["enterprise-cleanroom"])),
        ): ...

    For administration use ``require_platform_admin`` or ``require_org_admin``.
    """
    _reject_admin_role_name(roles)

    async def _roles_checker(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        user_roles = user.get("roles", [])
        if not any(r in user_roles for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of roles {roles} is required",
            )
        return user

    return _roles_checker
