"""Tests for the secret-access audit emitter."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from selva_tools._audit import emit_secret_access_event


@pytest.mark.asyncio
class TestEmitSecretAccessEvent:
    async def test_skips_when_nexus_url_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("NEXUS_API_URL", raising=False)
        with patch("httpx.AsyncClient") as mock_client:
            await emit_secret_access_event(
                operation="read", key="PORKBUN_KEY", namespace="autoswarm", success=True
            )
            mock_client.assert_not_called()

    async def test_posts_expected_body_shape(self, monkeypatch) -> None:
        monkeypatch.setenv("NEXUS_API_URL", "http://nexus.test")
        monkeypatch.setenv("WORKER_API_TOKEN", "wa-test")

        captured: dict = {}
        mock_post = AsyncMock()

        class FakeClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def post(self, url, *, json, headers):
                captured["url"] = url
                captured["body"] = json
                captured["headers"] = headers
                return MagicMock(status_code=201)

        with patch("httpx.AsyncClient", return_value=FakeClient()):
            await emit_secret_access_event(
                operation="read",
                key="PORKBUN_API_KEY",
                namespace="autoswarm",
                success=True,
            )

        assert captured["url"] == "http://nexus.test/api/v1/events/"
        assert captured["headers"]["Authorization"] == "Bearer wa-test"
        assert captured["body"]["event_type"] == "secret_read"
        assert captured["body"]["event_category"] == "secret_management"
        assert captured["body"]["payload"]["key"] == "PORKBUN_API_KEY"
        assert captured["body"]["payload"]["namespace"] == "autoswarm"
        assert captured["body"]["payload"]["success"] is True
        # Critical: the actual secret value must NEVER be in the body.
        serialised = json.dumps(captured["body"])
        for forbidden in ("value", "VALUE", "secret_value"):
            assert forbidden not in captured["body"].get("payload", {})

    async def test_failure_event_includes_truncated_error(self, monkeypatch) -> None:
        monkeypatch.setenv("NEXUS_API_URL", "http://nexus.test")
        captured: dict = {}

        class FakeClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def post(self, url, *, json, headers):
                captured["body"] = json
                return MagicMock(status_code=201)

        long_error = "x" * 1000
        with patch("httpx.AsyncClient", return_value=FakeClient()):
            await emit_secret_access_event(
                operation="read",
                key="K",
                namespace="ns",
                success=False,
                error_message=long_error,
            )
        assert len(captured["body"]["error_message"]) == 500

    async def test_http_failures_never_raise(self, monkeypatch) -> None:
        """Audit emission must be pure best-effort. A down nexus-api
        can't block a Vault operation from returning its result."""
        monkeypatch.setenv("NEXUS_API_URL", "http://nexus.test")

        class BrokenClient:
            async def __aenter__(self):
                raise RuntimeError("network down")
            async def __aexit__(self, *args):
                pass

        with patch("httpx.AsyncClient", return_value=BrokenClient()):
            # Should not raise.
            await emit_secret_access_event(
                operation="write", key="K", namespace="ns", success=True
            )

    async def test_agent_id_populated_from_env_when_set(self, monkeypatch) -> None:
        monkeypatch.setenv("NEXUS_API_URL", "http://nexus.test")
        monkeypatch.setenv("SELVA_AGENT_ID", "agent-heraldo")

        captured: dict = {}

        class FakeClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def post(self, url, *, json, headers):
                captured["body"] = json
                return MagicMock(status_code=201)

        with patch("httpx.AsyncClient", return_value=FakeClient()):
            await emit_secret_access_event(
                operation="read", key="K", namespace="ns", success=True
            )
        assert captured["body"]["agent_id"] == "agent-heraldo"

    async def test_extra_merged_into_payload(self, monkeypatch) -> None:
        monkeypatch.setenv("NEXUS_API_URL", "http://nexus.test")
        captured: dict = {}

        class FakeClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def post(self, url, *, json, headers):
                captured["body"] = json
                return MagicMock(status_code=201)

        with patch("httpx.AsyncClient", return_value=FakeClient()):
            await emit_secret_access_event(
                operation="rotate",
                key="K",
                namespace="ns",
                success=True,
                extra={"correlation_id": "rot-abc"},
            )
        assert captured["body"]["payload"]["correlation_id"] == "rot-abc"
