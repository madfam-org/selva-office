"""Operations tools -- pedimento lookup, carrier tracking, inventory check."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..audience import Audience
from ..base import BaseTool, ToolResult
from .service_auth import PRAVARA_EDGE, http_error_detail, machine_auth_headers

logger = logging.getLogger(__name__)

_VALID_CARRIERS = ("estafeta", "fedex", "dhl", "paquetexpress")


class PedimentoLookupTool(BaseTool):
    name = "pedimento_lookup"
    description = "Look up customs pedimento document via Karafiel SAT module"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "numero": {
                    "type": "string",
                    "description": ("Pedimento number (e.g. '26 48 3180 6001234')"),
                },
            },
            "required": ["numero"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        numero: str = kwargs.get("numero", "").strip()
        if not numero:
            return ToolResult(success=False, error="numero is required")

        try:
            from madfam_inference.adapters.karafiel import KarafielAdapter

            adapter = KarafielAdapter()
            result = await adapter.get_pedimento(numero)
            return ToolResult(
                success=True,
                output=f"Pedimento {numero}: {result.get('status', 'found')}",
                data=result,
            )
        except ImportError:
            return ToolResult(
                success=False,
                error="Karafiel adapter not available. Install madfam-inference.",
            )
        except Exception as exc:
            logger.warning("Pedimento lookup failed for %s: %s", numero, exc)
            return ToolResult(success=False, error=str(exc))


class CarrierTrackingTool(BaseTool):
    name = "carrier_tracking"
    description = (
        "Track shipment status with Mexican carriers (Estafeta, FedEx MX, DHL, PaqueteExpress)"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "carrier": {
                    "type": "string",
                    "enum": list(_VALID_CARRIERS),
                    "description": "Carrier name",
                },
                "tracking_number": {
                    "type": "string",
                    "description": "Shipment tracking number",
                },
            },
            "required": ["carrier", "tracking_number"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        carrier: str = kwargs.get("carrier", "").lower().strip()
        tracking_number: str = kwargs.get("tracking_number", "").strip()

        if not carrier or not tracking_number:
            return ToolResult(success=False, error="carrier and tracking_number are required")

        if carrier not in _VALID_CARRIERS:
            return ToolResult(
                success=False,
                error=f"Unsupported carrier '{carrier}'. Valid: {', '.join(_VALID_CARRIERS)}",
            )

        # Check if the carrier API key is configured
        env_key_map = {
            "estafeta": "ESTAFETA_API_KEY",
            "fedex": "FEDEX_MX_API_KEY",
            "dhl": "DHL_API_KEY",
            "paquetexpress": "PAQUETEXPRESS_API_KEY",
        }
        api_key_var = env_key_map.get(carrier, "")
        api_key = os.environ.get(api_key_var, "")

        if not api_key:
            return ToolResult(
                success=True,
                output=(
                    f"Carrier tracking for {carrier} / {tracking_number}: "
                    "tracking_service_not_configured"
                ),
                data={
                    "carrier": carrier,
                    "tracking_number": tracking_number,
                    "status": "tracking_service_not_configured",
                    "message": (
                        f"Set {api_key_var} environment variable to enable {carrier} tracking."
                    ),
                },
            )

        # Future enhancement: actual carrier API integration
        return ToolResult(
            success=True,
            output=(
                f"Carrier tracking for {carrier} / {tracking_number}: "
                "tracking_service_not_configured"
            ),
            data={
                "carrier": carrier,
                "tracking_number": tracking_number,
                "status": "tracking_service_not_configured",
                "message": "Full carrier API integration is a future enhancement.",
            },
        )


class InventoryCheckTool(BaseTool):
    """Read a SKU's stock level from Pravara-MES (read-only).

    Calls ``GET /v1/inventory?search=<sku>`` (Pravara matches name or SKU) and
    keeps the items whose SKU matches exactly. Pravara-MES has no warehouse
    dimension. Its machine route table serves ``GET /v1/inventory`` to Janua
    machine tokens holding ``pravara-mes:read``, and it reads only the
    inventory of the organization the token is bound to.

    PLATFORM audience: the read uses Selva's own Pravara identity.
    """

    name = "inventory_check"
    description = "Check the stock level of a SKU in Pravara-MES (read-only)."
    audience = Audience.PLATFORM

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "Product SKU to check",
                },
            },
            "required": ["sku"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        sku = str(kwargs.get("sku") or "").strip()
        if not sku:
            return ToolResult(success=False, error="sku is required")

        pravara_url = os.environ.get("PRAVARA_MES_API_URL", "")
        if not pravara_url:
            return ToolResult(
                success=True,
                output=f"Inventory for SKU {sku}: inventory service not configured",
                data={
                    "sku": sku,
                    "status": "inventory_service_not_configured",
                    "message": (
                        "Set PRAVARA_MES_API_URL and Pravara service credentials to enable "
                        "inventory checks."
                    ),
                },
            )

        headers, refusal = await machine_auth_headers(PRAVARA_EDGE)
        if refusal is not None:
            return refusal

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{pravara_url.rstrip('/')}/v1/inventory",
                    params={"search": sku, "limit": "100"},
                    headers=headers,
                )
                resp.raise_for_status()
                body = resp.json()
        except httpx.HTTPError as exc:
            error = f"Pravara inventory read failed: {http_error_detail(exc)}"
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 403:
                error += (
                    ". Pravara-MES serves /v1/inventory to machine tokens that hold "
                    "pravara-mes:read and are bound to an organization; API keys need "
                    "pravara-mes:read or the wildcard scope."
                )
            return ToolResult(success=False, error=error)
        except ValueError:
            return ToolResult(
                success=False, error="Pravara inventory read failed: response is not JSON"
            )

        items = body.get("data") if isinstance(body, dict) else None
        matches = (
            [item for item in items if isinstance(item, dict) and item.get("sku") == sku]
            if isinstance(items, list)
            else []
        )
        if not matches:
            return ToolResult(
                success=True,
                output=f"No Pravara-MES inventory item has SKU {sku}.",
                data={"sku": sku, "status": "not_found", "items": []},
            )
        item = matches[0]
        output = (
            f"Inventory for SKU {sku}: {item.get('quantity_available', 'N/A')} "
            f"{item.get('unit') or 'units'} available "
            f"({item.get('quantity_on_hand', 'N/A')} on hand, "
            f"{item.get('quantity_reserved', 'N/A')} reserved)."
        )
        if kwargs.get("warehouse"):
            output += " Pravara-MES has no warehouse dimension; these are totals."
        return ToolResult(
            success=True,
            output=output,
            data={"sku": sku, "status": "found", "items": matches},
        )
