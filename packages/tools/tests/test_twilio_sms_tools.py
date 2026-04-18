"""Tests for Twilio SMS tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from selva_tools.builtins.twilio_sms import (
    SmsListMessagesTool,
    SmsSendTemplateTool,
    SmsSendTool,
    SmsStatusTool,
    get_twilio_sms_tools,
)


class TestRegistry:
    def test_four_tools_exported(self) -> None:
        tools = get_twilio_sms_tools()
        names = {t.name for t in tools}
        assert names == {
            "sms_send",
            "sms_send_template",
            "sms_status",
            "sms_list_messages",
        }

    def test_schemas_valid(self) -> None:
        for t in get_twilio_sms_tools():
            s = t.parameters_schema()
            assert s["type"] == "object"
            assert "properties" in s


class TestCredsAbsence:
    @pytest.mark.asyncio
    async def test_missing_account_sid_errors(self) -> None:
        with patch("selva_tools.builtins.twilio_sms.TWILIO_ACCOUNT_SID", ""), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_AUTH_TOKEN", "t"
        ):
            r = await SmsSendTool().execute(to_number="+5215555555555", body="hi")
            assert r.success is False
            assert "TWILIO_ACCOUNT_SID" in (r.error or "")

    @pytest.mark.asyncio
    async def test_missing_auth_token_errors(self) -> None:
        with patch("selva_tools.builtins.twilio_sms.TWILIO_ACCOUNT_SID", "AC1"), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_AUTH_TOKEN", ""
        ):
            r = await SmsStatusTool().execute(message_sid="SM1")
            assert r.success is False
            assert "TWILIO_AUTH_TOKEN" in (r.error or "")

    @pytest.mark.asyncio
    async def test_missing_from_number_errors(self) -> None:
        with patch("selva_tools.builtins.twilio_sms.TWILIO_ACCOUNT_SID", "AC1"), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_AUTH_TOKEN", "t"
        ), patch("selva_tools.builtins.twilio_sms.TWILIO_FROM_NUMBER", ""):
            r = await SmsSendTool().execute(to_number="+52555", body="hi")
            assert r.success is False
            assert "TWILIO_FROM_NUMBER" in (r.error or "")


class TestSmsSend:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        captured: dict = {}

        async def fake(method, path, data=None, params=None):
            captured["method"] = method
            captured["path"] = path
            captured["data"] = data
            return 201, {
                "sid": "SM123",
                "status": "queued",
                "to": "+5215555555555",
                "from": "+15005550006",
                "num_segments": "1",
            }

        with patch("selva_tools.builtins.twilio_sms.TWILIO_ACCOUNT_SID", "AC1"), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_AUTH_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_FROM_NUMBER", "+15005550006"
        ), patch(
            "selva_tools.builtins.twilio_sms._request", new=fake
        ):
            r = await SmsSendTool().execute(
                to_number="+5215555555555", body="hola"
            )
            assert r.success is True
            assert r.data["sid"] == "SM123"
            assert captured["data"]["To"] == "+5215555555555"
            assert captured["data"]["Body"] == "hola"
            assert captured["data"]["From"] == "+15005550006"

    @pytest.mark.asyncio
    async def test_media_urls_attached(self) -> None:
        captured: dict = {}

        async def fake(method, path, data=None, params=None):
            captured["data"] = data
            return 201, {"sid": "SM9", "status": "queued"}

        with patch("selva_tools.builtins.twilio_sms.TWILIO_ACCOUNT_SID", "AC1"), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_AUTH_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_FROM_NUMBER", "+1500"
        ), patch(
            "selva_tools.builtins.twilio_sms._request", new=fake
        ):
            await SmsSendTool().execute(
                to_number="+52555",
                body="hi",
                media_urls=["https://example.com/a.png"],
            )
            assert captured["data"]["MediaUrl"] == ["https://example.com/a.png"]

    @pytest.mark.asyncio
    async def test_error_bubbles_up(self) -> None:
        with patch("selva_tools.builtins.twilio_sms.TWILIO_ACCOUNT_SID", "AC1"), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_AUTH_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_FROM_NUMBER", "+1500"
        ), patch(
            "selva_tools.builtins.twilio_sms._request",
            new=AsyncMock(
                return_value=(
                    400,
                    {"message": "The 'To' number is invalid.", "code": 21211},
                )
            ),
        ):
            r = await SmsSendTool().execute(to_number="bad", body="hi")
            assert r.success is False
            assert "invalid" in (r.error or "")


class TestSmsSendTemplate:
    @pytest.mark.asyncio
    async def test_content_sid_and_variables_encoded(self) -> None:
        captured: dict = {}

        async def fake(method, path, data=None, params=None):
            captured["data"] = data
            return 201, {"sid": "SM_T1", "status": "queued"}

        with patch("selva_tools.builtins.twilio_sms.TWILIO_ACCOUNT_SID", "AC1"), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_AUTH_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_FROM_NUMBER", "+1500"
        ), patch(
            "selva_tools.builtins.twilio_sms._request", new=fake
        ):
            r = await SmsSendTemplateTool().execute(
                to_number="+52555",
                template_id="HXabc123",
                variables={"1": "Ana", "2": "09:00"},
            )
            assert r.success is True
            assert r.data["sid"] == "SM_T1"
            assert captured["data"]["ContentSid"] == "HXabc123"
            # ContentVariables is a JSON string of the mapping
            import json
            loaded = json.loads(captured["data"]["ContentVariables"])
            assert loaded == {"1": "Ana", "2": "09:00"}


class TestSmsStatus:
    @pytest.mark.asyncio
    async def test_status_returned(self) -> None:
        with patch("selva_tools.builtins.twilio_sms.TWILIO_ACCOUNT_SID", "AC1"), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_AUTH_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.twilio_sms._request",
            new=AsyncMock(
                return_value=(
                    200,
                    {
                        "sid": "SM1",
                        "status": "delivered",
                        "error_code": None,
                        "error_message": None,
                        "price": "-0.0075",
                        "price_unit": "USD",
                    },
                )
            ),
        ):
            r = await SmsStatusTool().execute(message_sid="SM1")
            assert r.success is True
            assert r.data["status"] == "delivered"


class TestSmsListMessages:
    @pytest.mark.asyncio
    async def test_list_returns_summary(self) -> None:
        captured: dict = {}

        async def fake(method, path, data=None, params=None):
            captured["params"] = params
            return 200, {
                "messages": [
                    {
                        "sid": "SM1",
                        "to": "+52555",
                        "from": "+1500",
                        "status": "delivered",
                        "date_sent": "Sat, 01 Mar 2026 09:00:00 +0000",
                        "body": "hi",
                    }
                ]
            }

        with patch("selva_tools.builtins.twilio_sms.TWILIO_ACCOUNT_SID", "AC1"), patch(
            "selva_tools.builtins.twilio_sms.TWILIO_AUTH_TOKEN", "t"
        ), patch("selva_tools.builtins.twilio_sms._request", new=fake):
            r = await SmsListMessagesTool().execute(to="+52555", limit=10)
            assert r.success is True
            assert len(r.data["messages"]) == 1
            assert captured["params"]["To"] == "+52555"
            assert captured["params"]["PageSize"] == 10
