"""
Tests for the hardened multi-channel gateway endpoints.

Verifies:
- Telegram HMAC secret enforcement
- Discord HMAC-SHA256 enforcement
- /initiate_acp command routing
- /status FTS memory query
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_client():
    """Return a TestClient with the full FastAPI app."""
    from nexus_api.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _mock_celery(monkeypatch):
    """Prevent real Celery tasks from firing during gateway tests."""
    mock_task = MagicMock()
    mock_task.id = "test-task-xyz"
    monkeypatch.setattr(
        "nexus_api.routers.gateway.run_acp_workflow_task.delay",
        MagicMock(return_value=mock_task),
    )


@pytest.fixture(autouse=True)
def _mock_memory(monkeypatch):
    """Prevent writes to real SQLite during gateway tests."""
    monkeypatch.setattr(
        "nexus_api.routers.gateway.memory_store.insert_transcript",
        MagicMock(),
    )
    monkeypatch.setattr(
        "nexus_api.routers.gateway.memory_store.fts_search",
        MagicMock(return_value=[{"content": "test result", "run_id": "r1", "agent_role": "acp"}]),
    )


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

class TestTelegramGateway:
    URL = "/api/v1/gateway/telegram/webhook"

    def test_initiate_acp_no_secret_configured(self, test_client, monkeypatch):
        """When telegram_webhook_secret is empty, any request should pass."""
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(
                telegram_webhook_secret="",
                discord_webhook_secret="",
            ),
        )
        payload = {"message": {"text": "/initiate_acp https://example.com", "chat": {"id": 123}}}
        resp = test_client.post(self.URL, json=payload)
        assert resp.status_code == 200
        assert resp.json()["action"] == "acp_triggered"

    def test_rejects_bad_secret(self, test_client, monkeypatch):
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(telegram_webhook_secret="correct-secret"),
        )
        payload = {"message": {"text": "/initiate_acp https://evil.com", "chat": {"id": 999}}}
        resp = test_client.post(
            self.URL,
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )
        assert resp.status_code == 401

    def test_ignored_for_unknown_command(self, test_client, monkeypatch):
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(telegram_webhook_secret=""),
        )
        payload = {"message": {"text": "/hello world", "chat": {"id": 1}}}
        resp = test_client.post(self.URL, json=payload)
        assert resp.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------

class TestDiscordGateway:
    URL = "/api/v1/gateway/discord/webhook"

    def _signed_request(self, client, payload: dict, secret: str):
        body = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return client.post(
            self.URL,
            content=body,
            headers={"Content-Type": "application/json", "X-Signature-256": sig},
        )

    def test_status_command_returns_fts_results(self, test_client, monkeypatch):
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(discord_webhook_secret=""),
        )
        resp = test_client.post(self.URL, json={"content": "/status acp"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "results" in data

    def test_rejects_invalid_signature(self, test_client, monkeypatch):
        secret = "super-secret"
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(discord_webhook_secret=secret),
        )
        body = json.dumps({"content": "/status"}).encode()
        resp = test_client.post(
            self.URL,
            content=body,
            headers={"Content-Type": "application/json", "X-Signature-256": "sha256=badhash"},
        )
        assert resp.status_code == 401

    def test_initiate_acp_from_discord_with_valid_sig(self, test_client, monkeypatch):
        secret = "my-discord-secret"
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(discord_webhook_secret=secret),
        )
        payload = {"content": "/initiate_acp https://target.example.com"}
        resp = self._signed_request(test_client, payload, secret)
        assert resp.status_code == 200
        assert resp.json()["action"] == "acp_triggered"
