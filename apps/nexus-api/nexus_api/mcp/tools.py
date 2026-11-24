"""``inference_usage`` (RFC 0051 catalog: ``inference.usage(org, month)``).

Serves exactly ``GET /api/v1/billing/inference-usage``: the same service
function (``services.inference_usage_report.build_inference_usage_report``),
the same org scoping (the org of the verified token; ``org`` may only name it)
and the same RLS-scoped session (``database.tenant_session``). Its
``outputSchema`` is that route's response model.
"""

from __future__ import annotations

from typing import Any

from ..database import tenant_session
from ..schemas.inference_usage import InferenceUsageReport
from ..services.inference_usage_report import (
    MONTH_PATTERN,
    InvalidMonthError,
    build_inference_usage_report,
)
from .registry import ToolContext, ToolError, ToolSpec, object_schema

INFERENCE_USAGE_DESCRIPTION = (
    "Inference usage of one organization in one civil month (America/Mexico_City), read "
    "from Selva's compute token ledger: request count and tokens by provider, model and "
    "caller class, and list_price_estimate_usd, the sum of each call's LIST-PRICE "
    "ESTIMATE in USD from a public provider price table. That figure is not cash, not "
    "an invoice and not COGS; do not convert it. funding is 'unattributed' (paid and "
    "credit-grant-funded calls are not told apart yet). The ledger stores total tokens "
    "only, so input/output are null. status 'empty' means no rows were recorded, which "
    "is not proof of zero usage; totals are then null. 'org' must be your client's own "
    "organization."
)


async def inference_usage(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    if arguments["org"] != context.org_id:
        raise ToolError("org_not_visible", "org is outside your client's organization")
    try:
        async with tenant_session(org_id=context.org_id) as db:
            report = await build_inference_usage_report(
                db, org_id=context.org_id, month=arguments["month"]
            )
    except InvalidMonthError as exc:
        raise ToolError(exc.code, exc.message) from exc
    return report.model_dump(mode="json")


INFERENCE_USAGE = ToolSpec(
    name="inference_usage",
    title="inference.usage",
    description=INFERENCE_USAGE_DESCRIPTION,
    input_schema=object_schema(
        {
            "org": {
                "type": "string",
                "maxLength": 255,
                "description": "Organization id; must be the org your machine client is bound to.",
            },
            "month": {
                "type": "string",
                "pattern": MONTH_PATTERN,
                "description": "Civil month YYYY-MM (America/Mexico_City); not in the future.",
            },
        },
        required=("org", "month"),
    ),
    output_schema=InferenceUsageReport.model_json_schema(mode="serialization"),
    handler=inference_usage,
)

TOOLS: dict[str, ToolSpec] = {spec.name: spec for spec in (INFERENCE_USAGE,)}
