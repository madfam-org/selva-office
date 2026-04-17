"""Product catalog tool -- queries MADFAM product catalog from Dhanam API."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

DHANAM_API_URL = os.environ.get("DHANAM_API_URL", "")


class ProductCatalogTool(BaseTool):
    """Query the MADFAM product catalog.

    Returns product information including tiers, pricing, features,
    and credit costs. Agents use this to answer questions like
    "what products do we offer?" or "how much does Karafiel cost?"
    """

    name = "product_catalog"
    description = (
        "Query the MADFAM product catalog to get information about "
        "products, pricing tiers, features, and credit costs. "
        "Use this when asked about MADFAM products, pricing, or features."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "product_slug": {
                    "type": "string",
                    "description": (
                        "Optional product slug to get details for a specific product "
                        "(e.g., 'karafiel', 'dhanam', 'selva', 'tezca', 'forgesight', 'fortuna'). "
                        "Omit to get the full catalog."
                    ),
                },
                "query_type": {
                    "type": "string",
                    "enum": ["catalog", "credit_costs"],
                    "description": (
                        "Type of query: 'catalog' for full product info with pricing and features, "
                        "'credit_costs' for per-operation credit costs only."
                    ),
                    "default": "catalog",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        dhanam_url = DHANAM_API_URL
        if not dhanam_url:
            return ToolResult(
                success=False,
                error="DHANAM_API_URL not configured. Set the environment variable.",
            )

        product_slug = kwargs.get("product_slug")
        query_type = kwargs.get("query_type", "catalog")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if product_slug:
                    if query_type == "credit_costs":
                        url = f"{dhanam_url}/v1/billing/catalog/{product_slug}/credit-costs"
                    else:
                        url = f"{dhanam_url}/v1/billing/catalog/{product_slug}"
                else:
                    url = f"{dhanam_url}/v1/billing/catalog"

                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            return ToolResult(
                success=True,
                output=self._format_output(data, product_slug, query_type),
                data=data,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return ToolResult(
                    success=False,
                    error=f"Product '{product_slug}' not found in catalog.",
                )
            logger.warning("Product catalog query failed: %s", exc)
            return ToolResult(success=False, error=f"Catalog query failed: {exc}")
        except httpx.HTTPError as exc:
            logger.warning("Product catalog request failed: %s", exc)
            return ToolResult(success=False, error=f"Network error: {exc}")

    def _format_output(self, data: Any, slug: str | None, query_type: str) -> str:
        if query_type == "credit_costs" and isinstance(data, list):
            if not data:
                return f"No credit costs defined for '{slug}'."
            lines = [f"Credit costs for {slug}:"]
            for cost in data:
                lines.append(f"  - {cost['operation']}: {cost['credits']} credits")
            return "\n".join(lines)

        if slug and isinstance(data, dict):
            return self._format_product(data)

        # Full catalog
        products = data.get("products", []) if isinstance(data, dict) else []
        if not products:
            return "No products in the catalog."

        lines = [f"MADFAM Product Catalog ({len(products)} products):\n"]
        for product in products:
            lines.append(self._format_product(product))
            lines.append("")
        return "\n".join(lines)

    def _format_product(self, product: dict) -> str:
        lines = [f"## {product.get('name', '?')} ({product.get('slug', '?')})"]
        if product.get("description"):
            lines.append(f"  {product['description']}")
        if product.get("websiteUrl"):
            lines.append(f"  Website: {product['websiteUrl']}")

        tiers = product.get("tiers", [])
        if tiers:
            lines.append("  Tiers:")
            for tier in tiers:
                name = tier.get("displayName") or tier.get("tierSlug", "?")
                prices = tier.get("prices", {})
                price_parts = []
                for currency, p in prices.items():
                    if p.get("monthly"):
                        price_parts.append(f"{currency} {p['monthly'] / 100:.2f}/mo")
                    if p.get("yearly"):
                        price_parts.append(f"{currency} {p['yearly'] / 100:.2f}/yr")
                price_str = ", ".join(price_parts) if price_parts else "Custom"
                lines.append(f"    - {name}: {price_str}")
                features = tier.get("features", [])
                for feature in features[:5]:
                    lines.append(f"      * {feature}")
                if len(features) > 5:
                    lines.append(f"      ... and {len(features) - 5} more")

        costs = product.get("creditCosts", [])
        if costs:
            lines.append("  Credit costs:")
            for cost in costs:
                lines.append(f"    - {cost['operation']}: {cost['credits']} credits")

        return "\n".join(lines)
