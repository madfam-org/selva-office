"""Platform administration is read from the verified ``is_admin`` claim.

Janua publishes a user's organization membership roles in ``roles`` as bare
strings (``owner``, ``admin``, ``member`` or custom organization roles). These
tests pin that platform-level routes read the ``is_admin`` claim or the
``selva:admin`` application role instead, that organization administration is
scoped to the token's own organization, and that service-credential role names
are not read from a bearer token.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from nexus_api import auth as _auth_mod
from nexus_api.config import Settings

ORG_ADMIN: dict[str, Any] = {
    "sub": "org-admin",
    "roles": ["admin", "member"],
    "org_roles": ["admin"],
    "org_id": "tenant-a",
    "email": "org-admin@example.com",
    "is_admin": False,
}
PLATFORM_ADMIN: dict[str, Any] = {
    "sub": "platform-admin",
    "roles": ["member"],
    "org_roles": ["member"],
    "org_id": "tenant-a",
    "email": "platform-admin@example.com",
    "is_admin": True,
}
PLATFORM_ORG = "platform-org"
SELVA_ADMIN: dict[str, Any] = {
    "sub": "selva-admin",
    "roles": ["member", "selva:admin"],
    "org_roles": ["member"],
    "org_id": PLATFORM_ORG,
    "email": "selva-admin@example.com",
    "is_admin": False,
}


@pytest.fixture(autouse=True)
def _platform_org(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_ORG_ID", PLATFORM_ORG)


def _settings() -> MagicMock:
    s = MagicMock(spec=Settings)
    s.environment = "staging"
    s.dev_auth_bypass = False
    s.worker_api_token = "wt-secret"
    s.janua_issuer_url = "https://janua.example.com"
    s.janua_client_id = "client-xyz"
    return s


async def _user_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    request = MagicMock()
    request.headers = {}
    with patch.object(_auth_mod, "verify_jwt", AsyncMock(return_value=payload)):
        return await _auth_mod.get_current_user(
            request=request,
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="jwt"),
            settings=_settings(),
        )


# ---------------------------------------------------------------------------
# get_current_user: claims read from the verified token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVerifiedTokenMapping:
    @pytest.mark.parametrize(
        ("claim", "expected"),
        [(True, True), (False, False), ("true", False), (1, False), (None, False)],
    )
    async def test_is_admin_is_exactly_the_boolean_claim(self, claim: Any, expected: bool) -> None:
        payload: dict[str, Any] = {"sub": "u", "org_id": "o", "roles": ["admin"]}
        if claim is not None:
            payload["is_admin"] = claim
        user = await _user_from_payload(payload)
        assert user["is_admin"] is expected
        assert _auth_mod.is_platform_admin(user) is expected

    async def test_org_roles_come_from_the_namespaced_claim(self) -> None:
        user = await _user_from_payload(
            {"sub": "u", "org_id": "o", "roles": ["admin"], "madfam_org_roles": ["member"]}
        )
        assert user["org_roles"] == ["member"]
        assert _auth_mod.is_org_admin(user) is False

    async def test_service_credential_role_names_are_not_read_from_bearer_tokens(self) -> None:
        user = await _user_from_payload(
            {
                "sub": "u",
                "org_id": "o",
                "roles": ["service", "worker", "platform", "member", "guest"],
            }
        )
        assert user["roles"] == ["member", "guest"]

    async def test_worker_shared_secret_keeps_service_roles(self) -> None:
        request = MagicMock()
        request.headers = {}
        user = await _auth_mod.get_current_user(
            request=request,
            credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="wt-secret"),
            settings=_settings(),
        )
        assert "service" in user["roles"]
        assert user["is_admin"] is False


# ---------------------------------------------------------------------------
# Predicates and dependencies
# ---------------------------------------------------------------------------


class TestPredicates:
    def test_platform_admin_claim(self) -> None:
        assert _auth_mod.is_platform_admin(PLATFORM_ADMIN) is True

    def test_selva_admin_application_role_in_platform_org(self) -> None:
        assert _auth_mod.is_platform_admin(SELVA_ADMIN) is True

    def test_selva_admin_application_role_outside_platform_org(self) -> None:
        assert _auth_mod.is_platform_admin({**SELVA_ADMIN, "org_id": "tenant-a"}) is False
        assert _auth_mod.is_platform_admin({**SELVA_ADMIN, "org_id": None}) is False

    def test_selva_admin_application_role_without_platform_org_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PLATFORM_ORG_ID", raising=False)
        assert _auth_mod.is_platform_admin(SELVA_ADMIN) is False

    def test_organization_admin_is_not_platform_admin(self) -> None:
        assert _auth_mod.is_platform_admin(ORG_ADMIN) is False

    @pytest.mark.parametrize(
        "roles",
        [
            ["admin"],
            ["superadmin"],
            ["platform"],
            ["platform_admin"],
            ["platform-admin"],
            ["Admin"],
        ],
    )
    def test_custom_roles_named_like_admin_are_not_platform_admin(self, roles: list[str]) -> None:
        assert _auth_mod.is_platform_admin({"sub": "u", "roles": roles}) is False

    def test_org_admin_requires_role_in_own_org(self) -> None:
        assert _auth_mod.is_org_admin(ORG_ADMIN) is True

    def test_org_admin_requires_an_org_id(self) -> None:
        assert _auth_mod.is_org_admin({**ORG_ADMIN, "org_id": None}) is False

    def test_admin_elsewhere_is_not_org_admin_here(self) -> None:
        """``roles`` merges every organization; only the own-org role counts."""
        user = {**ORG_ADMIN, "org_roles": ["member"]}
        assert _auth_mod.is_org_admin(user) is False


@pytest.mark.asyncio
class TestDependencies:
    async def test_require_platform_admin_refuses_org_admin(self) -> None:
        with pytest.raises(HTTPException) as exc:
            await _auth_mod.require_platform_admin(user=ORG_ADMIN)
        assert exc.value.status_code == 403

    async def test_require_platform_admin_allows_claim_and_app_role(self) -> None:
        assert await _auth_mod.require_platform_admin(user=PLATFORM_ADMIN) is PLATFORM_ADMIN
        assert await _auth_mod.require_platform_admin(user=SELVA_ADMIN) is SELVA_ADMIN

    async def test_require_org_admin_allows_own_org_admin_and_platform_admin(self) -> None:
        assert await _auth_mod.require_org_admin(user=ORG_ADMIN) is ORG_ADMIN
        assert await _auth_mod.require_org_admin(user=PLATFORM_ADMIN) is PLATFORM_ADMIN

    async def test_require_org_admin_refuses_member(self) -> None:
        member = {**ORG_ADMIN, "roles": ["admin"], "org_roles": ["member"]}
        with pytest.raises(HTTPException) as exc:
            await _auth_mod.require_org_admin(user=member)
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _as_user(user: dict[str, Any]) -> Any:
    from nexus_api.auth import get_current_user
    from nexus_api.main import app

    async def _user() -> dict[str, Any]:
        return user

    app.dependency_overrides[get_current_user] = _user
    return app


PLATFORM_ROUTES = [
    ("GET", "/api/v1/admin/users", None),
    ("GET", "/api/v1/hitl/confidence", None),
    ("GET", "/api/v1/hitl/decisions", None),
    ("GET", "/api/v1/providers/balance", None),
    ("GET", "/api/v1/campaigns/authorizations/pending", None),
    ("POST", "/api/v1/checkpoints/run-1/plan/rollback", None),
    ("GET", "/api/v1/command-approvals/pending", None),
    ("GET", "/api/v1/trajectories", None),
    ("GET", "/api/v1/checkpoints/run-1", None),
    ("POST", "/api/v1/swarms/tasks/reap-stale", None),
    ("POST", "/api/v1/approvals/bulk-expire", None),
]


@pytest.mark.asyncio
class TestPlatformRoutes:
    @pytest.mark.parametrize(("method", "path", "body"), PLATFORM_ROUTES)
    async def test_organization_admin_is_refused(
        self, client: httpx.AsyncClient, method: str, path: str, body: Any
    ) -> None:
        app = _as_user(ORG_ADMIN)
        try:
            resp = await client.request(method, path, json=body, headers={"Authorization": "x"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403, (path, resp.text)

    @pytest.mark.parametrize(
        "path",
        ["/api/v1/trajectories", "/api/v1/command-approvals/pending", "/api/v1/checkpoints/run-1"],
    )
    async def test_cleanroom_role_alone_is_refused(
        self, client: httpx.AsyncClient, path: str
    ) -> None:
        app = _as_user({"sub": "c", "roles": ["enterprise-cleanroom"], "org_id": "tenant-a"})
        try:
            resp = await client.get(path, headers={"Authorization": "x"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403

    @pytest.mark.parametrize("roles", [["superadmin"], ["platform"], ["platform_admin"]])
    async def test_custom_role_named_like_admin_is_refused(
        self, client: httpx.AsyncClient, roles: list[str]
    ) -> None:
        app = _as_user({"sub": "u", "roles": roles, "org_id": "tenant-a"})
        try:
            resp = await client.get("/api/v1/admin/users", headers={"Authorization": "x"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403

    @pytest.mark.parametrize("user", [PLATFORM_ADMIN, SELVA_ADMIN])
    async def test_platform_admin_is_allowed(
        self, client: httpx.AsyncClient, user: dict[str, Any]
    ) -> None:
        app = _as_user(user)
        try:
            resp = await client.get("/api/v1/hitl/confidence", headers={"Authorization": "x"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
class TestOwnOrganizationRoutes:
    async def test_org_admin_updates_own_org_branding(self, client: httpx.AsyncClient) -> None:
        app = _as_user(ORG_ADMIN)
        try:
            resp = await client.patch(
                "/api/v1/tenants/me/branding",
                json={"brand_name": "Tenant A"},
                headers={"Authorization": "x"},
            )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200, resp.text
        assert resp.json()["brand_name"] == "Tenant A"

    async def test_admin_of_another_org_is_refused_on_own_org_branding(
        self, client: httpx.AsyncClient
    ) -> None:
        """``admin`` in the merged ``roles`` list is not admin of the token's org."""
        app = _as_user({**ORG_ADMIN, "org_roles": ["member"]})
        try:
            resp = await client.patch(
                "/api/v1/tenants/me/branding",
                json={"brand_name": "Tenant A"},
                headers={"Authorization": "x"},
            )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403
