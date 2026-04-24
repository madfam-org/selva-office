"""Twilio Voice outbound-call tools.

Closes the highest-reversibility-cost communication gap: a voice call.
When a botched email annoys a lead, a botched voice call actively damages
the relationship — but voice is still the right channel for late-stage
sales, appointment confirmations, and urgent ops calls out to an on-call
human phone. These tools are HITL-gated inside the outbound-voice skill.

Two call modes:

- ``voice_call_make``: caller provides a TwiML Bin / application URL the
  call will fetch on connect. Use this when the flow is dynamic (IVR,
  recording, transfer-to-agent).
- ``voice_call_say``: convenience one-shot. Constructs a TwiML payload
  inline that speaks the provided text via ``<Say voice="alice" language=
  "es-MX">…</Say>``. The TwiML is served via Twilio's ``Twiml`` parameter,
  so no external webhook is needed.

Credentials: ``TWILIO_ACCOUNT_SID``, ``TWILIO_AUTH_TOKEN``,
``TWILIO_FROM_NUMBER``.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

TWILIO_BASE = "https://api.twilio.com/2010-04-01"
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")


def _creds_check() -> str | None:
    if not TWILIO_ACCOUNT_SID:
        return "TWILIO_ACCOUNT_SID must be set."
    if not TWILIO_AUTH_TOKEN:
        return "TWILIO_AUTH_TOKEN must be set."
    return None


def _auth() -> tuple[str, str]:
    return (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


async def _request(
    method: str,
    path: str,
    data: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | str]:
    url = f"{TWILIO_BASE}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, auth=_auth(), data=data)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


def _err(status: int, body: Any) -> str:
    if isinstance(body, dict):
        return body.get("message") or body.get("error_message") or str(body)
    return f"HTTP {status}: {body}"


def _build_say_twiml(text: str, voice: str, language: str) -> str:
    """Build a minimal TwiML document that speaks `text` once."""
    safe_text = xml_escape(text)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say voice="{xml_escape(voice)}" language="{xml_escape(language)}">'
        f"{safe_text}"
        "</Say>"
        "</Response>"
    )


class VoiceCallMakeTool(BaseTool):
    """Initiate an outbound Twilio Voice call driven by a remote TwiML URL."""

    name = "voice_call_make"
    description = (
        "Initiate an outbound voice call. Twilio will fetch ``twiml_url`` "
        "on connect to determine the call flow (Say, Gather, Dial, Record, "
        "etc.). The URL must be publicly reachable and respond with valid "
        "TwiML. Returns the call SID; poll voice_call_status for "
        "completion/failure. Reversibility cost is high — HITL-gate this "
        "tool in any autonomous flow."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to_number": {
                    "type": "string",
                    "description": "E.164 destination, e.g. +5217771234567.",
                },
                "twiml_url": {
                    "type": "string",
                    "description": "URL Twilio will fetch on answer. Must "
                    "respond with TwiML. For static scripts prefer "
                    "voice_call_say.",
                },
                "from_number": {"type": "string"},
                "status_callback_url": {
                    "type": "string",
                    "description": "Optional webhook for call-status events "
                    "(initiated, ringing, answered, completed).",
                },
            },
            "required": ["to_number", "twiml_url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        from_number = kwargs.get("from_number") or TWILIO_FROM_NUMBER
        if not from_number:
            return ToolResult(
                success=False,
                error="TWILIO_FROM_NUMBER must be set (or pass from_number explicitly).",
            )
        payload: dict[str, Any] = {
            "To": kwargs["to_number"],
            "From": from_number,
            "Url": kwargs["twiml_url"],
        }
        if kwargs.get("status_callback_url"):
            payload["StatusCallback"] = kwargs["status_callback_url"]
            payload["StatusCallbackEvent"] = ["initiated", "ringing", "answered", "completed"]
        try:
            status, body = await _request(
                "POST",
                f"/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json",
                data=payload,
            )
            if status >= 400 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"Call initiated to {kwargs['to_number']}: "
                    f"sid={body.get('sid')} status={body.get('status')}"
                ),
                data={
                    "sid": body.get("sid"),
                    "status": body.get("status"),
                    "to": body.get("to"),
                    "from": body.get("from"),
                },
            )
        except Exception as e:
            logger.error("voice_call_make failed: %s", e)
            return ToolResult(success=False, error=str(e))


class VoiceCallStatusTool(BaseTool):
    """Get status for an in-progress or completed voice call."""

    name = "voice_call_status"
    description = (
        "Fetch current status for a Twilio voice call by SID. Typical "
        "lifecycle: queued → ringing → in-progress → completed. Terminal "
        "failure statuses: busy, no-answer, canceled, failed."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"call_sid": {"type": "string"}},
            "required": ["call_sid"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        sid = kwargs["call_sid"]
        try:
            status, body = await _request(
                "GET",
                f"/Accounts/{TWILIO_ACCOUNT_SID}/Calls/{sid}.json",
            )
            if status >= 400 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(f"{sid}: {body.get('status')} duration={body.get('duration')}s"),
                data={
                    "sid": body.get("sid"),
                    "status": body.get("status"),
                    "duration": body.get("duration"),
                    "start_time": body.get("start_time"),
                    "end_time": body.get("end_time"),
                    "price": body.get("price"),
                    "price_unit": body.get("price_unit"),
                    "direction": body.get("direction"),
                },
            )
        except Exception as e:
            logger.error("voice_call_status failed: %s", e)
            return ToolResult(success=False, error=str(e))


class VoiceCallSayTool(BaseTool):
    """Convenience: place a call that speaks a single text payload once."""

    name = "voice_call_say"
    description = (
        "Place an outbound call that speaks the provided text once and "
        "hangs up. Defaults: voice='alice', language='es-MX'. Builds the "
        "TwiML inline and submits via the ``Twiml`` Twilio param, so no "
        "external webhook is needed. Use this for simple confirmations "
        "(appointment reminders, delivery windows). Reversibility cost is "
        "high — HITL-gate autonomous usage."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to_number": {"type": "string"},
                "text": {
                    "type": "string",
                    "description": "Message to speak. Max ~4000 chars "
                    "(Twilio limit on inline TwiML).",
                },
                "voice": {
                    "type": "string",
                    "default": "alice",
                    "description": "Twilio voice. 'alice' (classic), "
                    "'Polly.Mia-Neural' (neural es-MX).",
                },
                "language": {
                    "type": "string",
                    "default": "es-MX",
                },
                "from_number": {"type": "string"},
            },
            "required": ["to_number", "text"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        from_number = kwargs.get("from_number") or TWILIO_FROM_NUMBER
        if not from_number:
            return ToolResult(
                success=False,
                error="TWILIO_FROM_NUMBER must be set (or pass from_number explicitly).",
            )
        voice = kwargs.get("voice", "alice")
        language = kwargs.get("language", "es-MX")
        twiml = _build_say_twiml(kwargs["text"], voice, language)
        payload = {
            "To": kwargs["to_number"],
            "From": from_number,
            "Twiml": twiml,
        }
        try:
            status, body = await _request(
                "POST",
                f"/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json",
                data=payload,
            )
            if status >= 400 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"Say-call initiated to {kwargs['to_number']}: "
                    f"sid={body.get('sid')} status={body.get('status')}"
                ),
                data={
                    "sid": body.get("sid"),
                    "status": body.get("status"),
                    "voice": voice,
                    "language": language,
                },
            )
        except Exception as e:
            logger.error("voice_call_say failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_voice_call_tools() -> list[BaseTool]:
    """Return the Twilio Voice tool set."""
    return [
        VoiceCallMakeTool(),
        VoiceCallStatusTool(),
        VoiceCallSayTool(),
    ]
