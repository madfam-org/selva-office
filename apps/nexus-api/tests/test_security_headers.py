"""Tests for SecurityHeadersMiddleware: CSP, Permissions-Policy, and CORS integration.

These tests use a minimal FastAPI app to isolate the middleware behaviour from
the full application stack (auth bypass, CSRF, rate limiting, etc.).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from starlette.responses import PlainTextResponse

from nexus_api.middleware.security import SecurityHeadersMiddleware


def _make_app(
    *,
    cors_origins: list[str] | None = None,
    csp_extra_sources: str = "",
) -> FastAPI:
    """Build a minimal FastAPI app with only the SecurityHeadersMiddleware."""
    app = FastAPI()

    app.add_middleware(
        SecurityHeadersMiddleware,
        cors_origins=cors_origins,
        csp_extra_sources=csp_extra_sources,
    )

    @app.get("/ping")
    async def _ping() -> PlainTextResponse:
        return PlainTextResponse("pong")

    return app


# ---------------------------------------------------------------------------
# Standard security headers
# ---------------------------------------------------------------------------


class TestSecurityHeadersPresent:
    """All standard security headers are present on every response."""

    @pytest.mark.asyncio
    async def test_security_headers_present(self) -> None:
        app = _make_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/ping")

        assert resp.status_code == 200
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert "max-age=" in resp.headers["strict-transport-security"]
        assert "includeSubDomains" in resp.headers["strict-transport-security"]
        assert resp.headers["x-xss-protection"] == "0"
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "permissions-policy" in resp.headers
        assert "content-security-policy" in resp.headers


# ---------------------------------------------------------------------------
# Permissions-Policy
# ---------------------------------------------------------------------------


class TestPermissionsPolicy:
    """Permissions-Policy allows camera and microphone for own origin (WebRTC)."""

    @pytest.mark.asyncio
    async def test_permissions_policy_allows_camera_mic(self) -> None:
        app = _make_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/ping")

        policy = resp.headers["permissions-policy"]
        assert "camera=(self)" in policy
        assert "microphone=(self)" in policy
        assert "geolocation=()" in policy


# ---------------------------------------------------------------------------
# Content-Security-Policy
# ---------------------------------------------------------------------------


class TestCSPHeader:
    """Content-Security-Policy header is built correctly."""

    @pytest.mark.asyncio
    async def test_csp_header_present(self) -> None:
        """CSP header exists and contains all expected directives."""
        app = _make_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/ping")

        csp = resp.headers["content-security-policy"]

        # Every directive should appear in the policy string.
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp
        assert "img-src 'self' data: blob:" in csp
        assert "connect-src" in csp
        assert "frame-src 'self' https:" in csp
        assert "media-src 'self' blob:" in csp
        assert "worker-src 'self' blob:" in csp

        # WebSocket schemes are always included for Colyseus / event streams.
        assert "ws:" in csp
        assert "wss:" in csp

    @pytest.mark.asyncio
    async def test_csp_includes_cors_origins(self) -> None:
        """connect-src includes every configured CORS origin."""
        origins = [
            "http://localhost:4301",
            "http://localhost:4302",
            "https://app.example.com",
        ]
        app = _make_app(cors_origins=origins)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/ping")

        csp = resp.headers["content-security-policy"]
        for origin in origins:
            assert origin in csp, f"Expected {origin!r} in CSP connect-src"

    @pytest.mark.asyncio
    async def test_csp_extra_sources(self) -> None:
        """csp_extra_sources setting adds additional domains to connect-src."""
        extra = "https://analytics.example.com https://cdn.example.com"
        app = _make_app(cors_origins=["http://localhost:4301"], csp_extra_sources=extra)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/ping")

        csp = resp.headers["content-security-policy"]
        assert "https://analytics.example.com" in csp
        assert "https://cdn.example.com" in csp
        # CORS origin is still present
        assert "http://localhost:4301" in csp

    @pytest.mark.asyncio
    async def test_csp_no_duplicate_sources(self) -> None:
        """Duplicate origins are de-duplicated in the CSP connect-src."""
        origins = ["http://localhost:4301", "http://localhost:4301"]
        app = _make_app(cors_origins=origins)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/ping")

        csp = resp.headers["content-security-policy"]
        # Extract the connect-src directive value
        for directive in csp.split(";"):
            directive = directive.strip()
            if directive.startswith("connect-src"):
                parts = directive.split()
                # Count how many times the origin appears (should be 1)
                count = parts.count("http://localhost:4301")
                assert count == 1, f"Origin duplicated {count} times in connect-src: {directive}"
                break
        else:
            pytest.fail("connect-src directive not found in CSP")

    @pytest.mark.asyncio
    async def test_csp_empty_origins_still_has_self_and_ws(self) -> None:
        """With no CORS origins the CSP still includes 'self', ws:, and wss:."""
        app = _make_app(cors_origins=[])
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/ping")

        csp = resp.headers["content-security-policy"]
        assert "connect-src 'self' ws: wss:" in csp
