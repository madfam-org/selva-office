"""
E2E tests — Gap 8: Gateway Wave 2 (WhatsApp, Matrix, Mattermost, Signal)
"""
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch
import pytest
from httpx import AsyncClient


def _make_whatsapp_payload(text: str, from_number: str = "+15551234567") -> dict:
    return {
        "entry": [{"changes": [{"value": {"messages": [{"text": {"body": text}, "from": from_number}]}}]}]
    }


def _make_matrix_payload(text: str, sender: str = "@user:matrix.example.com") -> dict:
    return {
        "events": [
            {"type": "m.room.message", "sender": sender, "content": {"msgtype": "m.text", "body": text}}
        ]
    }


class TestWhatsAppGateway:
    @pytest.mark.asyncio
    async def test_webhook_verification_challenge(self, async_client: AsyncClient):
        """GET /gateway/whatsapp/webhook responds to Meta verification challenge."""
        with patch("nexus_api.routers.gateway.get_settings") as mock_settings:
            mock_settings.return_value.whatsapp_verify_token = "my-verify-token"
            response = await async_client.get(
                "/api/v1/gateway/whatsapp/webhook",
                params={"hub.mode": "subscribe", "hub.verify_token": "my-verify-token", "hub.challenge": "abc123"},
            )
        assert response.status_code == 200
        assert response.text == "abc123"

    @pytest.mark.asyncio
    async def test_webhook_verification_fails_wrong_token(self, async_client: AsyncClient):
        with patch("nexus_api.routers.gateway.get_settings") as mock_settings:
            mock_settings.return_value.whatsapp_verify_token = "correct-token"
            response = await async_client.get(
                "/api/v1/gateway/whatsapp/webhook",
                params={"hub.mode": "subscribe", "hub.verify_token": "wrong-token", "hub.challenge": "abc123"},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_acp_command_triggers_task(self, async_client: AsyncClient):
        payload = _make_whatsapp_payload("acp https://example.com")
        with patch("nexus_api.routers.gateway.get_settings") as mock_settings:
            with patch("nexus_api.routers.gateway.run_acp_workflow_task") as mock_task:
                with patch("nexus_api.routers.gateway.memory_store"):
                    mock_settings.return_value.whatsapp_access_token = ""  # Skip sig validation
                    mock_task.delay.return_value = MagicMock(id="task-wa-001")
                    response = await async_client.post("/api/v1/gateway/whatsapp/webhook", json=payload)
        assert response.status_code == 200
        assert response.json()["action"] == "acp_triggered"


class TestMatrixGateway:
    @pytest.mark.asyncio
    async def test_valid_token_routes_acp(self, async_client: AsyncClient):
        payload = _make_matrix_payload("acp https://example.com")
        with patch("nexus_api.routers.gateway.get_settings") as mock_settings:
            with patch("nexus_api.routers.gateway.run_acp_workflow_task") as mock_task:
                with patch("nexus_api.routers.gateway.memory_store"):
                    mock_settings.return_value.matrix_appservice_token = "matrix-secret"
                    mock_task.delay.return_value = MagicMock(id="task-mx-001")
                    response = await async_client.post(
                        "/api/v1/gateway/matrix/webhook",
                        json=payload,
                        headers={"Authorization": "Bearer matrix-secret"},
                    )
        assert response.status_code == 200
        assert response.json()["action"] == "acp_triggered"

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, async_client: AsyncClient):
        payload = _make_matrix_payload("acp https://example.com")
        with patch("nexus_api.routers.gateway.get_settings") as mock_settings:
            mock_settings.return_value.matrix_appservice_token = "real-secret"
            response = await async_client.post(
                "/api/v1/gateway/matrix/webhook",
                json=payload,
                headers={"Authorization": "Bearer wrong-secret"},
            )
        assert response.status_code == 401


class TestMattermostGateway:
    @pytest.mark.asyncio
    async def test_slash_command_triggers_acp(self, async_client: AsyncClient):
        with patch("nexus_api.routers.gateway.get_settings") as mock_settings:
            with patch("nexus_api.routers.gateway.run_acp_workflow_task") as mock_task:
                with patch("nexus_api.routers.gateway.memory_store"):
                    mock_settings.return_value.mattermost_token = "mm-secret"
                    mock_task.delay.return_value = MagicMock(id="task-mm-001")
                    response = await async_client.post(
                        "/api/v1/gateway/mattermost/webhook",
                        data={"token": "mm-secret", "text": "https://example.com", "user_name": "alice"},
                    )
        assert response.status_code == 200
        body = response.json()
        assert body["response_type"] == "ephemeral"
        assert "task-mm-001" in body["text"]

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, async_client: AsyncClient):
        with patch("nexus_api.routers.gateway.get_settings") as mock_settings:
            mock_settings.return_value.mattermost_token = "real-token"
            response = await async_client.post(
                "/api/v1/gateway/mattermost/webhook",
                data={"token": "wrong-token", "text": "https://example.com", "user_name": "bob"},
            )
        assert response.status_code == 401


class TestSignalGateway:
    @pytest.mark.asyncio
    async def test_whitelisted_source_triggers_acp(self, async_client: AsyncClient):
        payload = {"envelope": {"source": "+15559998888", "dataMessage": {"message": "acp https://example.com"}}}
        with patch("nexus_api.routers.gateway.get_settings") as mock_settings:
            with patch("nexus_api.routers.gateway.run_acp_workflow_task") as mock_task:
                with patch("nexus_api.routers.gateway.memory_store"):
                    mock_settings.return_value.signal_allowed_numbers = "+15559998888"
                    mock_task.delay.return_value = MagicMock(id="task-sig-001")
                    response = await async_client.post("/api/v1/gateway/signal/webhook", json=payload)
        assert response.status_code == 200
        assert response.json()["action"] == "acp_triggered"

    @pytest.mark.asyncio
    async def test_non_whitelisted_source_rejected(self, async_client: AsyncClient):
        payload = {"envelope": {"source": "+19990000000", "dataMessage": {"message": "acp https://example.com"}}}
        with patch("nexus_api.routers.gateway.get_settings") as mock_settings:
            mock_settings.return_value.signal_allowed_numbers = "+15559998888"
            response = await async_client.post("/api/v1/gateway/signal/webhook", json=payload)
        assert response.status_code == 403
