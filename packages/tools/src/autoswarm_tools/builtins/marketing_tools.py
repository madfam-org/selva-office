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


def _build_madfam_email_html(
    body_text: str,
    cta_url: str = "",
    cta_text: str = "Comienza ahora",
    product_name: str = "",
) -> str:
    """Wrap email content in a MADFAM-branded HTML template.

    Uses table-based layout for Outlook/Gmail/Apple Mail compatibility.
    All styles are inline (no <style> block).
    """
    cta_block = ""
    if cta_url:
        cta_block = f'''
        <tr>
          <td style="padding:24px;text-align:center">
            <a href="{cta_url}" style="display:inline-block;background-color:#f6d55c;color:#1a1a2e;padding:14px 32px;text-decoration:none;border-radius:6px;font-weight:bold;font-family:Arial,sans-serif;font-size:16px">{cta_text}</a>
          </td>
        </tr>'''

    product_line = f' — {product_name}' if product_name else ''

    # Convert plain text paragraphs to HTML if not already HTML
    if '<' not in body_text:
        body_html = ''.join(f'<p style="margin:0 0 16px">{p.strip()}</p>' for p in body_text.split('\n\n') if p.strip())
    else:
        body_html = body_text

    return f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#f0f0f5;font-family:Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f0f0f5">
  <tr><td align="center" style="padding:24px 16px">
    <!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0"><tr><td><![endif]-->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background-color:#ffffff;border-radius:8px;overflow:hidden">
      <tr>
        <td style="padding:28px 24px;background-color:#1a1a2e;text-align:center">
          <h1 style="color:#f6d55c;font-family:Arial,sans-serif;font-size:22px;margin:0;letter-spacing:1px">MADFAM{product_line}</h1>
          <p style="color:#a0a0b0;font-size:12px;margin:8px 0 0;font-family:Arial,sans-serif">Tecnología que potencia tu negocio</p>
        </td>
      </tr>
      <tr>
        <td style="padding:32px 24px;font-family:Arial,sans-serif;font-size:16px;line-height:1.6;color:#333333">
          {body_html}
        </td>
      </tr>
      {cta_block}
      <tr>
        <td style="padding:20px 24px;background-color:#f5f5f5;text-align:center;font-family:Arial,sans-serif">
          <p style="font-size:12px;color:#888888;margin:0">By Innovaciones MADFAM · <a href="https://madfam.io" style="color:#888888">madfam.io</a></p>
          <p style="font-size:11px;color:#aaaaaa;margin:8px 0 0"><a href="https://madfam.io/unsubscribe" style="color:#aaaaaa">Cancelar suscripción</a></p>
        </td>
      </tr>
    </table>
    <!--[if mso]></td></tr></table><![endif]-->
  </td></tr>
</table>
</body>
</html>'''


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

        # Wrap in MADFAM branded template (unless raw HTML with full <html> tag)
        template = kwargs.get("template", "madfam")
        cta_url = kwargs.get("cta_url", "")
        cta_text = kwargs.get("cta_text", "Comienza ahora")
        product_name = kwargs.get("product_name", "")
        if template == "madfam" and "<!DOCTYPE" not in body_html and "<html" not in body_html:
            body_html = _build_madfam_email_html(body_html, cta_url, cta_text, product_name)

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
