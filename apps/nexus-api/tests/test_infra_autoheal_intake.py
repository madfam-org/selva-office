"""POST /api/v1/infra/autoheal/alertmanager: off by default, bearer-gated, queues only.

The payload is the recorded 2026-10-24 CNPG replay from packages/autoheal.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fakeredis.aioredis
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from selva_autoheal.config import AutohealConfig
from selva_autoheal.store import QUEUE_KEY, IncidentStore

from nexus_api.routers import infra_autoheal

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "packages/autoheal/tests/fixtures/cnpg_operator_ingress_2026-10-24.alertmanager.json"
)
SECRET = "webhook-secret-placeholder"
URL = "/api/v1/infra/autoheal/alertmanager"


def _cfg(enabled: bool = True) -> AutohealConfig:
    return AutohealConfig(
        enabled=enabled,
        incident_cap_usd=1.0,
        daily_cap_usd=5.0,
        alertnames=("CNPGInstanceStatusUnreachable",),
    )


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _app(monkeypatch: pytest.MonkeyPatch, redis: Any, *, enabled: bool, secret: str) -> FastAPI:
    app = FastAPI()
    app.include_router(infra_autoheal.router, prefix="/api/v1")
    cfg = _cfg(enabled)
    app.dependency_overrides[infra_autoheal.get_autoheal_config] = lambda: cfg

    async def store(c: AutohealConfig) -> IncidentStore:
        return IncidentStore(redis, c)

    monkeypatch.setattr(infra_autoheal, "get_autoheal_store", store)
    monkeypatch.setattr(
        infra_autoheal,
        "get_settings",
        lambda: SimpleNamespace(infra_autoheal_webhook_secret=secret),
    )
    return app


async def _post(app: FastAPI, body: Any, token: str | None = SECRET) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(URL, json=body, headers=headers)


@pytest.fixture
def payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


async def test_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch, redis: Any, payload: dict[str, Any]
) -> None:
    resp = await _post(_app(monkeypatch, redis, enabled=False, secret=SECRET), payload)
    assert resp.status_code == 503 and resp.json()["detail"] == "autoheal_disabled"
    assert await redis.llen(QUEUE_KEY) == 0


async def test_unset_secret_is_503(
    monkeypatch: pytest.MonkeyPatch, redis: Any, payload: dict[str, Any]
) -> None:
    resp = await _post(_app(monkeypatch, redis, enabled=True, secret=""), payload)
    assert resp.status_code == 503


async def test_wrong_or_missing_token_is_401(
    monkeypatch: pytest.MonkeyPatch, redis: Any, payload: dict[str, Any]
) -> None:
    app = _app(monkeypatch, redis, enabled=True, secret=SECRET)
    assert (await _post(app, payload, token="nope")).status_code == 401
    assert (await _post(app, payload, token=None)).status_code == 401
    assert await redis.llen(QUEUE_KEY) == 0


async def test_queues_the_incident_once(
    monkeypatch: pytest.MonkeyPatch, redis: Any, payload: dict[str, Any]
) -> None:
    app = _app(monkeypatch, redis, enabled=True, secret=SECRET)
    first = await _post(app, payload)
    again = await _post(app, payload)
    assert first.status_code == 202 and first.json()["incident"]["decision"] == "queued"
    assert again.json()["incident"]["decision"] == "duplicate"
    assert await redis.llen(QUEUE_KEY) == 1


async def test_invalid_payload_is_422(monkeypatch: pytest.MonkeyPatch, redis: Any) -> None:
    resp = await _post(_app(monkeypatch, redis, enabled=True, secret=SECRET), {"status": "x"})
    assert resp.status_code == 422


def test_route_is_not_in_the_public_schema() -> None:
    app = FastAPI()
    app.include_router(infra_autoheal.router, prefix="/api/v1")
    assert URL not in app.openapi().get("paths", {})
