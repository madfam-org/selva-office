"""Tests for the revenue-loop probe router (A.7).

Covers the four endpoints:
    POST /api/v1/probe/draft         — dry-run drafter
    POST /api/v1/probe/email/send    — dry-run send with contract validation
    POST /api/v1/probe/runs          — report persistence
    GET  /api/v1/probe/latest-run    — public read

Auth, happy-path, dry-run enforcement, HTML sanitisation, and Redis
persistence are exercised. The Redis client is mocked per-test so the
suite never touches a live Redis.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nexus_api import config as _cfg_mod

# The test token — set on the patched settings instance the conftest already
# installed. We mutate the existing singleton so every request sees it.
_PROBE_TOKEN = "probe-test-secret"


@pytest.fixture(autouse=True)
def _set_probe_token() -> None:
    """Install a probe token on the shared test settings for every probe test."""
    settings = _cfg_mod.get_settings()
    settings.nexus_probe_token = _PROBE_TOKEN
    settings.email_from = "Selva <noreply@selva.town>"


def _probe_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_PROBE_TOKEN}",
        "X-CSRF-Token": "test-csrf-token-fixed",
    }


# ============================================================================
# POST /api/v1/probe/draft
# ============================================================================


@pytest.mark.asyncio
class TestProbeDraft:
    async def test_draft_requires_bearer_token(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/probe/draft",
            json={"correlation_id": "probe-c1", "lead_id": "lead-1", "dry_run": True},
        )
        assert resp.status_code == 401

    async def test_draft_rejects_wrong_token(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/probe/draft",
            json={"correlation_id": "probe-c1", "lead_id": "lead-1", "dry_run": True},
            headers={
                "Authorization": "Bearer not-the-right-token",
                "X-CSRF-Token": "test-csrf-token-fixed",
            },
        )
        assert resp.status_code == 401

    async def test_draft_returns_deterministic_body(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/probe/draft",
            json={"correlation_id": "probe-c1", "lead_id": "lead-abc123", "dry_run": True},
            headers=_probe_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Non-empty, non-sentinel draft — matches the probe's assertion set.
        assert body["draft"]
        assert not body["draft"].startswith("[LLM unavailable")
        assert "lead-abc123" in body["draft"]
        assert body["provider"] == "probe-dry"
        assert body["token_count"] > 0

    async def test_draft_rejects_live_mode(self, client: httpx.AsyncClient) -> None:
        """The dry-run guard prevents accidental billing from the probe path."""
        resp = await client.post(
            "/api/v1/probe/draft",
            json={"correlation_id": "probe-c1", "lead_id": "lead-1", "dry_run": False},
            headers=_probe_headers(),
        )
        assert resp.status_code == 422

    async def test_draft_503_when_token_not_configured(
        self, client: httpx.AsyncClient
    ) -> None:
        settings = _cfg_mod.get_settings()
        original = settings.nexus_probe_token
        settings.nexus_probe_token = ""
        try:
            resp = await client.post(
                "/api/v1/probe/draft",
                json={"correlation_id": "probe-c1", "lead_id": "lead-1", "dry_run": True},
                headers=_probe_headers(),
            )
            assert resp.status_code == 503
        finally:
            settings.nexus_probe_token = original


# ============================================================================
# POST /api/v1/probe/email/send
# ============================================================================


@pytest.mark.asyncio
class TestProbeEmailSend:
    async def test_send_requires_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/probe/email/send",
            json={
                "correlation_id": "probe-c1",
                "lead_id": "lead-1",
                "body": "<p>hi</p>",
                "dry_run": True,
            },
        )
        assert resp.status_code == 401

    async def test_send_returns_full_contract(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/probe/email/send",
            json={
                "correlation_id": "probe-c1",
                "lead_id": "lead-1",
                "body": "<p>Hello world</p>",
                "dry_run": True,
            },
            headers=_probe_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Contract fields the probe asserts on:
        assert body["list_unsubscribe_header_present"] is True
        assert body["sanitized_html"] == "<p>Hello world</p>"
        assert body["from_address"] == "Selva <noreply@selva.town>"
        assert body["provider"] == "resend-dry"
        assert body["message_id"].startswith("probe-msg-")

    async def test_send_sanitizes_script_tags(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/probe/email/send",
            json={
                "correlation_id": "probe-c1",
                "lead_id": "lead-1",
                "body": "<p>Hi</p><script>alert('xss')</script><p>bye</p>",
                "dry_run": True,
            },
            headers=_probe_headers(),
        )
        assert resp.status_code == 200
        sanitized = resp.json()["sanitized_html"]
        assert "<script" not in sanitized.lower()
        assert "alert" not in sanitized
        assert "<p>Hi</p>" in sanitized
        assert "<p>bye</p>" in sanitized

    async def test_send_strips_on_handlers_and_js_urls(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/v1/probe/email/send",
            json={
                "correlation_id": "probe-c1",
                "lead_id": "lead-1",
                "body": '<a href="javascript:void(0)" onclick="steal()">go</a>',
                "dry_run": True,
            },
            headers=_probe_headers(),
        )
        assert resp.status_code == 200
        sanitized = resp.json()["sanitized_html"]
        assert "onclick" not in sanitized.lower()
        assert "javascript:" not in sanitized.lower()

    async def test_send_rejects_live_mode(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/probe/email/send",
            json={
                "correlation_id": "probe-c1",
                "lead_id": "lead-1",
                "body": "<p>x</p>",
                "dry_run": False,
            },
            headers=_probe_headers(),
        )
        assert resp.status_code == 422


# ============================================================================
# POST /api/v1/probe/runs  +  GET /api/v1/probe/latest-run
# ============================================================================


def _sample_run(correlation_id: str = "probe-upload-1", *, ok: bool = True) -> dict:
    return {
        "correlation_id": correlation_id,
        "dry_run": True,
        "started_at": 1_800_000_000.0,
        "finished_at": 1_800_000_001.5,
        "duration_ms": 1500.0,
        "ok": ok,
        "fail_count": 0 if ok else 1,
        "stages": [
            {
                "name": "crm.hot_lead",
                "status": "passed",
                "duration_ms": 120.0,
                "detail": None,
                "facts": {"lead_id": "lead-xyz"},
            },
            {
                "name": "drafter.first_touch",
                "status": "dry_run",
                "duration_ms": 45.2,
                "detail": None,
                "facts": {"provider": "probe-dry", "tokens": 18},
            },
        ],
    }


@pytest.mark.asyncio
class TestProbeRunUpload:
    async def test_upload_requires_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/v1/probe/runs", json=_sample_run())
        assert resp.status_code == 401

    async def test_upload_persists_to_redis(self, client: httpx.AsyncClient) -> None:
        """The report is stringified and pushed to both keys."""
        mock_client = MagicMock()
        mock_client.set = AsyncMock()
        mock_client.lpush = AsyncMock()
        mock_client.ltrim = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.client = AsyncMock(return_value=mock_client)

        with patch(
            "nexus_api.routers.probe.get_redis_pool", return_value=mock_pool
        ):
            resp = await client.post(
                "/api/v1/probe/runs",
                json=_sample_run("probe-upload-abc"),
                headers=_probe_headers(),
            )

        assert resp.status_code == 202
        body = resp.json()
        assert body["ok"] is True
        assert body["persisted"] is True
        assert body["correlation_id"] == "probe-upload-abc"
        mock_client.set.assert_awaited_once()
        args = mock_client.set.await_args.args
        assert args[0] == "selva:probe:latest-run"
        # The stored payload should be valid JSON and include our received_at.
        stored = json.loads(args[1])
        assert stored["correlation_id"] == "probe-upload-abc"
        assert "received_at" in stored
        mock_client.lpush.assert_awaited_once()
        mock_client.ltrim.assert_awaited_once()
        # Cap history at most 50 entries.
        ltrim_args = mock_client.ltrim.await_args.args
        assert ltrim_args == ("selva:probe:history", 0, 49)

    async def test_upload_survives_redis_failure(
        self, client: httpx.AsyncClient
    ) -> None:
        """Redis outage must not cause the probe's upload step to fail."""
        mock_pool = MagicMock()
        mock_pool.client = AsyncMock(side_effect=RuntimeError("redis down"))

        with patch(
            "nexus_api.routers.probe.get_redis_pool", return_value=mock_pool
        ):
            resp = await client.post(
                "/api/v1/probe/runs",
                json=_sample_run(),
                headers=_probe_headers(),
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["ok"] is False
        assert body["persisted"] is False


@pytest.mark.asyncio
class TestProbeLatestRun:
    async def test_latest_run_returns_null_when_empty(
        self, client: httpx.AsyncClient
    ) -> None:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.client = AsyncMock(return_value=mock_client)

        with patch(
            "nexus_api.routers.probe.get_redis_pool", return_value=mock_pool
        ):
            resp = await client.get("/api/v1/probe/latest-run")

        assert resp.status_code == 200
        assert resp.json() is None

    async def test_latest_run_returns_stored_payload(
        self, client: httpx.AsyncClient
    ) -> None:
        stored = {
            **_sample_run("probe-latest-xyz"),
            "received_at": 1_800_000_002.0,
        }
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=json.dumps(stored))
        mock_pool = MagicMock()
        mock_pool.client = AsyncMock(return_value=mock_client)

        with patch(
            "nexus_api.routers.probe.get_redis_pool", return_value=mock_pool
        ):
            resp = await client.get("/api/v1/probe/latest-run")

        assert resp.status_code == 200
        body = resp.json()
        assert body is not None
        assert body["correlation_id"] == "probe-latest-xyz"
        assert body["received_at"] == 1_800_000_002.0
        assert len(body["stages"]) == 2

    async def test_latest_run_is_public(self, client: httpx.AsyncClient) -> None:
        """No Authorization header should still succeed."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.client = AsyncMock(return_value=mock_client)

        with patch(
            "nexus_api.routers.probe.get_redis_pool", return_value=mock_pool
        ):
            resp = await client.get("/api/v1/probe/latest-run")
        assert resp.status_code == 200

    async def test_latest_run_survives_redis_failure(
        self, client: httpx.AsyncClient
    ) -> None:
        mock_pool = MagicMock()
        mock_pool.client = AsyncMock(side_effect=RuntimeError("redis down"))

        with patch(
            "nexus_api.routers.probe.get_redis_pool", return_value=mock_pool
        ):
            resp = await client.get("/api/v1/probe/latest-run")

        # Fail-soft: return 200 null rather than 500 so the status page
        # renders the empty state instead of bricking.
        assert resp.status_code == 200
        assert resp.json() is None


# ============================================================================
# GET /api/v1/probe/history
# ============================================================================


@pytest.mark.asyncio
class TestProbeHistory:
    async def test_history_caps_limit_at_50(self, client: httpx.AsyncClient) -> None:
        mock_client = MagicMock()
        mock_client.lrange = AsyncMock(return_value=[])
        mock_pool = MagicMock()
        mock_pool.client = AsyncMock(return_value=mock_client)

        with patch(
            "nexus_api.routers.probe.get_redis_pool", return_value=mock_pool
        ):
            resp = await client.get("/api/v1/probe/history?limit=500")

        assert resp.status_code == 200
        mock_client.lrange.assert_awaited_once_with("selva:probe:history", 0, 49)

    async def test_history_returns_parsed_entries(
        self, client: httpx.AsyncClient
    ) -> None:
        stored = [
            json.dumps({**_sample_run(f"probe-{i}"), "received_at": 1_800_000_000.0 + i})
            for i in range(3)
        ]
        mock_client = MagicMock()
        mock_client.lrange = AsyncMock(return_value=stored)
        mock_pool = MagicMock()
        mock_pool.client = AsyncMock(return_value=mock_client)

        with patch(
            "nexus_api.routers.probe.get_redis_pool", return_value=mock_pool
        ):
            resp = await client.get("/api/v1/probe/history?limit=10")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3
        assert [r["correlation_id"] for r in body] == ["probe-0", "probe-1", "probe-2"]
