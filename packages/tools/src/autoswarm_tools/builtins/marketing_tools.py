"""Marketing tools for the Growth Node — content distribution and email campaigns."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def _inject_utm(url: str, campaign: str = "", source: str = "selva", medium: str = "email") -> str:
    """Inject UTM tracking parameters into a URL for attribution."""
    if not url:
        return url
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    params.update({
        "utm_source": [source],
        "utm_medium": [medium],
        "utm_campaign": [campaign or "agent_outreach"],
    })
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


class SendMarketingEmailTool(BaseTool):
    """Send a marketing email with UTM tracking via Resend.

    Used by Growth Node agents (Heraldo, Nexo) for lead outreach,
    content distribution, and retention campaigns. All links in the
    email body are auto-tagged with UTM parameters for attribution.

    Category: MARKETING_SEND (requires playbook approval or HITL).
    """

    name = "send_marketing_email"
    description = (
        "Send a marketing email with UTM tracking for attribution. "
        "Use for lead outreach, content distribution, or retention campaigns. "
        "Links are auto-tagged with utm_source=selva for PostHog attribution."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to_email": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body_html": {
                    "type": "string",
                    "description": "Email body in HTML. Links will have UTM parameters injected.",
                },
                "utm_campaign": {
                    "type": "string",
                    "description": "UTM campaign name for attribution tracking",
                    "default": "agent_outreach",
                },
                "reply_to": {
                    "type": "string",
                    "description": "Reply-to address",
                    "default": "",
                },
            },
            "required": ["to_email", "subject", "body_html"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        api_key = os.environ.get("RESEND_API_KEY")
        from_addr = os.environ.get("EMAIL_FROM", "MADFAM <hola@madfam.io>")

        if not api_key:
            return ToolResult(
                success=False,
                error="RESEND_API_KEY not configured. Cannot send marketing email.",
            )

        to_email = kwargs.get("to_email", "")
        subject = kwargs.get("subject", "")
        body_html = kwargs.get("body_html", "")
        utm_campaign = kwargs.get("utm_campaign", "agent_outreach")
        reply_to = kwargs.get("reply_to", "")

        if not to_email or not subject:
            return ToolResult(success=False, error="to_email and subject are required")

        # Inject UTM into any links in the HTML body
        # Simple approach: find href="..." and append UTM params
        import re
        def _add_utm_to_link(match: re.Match) -> str:
            url = match.group(1)
            if url.startswith("mailto:") or url.startswith("#"):
                return match.group(0)
            tracked_url = _inject_utm(url, campaign=utm_campaign)
            return f'href="{tracked_url}"'

        tracked_body = re.sub(r'href="([^"]*)"', _add_utm_to_link, body_html)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                payload: dict[str, Any] = {
                    "from": from_addr,
                    "to": [to_email],
                    "subject": subject,
                    "html": tracked_body,
                }
                if reply_to:
                    payload["reply_to"] = reply_to

                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            # Track in PostHog if available
            try:
                from nexus_api.analytics import track
                track(to_email, "marketing_email_sent", {
                    "subject": subject,
                    "utm_campaign": utm_campaign,
                    "agent_tool": "send_marketing_email",
                })
            except Exception:
                pass

            email_id = data.get("id", "unknown")
            logger.info("Marketing email sent: to=%s subject=%s id=%s", to_email, subject, email_id)

            return ToolResult(
                success=True,
                output=f"Marketing email sent to {to_email}: '{subject}' (id: {email_id})",
                data={"email_id": email_id, "to": to_email, "utm_campaign": utm_campaign},
            )
        except httpx.HTTPError as exc:
            logger.error("Marketing email failed: %s", exc)
            return ToolResult(success=False, error=f"Email send failed: {exc}")
