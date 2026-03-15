"""Tests for guest user permission restrictions (PR 4.1)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus_api.auth import get_current_user, require_non_guest

# ---------------------------------------------------------------------------
# Minimal app fixture
# ---------------------------------------------------------------------------

def _create_test_app() -> FastAPI:
    from fastapi import APIRouter, Depends

    app = FastAPI()
    router = APIRouter()

    @router.get("/public")
    async def public_endpoint(
        user: dict = Depends(get_current_user),  # noqa: B008
    ) -> dict:
        return {"ok": True, "user": user.get("sub")}

    @router.post(
        "/protected",
        dependencies=[Depends(require_non_guest)],
    )
    async def protected_endpoint() -> dict:
        return {"ok": True}

    app.include_router(router, prefix="/test")
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guest_user() -> dict:
    return {
        "sub": "guest-00000001",
        "roles": ["guest"],
        "org_id": "test-org",
        "email": None,
    }


def _regular_user() -> dict:
    return {
        "sub": "user-00000001",
        "roles": ["tactician"],
        "org_id": "test-org",
        "email": "user@test.com",
    }


def _admin_user() -> dict:
    return {
        "sub": "admin-00000001",
        "roles": ["admin", "tactician"],
        "org_id": "test-org",
        "email": "admin@test.com",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRequireNonGuest:
    """Unit tests for the require_non_guest dependency."""

    @pytest.mark.asyncio
    async def test_allows_regular_user(self) -> None:
        user = _regular_user()
        result = await require_non_guest(user)
        assert result["sub"] == "user-00000001"

    @pytest.mark.asyncio
    async def test_allows_admin_user(self) -> None:
        user = _admin_user()
        result = await require_non_guest(user)
        assert result["sub"] == "admin-00000001"

    @pytest.mark.asyncio
    async def test_rejects_guest_user(self) -> None:
        from fastapi import HTTPException

        user = _guest_user()
        with pytest.raises(HTTPException) as exc_info:
            await require_non_guest(user)
        assert exc_info.value.status_code == 403
        assert "Guest" in exc_info.value.detail


class TestGuestEndpointAccess:
    """Integration tests verifying guest restrictions on endpoint decorators."""

    def test_guest_can_access_public_get(self) -> None:
        app = _create_test_app()
        app.dependency_overrides[get_current_user] = lambda: _guest_user()
        client = TestClient(app)
        resp = client.get("/test/public")
        assert resp.status_code == 200

    def test_guest_blocked_from_protected_post(self) -> None:
        app = _create_test_app()
        app.dependency_overrides[get_current_user] = lambda: _guest_user()
        client = TestClient(app)
        resp = client.post("/test/protected")
        assert resp.status_code == 403
        assert "Guest" in resp.json()["detail"]

    def test_regular_user_can_access_protected_post(self) -> None:
        app = _create_test_app()
        app.dependency_overrides[get_current_user] = lambda: _regular_user()
        client = TestClient(app)
        resp = client.post("/test/protected")
        assert resp.status_code == 200

    def test_admin_can_access_protected_post(self) -> None:
        app = _create_test_app()
        app.dependency_overrides[get_current_user] = lambda: _admin_user()
        client = TestClient(app)
        resp = client.post("/test/protected")
        assert resp.status_code == 200
