"""Billing tools for the Ledger Node — revenue-generating agent actions."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

DHANAM_API_URL = os.environ.get("DHANAM_API_URL", "")
DHANAM_API_TOKEN = os.environ.get("DHANAM_API_TOKEN", "")


class CreateCheckoutLinkTool(BaseTool):
    """Create a Stripe checkout link via Dhanam for a customer.

    This is a revenue-generating action — the returned URL, when visited
    by a customer, initiates a payment flow. Category: BILLING_WRITE.
    """

    name = "create_checkout_link"
    description = (
        "Create a Stripe payment checkout link for a customer via Dhanam. "
        "Returns a URL that the customer can visit to complete payment. "
        "Use this when you need to send a payment link to a lead or customer."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "product": {
                    "type": "string",
                    "description": "Product slug (e.g., 'karafiel', 'dhanam', 'selva')",
                },
                "plan": {
                    "type": "string",
                    "description": "Plan tier (e.g., 'contador', 'pro', 'essentials')",
                },
                "customer_email": {
                    "type": "string",
                    "description": "Customer's email address",
                },
                "success_url": {
                    "type": "string",
                    "description": "URL to redirect after successful payment",
                    "default": "https://madfam.io/gracias",
                },
            },
            "required": ["product", "plan", "customer_email"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not DHANAM_API_URL:
            return ToolResult(success=False, error="DHANAM_API_URL not configured")

        product = kwargs.get("product", "")
        plan = kwargs.get("plan", "")
        email = kwargs.get("customer_email", "")
        success_url = kwargs.get("success_url", "https://madfam.io/gracias")

        plan_slug = f"{product}_{plan}" if not plan.startswith(product) else plan

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{DHANAM_API_URL}/v1/billing/checkout",
                    params={
                        "plan": plan_slug,
                        "user_id": email,
                        "return_url": success_url,
                        "product": product,
                    },
                    follow_redirects=False,
                )

                if resp.status_code == 302:
                    checkout_url = resp.headers.get("location", "")
                    return ToolResult(
                        success=True,
                        output=f"Checkout link created: {checkout_url}",
                        data={"checkout_url": checkout_url, "plan": plan_slug, "email": email},
                    )

                return ToolResult(
                    success=False,
                    error=f"Dhanam returned {resp.status_code}: {resp.text[:200]}",
                )
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Checkout link creation failed: {exc}")


class GetRevenueMetricsTool(BaseTool):
    """Read MRR, ARR, churn rate, and subscriber counts from Dhanam.

    Read-only financial intelligence for the Ledger Node. Category: API_CALL.
    """

    name = "get_revenue_metrics"
    description = (
        "Get current revenue metrics: MRR, ARR, subscribers by tier, churn rate. "
        "Use this when reporting on financial performance or making budget decisions."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not DHANAM_API_URL:
            return ToolResult(success=False, error="DHANAM_API_URL not configured")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {}
                if DHANAM_API_TOKEN:
                    headers["Authorization"] = f"Bearer {DHANAM_API_TOKEN}"

                resp = await client.get(
                    f"{DHANAM_API_URL}/v1/billing/admin/revenue-metrics",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            metrics = data
            summary = (
                f"MRR: ${metrics.get('mrr', 0):.2f} | "
                f"ARR: ${metrics.get('arr', 0):.2f} | "
                f"Churn: {metrics.get('churnRate', 0):.1%} | "
                f"Subscribers: {metrics.get('totalSubscribers', 0)}"
            )

            return ToolResult(success=True, output=summary, data=metrics)
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Revenue metrics fetch failed: {exc}")
