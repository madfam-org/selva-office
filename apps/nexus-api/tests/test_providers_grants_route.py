"""GET /api/v1/providers/grants — platform administrators only, C2 fields."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import fakeredis.aioredis
import httpx
import pytest

from madfam_inference import grants as g


@pytest.fixture
def grant_guard() -> Iterator[g.GrantGuard]:
    book = g.parse_grants(
        json.dumps(
            {
                "grants": [
                    {
                        "id": "example-grant",
                        "provider": "anthropic",
                        "amount_usd": 100.0,
                        "safety_margin_usd": 5.0,
                        "starts_at": "2030-01-01T00:00:00Z",
                        "expires_at": "2030-01-02T00:00:00Z",
                        "allowed_orgs": ["madfam"],
                    }
                ]
            }
        )
    )
    state = g.GrantConfigState(grants=tuple(book.grants), source="test")
    guard = g.GrantGuard(
        config_loader=lambda: state,
        required=("anthropic",),
        meter=g.GrantMeter(fakeredis.aioredis.FakeRedis(decode_responses=True)),
        now_fn=lambda: datetime(2030, 1, 1, 12, tzinfo=UTC),
    )
    g.set_default_guard(guard)
    yield guard
    g.set_default_guard(None)


def _as_user(user: dict[str, Any]) -> Any:
    from nexus_api.auth import get_current_user
    from nexus_api.main import app

    async def _user() -> dict[str, Any]:
        return user

    app.dependency_overrides[get_current_user] = _user
    return app


@pytest.mark.asyncio
class TestProviderGrantsRoute:
    async def test_platform_role_sees_c2_fields(
        self, client: httpx.AsyncClient, grant_guard: g.GrantGuard
    ) -> None:
        app = _as_user({"sub": "u-1", "roles": ["platform"], "org_id": "any-org"})
        try:
            resp = await client.get("/api/v1/providers/grants", headers={"Authorization": "x"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        body = resp.json()
        assert body["required_for"] == ["anthropic"]
        [grant] = body["grants"]
        assert grant["id"] == "example-grant"
        assert grant["remaining_usd"] == pytest.approx(95.0)
        assert grant["pace_status"] == "behind"
        assert grant["meter_ok"] is True

    async def test_admin_in_platform_org_allowed(
        self,
        client: httpx.AsyncClient,
        grant_guard: g.GrantGuard,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PLATFORM_ORG_ID", "madfam")
        app = _as_user({"sub": "u-1", "roles": ["admin"], "org_id": "madfam"})
        try:
            resp = await client.get("/api/v1/providers/grants", headers={"Authorization": "x"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200

    async def test_tenant_admin_refused(
        self,
        client: httpx.AsyncClient,
        grant_guard: g.GrantGuard,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PLATFORM_ORG_ID", "madfam")
        app = _as_user({"sub": "u-2", "roles": ["admin"], "org_id": "tenant-org"})
        try:
            resp = await client.get("/api/v1/providers/grants", headers={"Authorization": "x"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403

    async def test_viewer_refused(
        self, client: httpx.AsyncClient, grant_guard: g.GrantGuard
    ) -> None:
        app = _as_user({"sub": "u-3", "roles": ["viewer"], "org_id": "madfam"})
        try:
            resp = await client.get("/api/v1/providers/grants", headers={"Authorization": "x"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_prometheus_grant_gauges(grant_guard: g.GrantGuard) -> None:
    from prometheus_client import REGISTRY

    from nexus_api.operational_metrics import _refresh_provider_grant_gauges

    await _refresh_provider_grant_gauges()
    labels = {"grant": "example-grant"}
    assert REGISTRY.get_sample_value("selva_provider_grant_remaining_usd", labels) == 95.0
    assert REGISTRY.get_sample_value("selva_provider_grant_spent_usd", labels) == 0.0
    assert (
        REGISTRY.get_sample_value("selva_provider_grant_seconds_to_expiry", labels) == 12 * 3600
    )
