"""
Tests for Gap 4: Extended Gateway Platforms (Slack, Email, SMS).
"""
from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def test_client():
    from nexus_api.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _mock_celery(monkeypatch):
    mock_task = MagicMock()
    mock_task.id = "task-ext-001"
    monkeypatch.setattr(
        "nexus_api.routers.gateway.run_acp_workflow_task.delay",
        MagicMock(return_value=mock_task),
    )


@pytest.fixture(autouse=True)
def _mock_memory(monkeypatch):
    monkeypatch.setattr(
        "nexus_api.routers.gateway.memory_store.insert_transcript",
        MagicMock(),
    )
    monkeypatch.setattr(
        "nexus_api.routers.gateway.memory_store.fts_search",
        MagicMock(return_value=[]),
    )


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------

class TestSlackGateway:
    URL = "/api/v1/gateway/slack/webhook"

    def _signed(self, client, body: str, secret: str, ts: int | None = None):
        ts = ts or int(time.time())
        sig_base = f"v0:{ts}:{body}"
        sig = "v0=" + _hmac.new(secret.encode(), sig_base.encode(), hashlib.sha256).hexdigest()
        return client.post(
            self.URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Signature": sig,
                "X-Slack-Request-Timestamp": str(ts),
            },
        )

    def test_initiate_acp_with_valid_sig(self, test_client, monkeypatch):
        secret = "slack-signing-secret"
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(
                slack_signing_secret=secret,
                discord_webhook_secret="",
                telegram_webhook_secret="",
                twilio_auth_token="",
                gateway_email_whitelist="",
            ),
        )
        body = "command=%2Finitiate_acp&text=https%3A%2F%2Ftarget.com&user_name=aldo"
        resp = self._signed(test_client, body, secret)
        assert resp.status_code == 200
        data = resp.json()
        assert "acp" in data.get("text", "").lower() or data.get("action") == "acp_triggered"

    def test_rejects_stale_timestamp(self, test_client, monkeypatch):
        secret = "slack-signing-secret"
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(slack_signing_secret=secret, discord_webhook_secret="", telegram_webhook_secret="", twilio_auth_token="", gateway_email_whitelist=""),
        )
        stale_ts = int(time.time()) - 400  # > 5 minutes old
        body = "command=%2Finitiate_acp&text=https%3A%2F%2Fhacker.com&user_name=bad"
        resp = self._signed(test_client, body, secret, ts=stale_ts)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

class TestEmailGateway:
    URL = "/api/v1/gateway/email/inbound"

    def test_whitelisted_sender_triggers_acp(self, test_client, monkeypatch):
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(slack_signing_secret="", discord_webhook_secret="", telegram_webhook_secret="", twilio_auth_token="", gateway_email_whitelist="boss@selva.town"),
        )
        resp = test_client.post(self.URL, json={
            "from": "boss@selva.town",
            "text": "Hey agent,\ninitiate_acp: https://target.example.com\nThanks",
        })
        assert resp.status_code == 200
        assert resp.json().get("action") == "acp_triggered"

    def test_unlisted_sender_is_rejected(self, test_client, monkeypatch):
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(slack_signing_secret="", discord_webhook_secret="", telegram_webhook_secret="", twilio_auth_token="", gateway_email_whitelist="boss@selva.town"),
        )
        resp = test_client.post(self.URL, json={
            "from": "stranger@evil.com",
            "text": "initiate_acp: https://hacker.com",
        })
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------

class TestSMSGateway:
    URL = "/api/v1/gateway/sms/inbound"

    def test_acp_sms_command_no_auth_configured(self, test_client, monkeypatch):
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(slack_signing_secret="", discord_webhook_secret="", telegram_webhook_secret="", twilio_auth_token="", gateway_email_whitelist=""),
        )
        body = "From=%2B15550001234&Body=acp+https%3A%2F%2Ftarget.com"
        resp = test_client.post(
            self.URL,
            content=body.encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        assert resp.json().get("action") == "acp_triggered"

    def test_unknown_sms_body_ignored(self, test_client, monkeypatch):
        monkeypatch.setattr(
            "nexus_api.routers.gateway.get_settings",
            lambda: MagicMock(slack_signing_secret="", discord_webhook_secret="", telegram_webhook_secret="", twilio_auth_token="", gateway_email_whitelist=""),
        )
        body = "From=%2B15550001234&Body=hello+world"
        resp = test_client.post(
            self.URL,
            content=body.encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.json()["status"] == "ignored"
