"""Tests for the Enclii webhook endpoint (Gap D)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEncliiWebhookAuth:
    """Enclii webhook Bearer token verification."""

    @pytest.mark.asyncio
    async def test_missing_bearer_token_returns_401(self) -> None:
        from nexus_api.routers.gateway import enclii_webhook

        request = MagicMock()
        request.headers = {}
        request.body = AsyncMock(return_value=b'{"event": "deploy_failed"}')

        with pytest.raises(Exception) as exc_info:
            await enclii_webhook(request)

        # HTTPException with 401
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self) -> None:
        from nexus_api.routers.gateway import enclii_webhook

        request = MagicMock()
        request.headers = {"authorization": "Bearer wrong-token"}
        request.body = AsyncMock(return_value=b'{"event": "deploy_failed"}')
        request.state = MagicMock(request_id=None)

        mock_settings = MagicMock()
        mock_settings.enclii_webhook_secret = "correct-secret"
        mock_settings.environment = "production"
        mock_settings.redis_url = "redis://localhost"

        with (
            patch("nexus_api.routers.gateway.get_settings", return_value=mock_settings),
            pytest.raises(Exception) as exc_info,
        ):
            await enclii_webhook(request)

        assert exc_info.value.status_code == 401


class TestEncliiEventMapping:
    """Enclii events map to correct graph types."""

    def test_event_map_entries(self) -> None:
        from nexus_api.routers.gateway import _ENCLII_EVENT_MAP

        assert _ENCLII_EVENT_MAP["deploy_failed"] == "coding"
        assert _ENCLII_EVENT_MAP["deploy_rollback"] == "coding"
        assert _ENCLII_EVENT_MAP["deploy_succeeded"] == "research"

    @pytest.mark.asyncio
    async def test_unknown_event_ignored(self) -> None:
        from nexus_api.routers.gateway import enclii_webhook

        request = MagicMock()
        request.headers = {"authorization": "Bearer dev-token"}
        request.body = AsyncMock(
            return_value=json.dumps({"event": "deploy_started"}).encode()
        )
        request.state = MagicMock(request_id=None)

        mock_settings = MagicMock()
        mock_settings.enclii_webhook_secret = ""
        mock_settings.environment = "development"

        with patch("nexus_api.routers.gateway.get_settings", return_value=mock_settings):
            result = await enclii_webhook(request)

        assert result["status"] == "ignored"


class TestEncliiTaskCreation:
    """_create_task_from_enclii creates SwarmTasks."""

    @pytest.mark.asyncio
    async def test_deploy_failed_creates_coding_task(self) -> None:
        from nexus_api.routers.gateway import _create_task_from_enclii

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        payload = {
            "service": "web-api",
            "environment": "staging",
            "deploy_id": "dep-456",
            "error": "health check failed",
        }

        task = await _create_task_from_enclii(
            mock_session, "deploy_failed", payload, "coding"
        )

        assert task is not None
        assert task.graph_type == "coding"
        assert "web-api" in task.description
        assert "investigate" in task.description
        assert task.payload["deploy_id"] == "dep-456"
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_deploy_succeeded_creates_research_task(self) -> None:
        from nexus_api.routers.gateway import _create_task_from_enclii

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        payload = {
            "service": "web-api",
            "environment": "production",
            "deploy_id": "dep-789",
        }

        task = await _create_task_from_enclii(
            mock_session, "deploy_succeeded", payload, "research"
        )

        assert task is not None
        assert task.graph_type == "research"
        assert "report" in task.description

    @pytest.mark.asyncio
    async def test_unknown_event_returns_none(self) -> None:
        from nexus_api.routers.gateway import _create_task_from_enclii

        mock_session = MagicMock()

        task = await _create_task_from_enclii(
            mock_session, "deploy_unknown", {}, "coding"
        )

        assert task is None
