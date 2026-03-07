"""Tests for the gateway webhook endpoints.

Tests the GitHub webhook handler including signature verification,
event mapping, and task creation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest


class TestGitHubWebhookPing:
    """Tests for ping events."""

    async def test_ping_returns_pong(self, client: httpx.AsyncClient) -> None:
        """GitHub ping event returns pong."""
        resp = await client.post(
            "/api/v1/gateway/github",
            content=b"{}",
            headers={"X-GitHub-Event": "ping"},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "pong"


class TestGitHubWebhookSignature:
    """Tests for HMAC-SHA256 signature verification."""

    async def test_rejects_invalid_signature(self, client: httpx.AsyncClient) -> None:
        """Invalid signature returns 401 when webhook secret is set."""
        from nexus_api.config import get_settings

        settings = get_settings()
        original_secret = settings.github_webhook_secret
        settings.github_webhook_secret = "test-secret"

        try:
            resp = await client.post(
                "/api/v1/gateway/github",
                content=b'{"action":"opened"}',
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": "sha256=invalid",
                },
            )
            assert resp.status_code == 401
            assert "signature" in resp.json()["detail"].lower()
        finally:
            settings.github_webhook_secret = original_secret

    async def test_accepts_valid_signature(self, client: httpx.AsyncClient) -> None:
        """Valid HMAC-SHA256 signature is accepted."""
        from nexus_api.config import get_settings

        settings = get_settings()
        original_secret = settings.github_webhook_secret
        secret = "test-secret-123"
        settings.github_webhook_secret = secret

        body = json.dumps({"action": "opened"}).encode()
        sig = "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()

        try:
            resp = await client.post(
                "/api/v1/gateway/github",
                content=body,
                headers={
                    "X-GitHub-Event": "ping",
                    "X-Hub-Signature-256": sig,
                },
            )
            assert resp.status_code == 200
        finally:
            settings.github_webhook_secret = original_secret

    async def test_skips_verification_when_no_secret(
        self, client: httpx.AsyncClient
    ) -> None:
        """When no webhook secret is configured, any payload is accepted."""
        from nexus_api.config import get_settings

        settings = get_settings()
        original_secret = settings.github_webhook_secret
        settings.github_webhook_secret = ""

        try:
            resp = await client.post(
                "/api/v1/gateway/github",
                content=b"{}",
                headers={"X-GitHub-Event": "ping"},
            )
            assert resp.status_code == 200
        finally:
            settings.github_webhook_secret = original_secret


class TestGitHubWebhookEvents:
    """Tests for event type handling and task creation."""

    async def test_ignored_event_returns_ignored(
        self, client: httpx.AsyncClient
    ) -> None:
        """Unknown event type returns ignored status."""
        body = json.dumps({"action": "completed"}).encode()
        resp = await client.post(
            "/api/v1/gateway/github",
            content=body,
            headers={"X-GitHub-Event": "deployment"},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @patch("nexus_api.routers.gateway.aioredis")
    @patch("nexus_api.routers.gateway.manager")
    async def test_pull_request_opened_creates_task(
        self,
        mock_manager: AsyncMock,
        mock_aioredis: AsyncMock,
        client: httpx.AsyncClient,
    ) -> None:
        """PR opened event creates a coding task."""
        mock_redis_client = AsyncMock()
        mock_aioredis.from_url.return_value = mock_redis_client
        mock_manager.broadcast = AsyncMock()

        payload = {
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Fix auth bug",
                "user": {"login": "dev-user"},
                "html_url": "https://github.com/org/repo/pull/42",
            },
            "repository": {"full_name": "org/repo"},
        }
        body = json.dumps(payload).encode()

        resp = await client.post(
            "/api/v1/gateway/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request"},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["tasks_created"] == 1

        # Verify Redis enqueue was attempted
        mock_redis_client.lpush.assert_called_once()
        call_args = mock_redis_client.lpush.call_args
        assert call_args[0][0] == "autoswarm:tasks"
        enqueued = json.loads(call_args[0][1])
        assert enqueued["graph_type"] == "coding"
        assert "PR #42" in enqueued["description"]

        # Verify WebSocket broadcast
        mock_manager.broadcast.assert_called_once()

    @patch("nexus_api.routers.gateway.aioredis")
    @patch("nexus_api.routers.gateway.manager")
    async def test_issue_opened_creates_research_task(
        self,
        mock_manager: AsyncMock,
        mock_aioredis: AsyncMock,
        client: httpx.AsyncClient,
    ) -> None:
        """Issue opened event creates a research task."""
        mock_redis_client = AsyncMock()
        mock_aioredis.from_url.return_value = mock_redis_client
        mock_manager.broadcast = AsyncMock()

        payload = {
            "action": "opened",
            "issue": {
                "number": 99,
                "title": "Investigate memory leak",
                "user": {"login": "reporter"},
                "html_url": "https://github.com/org/repo/issues/99",
                "labels": [{"name": "bug"}, {"name": "priority-high"}],
            },
            "repository": {"full_name": "org/repo"},
        }
        body = json.dumps(payload).encode()

        resp = await client.post(
            "/api/v1/gateway/github",
            content=body,
            headers={"X-GitHub-Event": "issues"},
        )

        assert resp.status_code == 200
        assert resp.json()["tasks_created"] == 1

        enqueued = json.loads(mock_redis_client.lpush.call_args[0][1])
        assert enqueued["graph_type"] == "research"
        assert "Issue #99" in enqueued["description"]

    @patch("nexus_api.routers.gateway.aioredis")
    @patch("nexus_api.routers.gateway.manager")
    async def test_check_suite_failure_creates_task(
        self,
        mock_manager: AsyncMock,
        mock_aioredis: AsyncMock,
        client: httpx.AsyncClient,
    ) -> None:
        """CI failure event creates a coding task."""
        mock_redis_client = AsyncMock()
        mock_aioredis.from_url.return_value = mock_redis_client
        mock_manager.broadcast = AsyncMock()

        payload = {
            "action": "completed",
            "check_suite": {
                "conclusion": "failure",
                "head_branch": "feat/new-feature",
                "head_sha": "abc123",
            },
            "repository": {"full_name": "org/repo"},
        }
        body = json.dumps(payload).encode()

        resp = await client.post(
            "/api/v1/gateway/github",
            content=body,
            headers={"X-GitHub-Event": "check_suite"},
        )

        assert resp.status_code == 200
        assert resp.json()["tasks_created"] == 1

    @patch("nexus_api.routers.gateway.aioredis")
    @patch("nexus_api.routers.gateway.manager")
    async def test_check_suite_success_no_task(
        self,
        mock_manager: AsyncMock,
        mock_aioredis: AsyncMock,
        client: httpx.AsyncClient,
    ) -> None:
        """Successful CI check does not create a task."""
        mock_redis_client = AsyncMock()
        mock_aioredis.from_url.return_value = mock_redis_client
        mock_manager.broadcast = AsyncMock()

        payload = {
            "action": "completed",
            "check_suite": {
                "conclusion": "success",
                "head_branch": "main",
                "head_sha": "def456",
            },
            "repository": {"full_name": "org/repo"},
        }
        body = json.dumps(payload).encode()

        resp = await client.post(
            "/api/v1/gateway/github",
            content=body,
            headers={"X-GitHub-Event": "check_suite"},
        )

        assert resp.status_code == 200
        assert resp.json()["tasks_created"] == 0

    @patch("nexus_api.routers.gateway.aioredis")
    @patch("nexus_api.routers.gateway.manager")
    async def test_redis_failure_still_returns_ok(
        self,
        mock_manager: AsyncMock,
        mock_aioredis: AsyncMock,
        client: httpx.AsyncClient,
    ) -> None:
        """Task is created even when Redis is unavailable."""
        mock_redis_client = AsyncMock()
        mock_redis_client.lpush.side_effect = Exception("Connection refused")
        mock_aioredis.from_url.return_value = mock_redis_client
        mock_manager.broadcast = AsyncMock()

        payload = {
            "action": "opened",
            "pull_request": {
                "number": 1,
                "title": "Test PR",
                "user": {"login": "dev"},
                "html_url": "https://github.com/org/repo/pull/1",
            },
            "repository": {"full_name": "org/repo"},
        }
        body = json.dumps(payload).encode()

        resp = await client.post(
            "/api/v1/gateway/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request"},
        )

        assert resp.status_code == 200
        assert resp.json()["tasks_created"] == 1
