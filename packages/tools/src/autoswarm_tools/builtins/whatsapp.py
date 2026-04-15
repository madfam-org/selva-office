"""WhatsApp Business API template messaging tool."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Pre-approved template catalog for Mexican business workflows
TEMPLATE_CATALOG: dict[str, dict[str, Any]] = {
    "factura_enviada": {
        "name": "factura_enviada",
        "language": "es_MX",
        "description": "Invoice sent notification with CFDI UUID and amount",
        "parameters": ["customer_name", "cfdi_uuid", "total_amount", "download_url"],
    },
    "recordatorio_pago": {
        "name": "recordatorio_pago",
        "language": "es_MX",
        "description": "Payment reminder with due date and amount",
        "parameters": ["customer_name", "invoice_number", "amount_due", "due_date"],
    },
    "confirmacion_pedido": {
        "name": "confirmacion_pedido",
        "language": "es_MX",
        "description": "Order confirmation with order number and estimated delivery",
        "parameters": ["customer_name", "order_number", "estimated_delivery"],
    },
    "cotizacion_lista": {
        "name": "cotizacion_lista",
        "language": "es_MX",
        "description": "Quotation ready notification with link to view",
        "parameters": ["customer_name", "quotation_number", "valid_until", "view_url"],
    },
}


class WhatsAppTemplateTool(BaseTool):
    """Send pre-approved WhatsApp Business template messages via Meta Cloud API."""

    name = "whatsapp_send_template"
    description = (
        "Send a pre-approved WhatsApp Business template message. "
        "Available templates: factura_enviada, recordatorio_pago, "
        "confirmacion_pedido, cotizacion_lista."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": (
                        "Recipient phone number in E.164 format "
                        "(e.g., +5215512345678)"
                    ),
                },
                "template_name": {
                    "type": "string",
                    "enum": list(TEMPLATE_CATALOG.keys()),
                    "description": "Name of the pre-approved template to send",
                },
                "parameters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Template parameter values in order",
                },
                "language": {
                    "type": "string",
                    "default": "es_MX",
                    "description": "Template language code",
                },
            },
            "required": ["phone", "template_name", "parameters"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        phone = kwargs.get("phone", "")
        template_name = kwargs.get("template_name", "")
        parameters: list[str] = kwargs.get("parameters", [])
        language = kwargs.get("language", "es_MX")

        if not phone:
            return ToolResult(success=False, error="Phone number is required")

        if template_name not in TEMPLATE_CATALOG:
            return ToolResult(
                success=False,
                error=(
                    f"Unknown template: {template_name}. "
                    f"Available: {list(TEMPLATE_CATALOG.keys())}"
                ),
            )

        access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
        phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")

        if not access_token or not phone_number_id:
            return ToolResult(
                success=False,
                error="WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID required",
            )

        # Build template message payload per Meta Business API spec
        template_components: list[dict[str, Any]] = []
        if parameters:
            template_components.append({
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(p)} for p in parameters
                ],
            })

        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": template_components,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"https://graph.facebook.com/v18.0/{phone_number_id}/messages",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                message_id = data.get("messages", [{}])[0].get("id", "")
                return ToolResult(
                    success=True,
                    output=f"Template '{template_name}' sent to {phone}",
                    data={
                        "message_id": message_id,
                        "template": template_name,
                        "phone": phone,
                    },
                )
        except Exception as exc:
            logger.warning("WhatsApp template send failed: %s", exc)
            return ToolResult(success=False, error=str(exc))
