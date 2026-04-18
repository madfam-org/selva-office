"""Gate tests for SendEmailTool / SendMarketingEmailTool voice-mode enforcement.

These tests run without a real nexus-api by monkeypatching the
``_fetch_voice_mode`` helper. They verify:

- When voice_mode is None the tool refuses to send.
- When agent_identified, SPF/DKIM/DMARC failure blocks the send.
- When the mode is set and alignment passes, the send proceeds.
- The From header matches the selected mode's identity builder.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from selva_tools.builtins import email_tools, marketing_tools
from selva_tools.builtins._spf_check import SpfResult


@pytest.mark.asyncio
async def test_send_email_blocked_when_voice_mode_not_set() -> None:
    tool = email_tools.SendEmailTool()
    with patch.object(
        email_tools, "_fetch_voice_mode", AsyncMock(return_value=None)
    ):
        result = await tool.execute(
            to="dest@example.com",
            subject="Hi",
            html="<p>x</p>",
            org_id="org-1",
            user_email="me@example.com",
        )
    assert result.success is False
    assert "voice mode" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_send_email_agent_identified_blocked_on_spf_fail() -> None:
    tool = email_tools.SendEmailTool()
    bad_alignment = SpfResult(
        domain="selva.town",
        spf_ok=False,
        dkim_ok=False,
        dmarc_ok=False,
        status="fail",
        reason="Missing SPF",
    )
    with (
        patch.object(email_tools, "_fetch_voice_mode", AsyncMock(return_value="agent_identified")),
        patch.object(email_tools, "check_alignment", return_value=bad_alignment),
        patch.dict("os.environ", {"RESEND_API_KEY": "rk-test"}, clear=False),
    ):
        result = await tool.execute(
            to="dest@example.com",
            subject="Hi",
            html="<p>x</p>",
            org_id="org-1",
            user_email="me@example.com",
            agent_slug="bot",
            agent_display_name="Bot",
        )
    assert result.success is False
    assert "alignment" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_send_email_dyad_mode_sends_with_co_branded_from() -> None:
    tool = email_tools.SendEmailTool()
    captured: dict = {}

    class _MockResp:
        status_code = 201

        def json(self) -> dict:
            return {"id": "msg-123"}

    class _MockClient:
        async def __aenter__(self) -> _MockClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, headers: dict, json: dict) -> _MockResp:
            captured["payload"] = json
            return _MockResp()

    with (
        patch.object(
            email_tools,
            "_fetch_voice_mode",
            AsyncMock(return_value="dyad_selva_plus_user"),
        ),
        patch.object(email_tools.httpx, "AsyncClient", lambda timeout=10: _MockClient()),
        patch.dict("os.environ", {"RESEND_API_KEY": "rk-test"}, clear=False),
    ):
        result = await tool.execute(
            to="dest@example.com",
            subject="Hi",
            html="<p>Hello</p>",
            org_id="org-1",
            user_name="Ada",
            user_email="ada@example.com",
        )
    assert result.success is True, result.error
    payload = captured["payload"]
    assert "Selva on behalf of Ada" in payload["from"]
    assert payload["reply_to"] == "ada@example.com"


@pytest.mark.asyncio
async def test_send_email_agent_identified_passes_when_aligned() -> None:
    tool = email_tools.SendEmailTool()
    good_alignment = SpfResult(
        domain="selva.town",
        spf_ok=True,
        dkim_ok=True,
        dmarc_ok=True,
        status="pass",
        reason="aligned",
    )
    captured: dict = {}

    class _MockResp:
        status_code = 201

        def json(self) -> dict:
            return {"id": "msg-aid-123"}

    class _MockClient:
        async def __aenter__(self) -> _MockClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, headers: dict, json: dict) -> _MockResp:
            captured["payload"] = json
            return _MockResp()

    with (
        patch.object(
            email_tools,
            "_fetch_voice_mode",
            AsyncMock(return_value="agent_identified"),
        ),
        patch.object(email_tools, "check_alignment", return_value=good_alignment),
        patch.object(email_tools.httpx, "AsyncClient", lambda timeout=10: _MockClient()),
        patch.dict("os.environ", {"RESEND_API_KEY": "rk-test"}, clear=False),
    ):
        result = await tool.execute(
            to="dest@example.com",
            subject="Hi",
            html="<p>x</p>",
            org_id="org-1",
            user_name="Ada",
            user_email="ada@example.com",
            agent_slug="nexo",
            agent_display_name="Nexo",
            org_name="MADFAM",
        )
    assert result.success is True, result.error
    payload = captured["payload"]
    assert "nexo@selva.town" in payload["from"]
    # agent_identified does NOT inject Reply-To (no user mailbox).
    assert "reply_to" not in payload


@pytest.mark.asyncio
async def test_marketing_email_refuses_without_voice_mode() -> None:
    tool = marketing_tools.SendMarketingEmailTool()
    with (
        patch.object(
            marketing_tools, "_fetch_voice_mode", AsyncMock(return_value=None)
        ),
        patch.dict("os.environ", {"RESEND_API_KEY": "rk-test"}, clear=False),
    ):
        result = await tool.execute(
            to_email="dest@example.com",
            subject="Hi",
            body_html="<p>body</p>",
            org_id="org-1",
            user_email="me@example.com",
        )
    assert result.success is False
    assert "voice mode" in (result.error or "").lower()
