"""Twilio SMS tools for Mexico + international outbound messaging.

Closes the capability gap around asynchronous, low-friction customer contact:
email is too slow for time-sensitive confirmations (appointments, OTP codes,
payment reminders); WhatsApp requires pre-approved templates and a Business
API onboarding flow. SMS is the lowest-friction fallback and, critically, the
channel Mexican carriers (Telcel, AT&T MX, Movistar) enforce templating /
content rules on — this module surfaces the ``sms_send_template`` path so an
agent can choose the correct mode without reaching for a shell escape.

Talks directly to Twilio's REST API (``api.twilio.com``). Credentials come
from ``TWILIO_ACCOUNT_SID``, ``TWILIO_AUTH_TOKEN``, and the default sender
``TWILIO_FROM_NUMBER`` (E.164). All four tools fail closed when credentials
are absent.
"""

from __future__ import annotations

import logging
import os
from typing import Any

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
    params: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | str]:
    """Low-level Twilio API call; returns (status, parsed_body).

    Twilio REST uses form-encoded bodies for POSTs, not JSON.
    """
    url = f"{TWILIO_BASE}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method,
            url,
            auth=_auth(),
            data=data,
            params=params,
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


def _err(status: int, body: Any) -> str:
    if isinstance(body, dict):
        return body.get("message") or body.get("error_message") or str(body)
    return f"HTTP {status}: {body}"


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


class SmsSendTool(BaseTool):
    """Send a plain-text SMS (or MMS with media) via Twilio."""

    name = "sms_send"
    description = (
        "Send an SMS to ``to_number`` (E.164, e.g. +5217771234567). Use "
        "for transactional / informational messages that don't require a "
        "pre-approved template. For MX carriers requiring templating on "
        "promotional or authentication content, use sms_send_template "
        "instead. Optional ``media_urls`` upgrade the send to MMS."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to_number": {
                    "type": "string",
                    "description": "E.164 phone number, e.g. +5217771234567.",
                },
                "body": {
                    "type": "string",
                    "description": "Message body. Max 1600 chars; longer messages "
                    "are split by Twilio into concatenated segments.",
                },
                "media_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Optional list of publicly-fetchable media URLs "
                    "(images, PDFs). Promotes the send to MMS.",
                },
                "from_number": {
                    "type": "string",
                    "description": "Override the default ``TWILIO_FROM_NUMBER`` "
                    "(E.164). Rarely needed.",
                },
            },
            "required": ["to_number", "body"],
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
            "Body": kwargs["body"],
        }
        media_urls = kwargs.get("media_urls") or []
        if media_urls:
            # Twilio accepts repeated MediaUrl params; httpx data= flattens lists.
            payload["MediaUrl"] = media_urls
        try:
            status, body = await _request(
                "POST",
                f"/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
                data=payload,
            )
            if status >= 400 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"SMS queued to {kwargs['to_number']}: "
                    f"sid={body.get('sid')} status={body.get('status')}"
                ),
                data={
                    "sid": body.get("sid"),
                    "status": body.get("status"),
                    "to": body.get("to"),
                    "from": body.get("from"),
                    "num_segments": body.get("num_segments"),
                },
            )
        except Exception as e:
            logger.error("sms_send failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# send template
# ---------------------------------------------------------------------------


class SmsSendTemplateTool(BaseTool):
    """Send an SMS using a pre-approved Twilio Content API template."""

    name = "sms_send_template"
    description = (
        "Send an SMS referencing a pre-approved Twilio Content template "
        "(Content SID HX...). Required for promotional / authentication / "
        "otp traffic to Mexican carriers and any regulated-content path. "
        "``variables`` is a dict of template placeholder substitutions; "
        "Twilio expects it JSON-encoded in the form body."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to_number": {"type": "string"},
                "template_id": {
                    "type": "string",
                    "description": "Twilio Content SID (starts with HX).",
                },
                "variables": {
                    "type": "object",
                    "description": "Placeholder substitutions, e.g. "
                    '{"1": "Ana", "2": "09:00"} for a template with {{1}} {{2}}.',
                    "default": {},
                },
                "from_number": {"type": "string"},
            },
            "required": ["to_number", "template_id"],
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
        import json

        variables = kwargs.get("variables") or {}
        payload = {
            "To": kwargs["to_number"],
            "From": from_number,
            "ContentSid": kwargs["template_id"],
            "ContentVariables": json.dumps(variables),
        }
        try:
            status, body = await _request(
                "POST",
                f"/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
                data=payload,
            )
            if status >= 400 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"Templated SMS queued to {kwargs['to_number']}: "
                    f"sid={body.get('sid')} status={body.get('status')}"
                ),
                data={
                    "sid": body.get("sid"),
                    "status": body.get("status"),
                    "template_id": kwargs["template_id"],
                },
            )
        except Exception as e:
            logger.error("sms_send_template failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class SmsStatusTool(BaseTool):
    """Get delivery status for a previously-sent message."""

    name = "sms_status"
    description = (
        "Fetch current delivery status for a Twilio message by SID. "
        "Typical lifecycle: queued → sending → sent → delivered (or failed, "
        "undelivered). Use this to reconcile long-running deliveries or "
        "after a webhook misses."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message_sid": {
                    "type": "string",
                    "description": "Message SID returned by sms_send/sms_send_template.",
                }
            },
            "required": ["message_sid"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        sid = kwargs["message_sid"]
        try:
            status, body = await _request(
                "GET",
                f"/Accounts/{TWILIO_ACCOUNT_SID}/Messages/{sid}.json",
            )
            if status >= 400 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"{sid}: {body.get('status')} "
                    f"(error_code={body.get('error_code')})"
                ),
                data={
                    "sid": body.get("sid"),
                    "status": body.get("status"),
                    "error_code": body.get("error_code"),
                    "error_message": body.get("error_message"),
                    "date_sent": body.get("date_sent"),
                    "price": body.get("price"),
                    "price_unit": body.get("price_unit"),
                },
            )
        except Exception as e:
            logger.error("sms_status failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class SmsListMessagesTool(BaseTool):
    """List recent SMS messages from the Twilio account."""

    name = "sms_list_messages"
    description = (
        "List recent SMS messages. Filter by ``to`` or ``from_`` (E.164) "
        "and/or ``date_after`` (ISO-8601 date, e.g. 2026-04-01). Useful "
        "for reconciling a conversation thread or auditing sends."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "from_": {"type": "string"},
                "date_after": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD). Twilio interprets "
                    "as DateSent>=.",
                },
                "limit": {"type": "integer", "default": 50, "maximum": 1000},
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        params: dict[str, Any] = {
            "PageSize": min(int(kwargs.get("limit", 50)), 1000),
        }
        if kwargs.get("to"):
            params["To"] = kwargs["to"]
        if kwargs.get("from_"):
            params["From"] = kwargs["from_"]
        if kwargs.get("date_after"):
            params["DateSent>"] = kwargs["date_after"]
        try:
            status, body = await _request(
                "GET",
                f"/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
                params=params,
            )
            if status >= 400 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            messages = body.get("messages") or []
            summary = [
                {
                    "sid": m.get("sid"),
                    "to": m.get("to"),
                    "from": m.get("from"),
                    "status": m.get("status"),
                    "date_sent": m.get("date_sent"),
                    "body": (m.get("body") or "")[:200],
                }
                for m in messages
            ]
            return ToolResult(
                success=True,
                output=f"Found {len(summary)} message(s).",
                data={"messages": summary},
            )
        except Exception as e:
            logger.error("sms_list_messages failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_twilio_sms_tools() -> list[BaseTool]:
    """Return the Twilio SMS tool set."""
    return [
        SmsSendTool(),
        SmsSendTemplateTool(),
        SmsStatusTool(),
        SmsListMessagesTool(),
    ]
