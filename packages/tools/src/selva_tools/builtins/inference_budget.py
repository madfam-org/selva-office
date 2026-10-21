"""inference_budget_status — how much prepaid provider credit Selva has left.

Reads the provider credit-grant meter (``madfam_inference.grants``, contract
C2) so the platform swarm can pace its own inference spend: remaining USD,
burn over the last hour, the hourly rate needed to use the credit before it
expires, and a pace verdict. Amounts are MADFAM-private, so the tool is
PLATFORM audience: tenant swarms never see it in their spec list, and the
audience guard refuses it at execute time.

Read-only. It never calls a provider and never sees a key — only the grant
declaration and the Redis meter the router already keeps.
"""

from __future__ import annotations

from typing import Any

from ..audience import Audience
from ..base import BaseTool, ToolResult


class InferenceBudgetStatusTool(BaseTool):
    name = "inference_budget_status"
    description = (
        "Report Selva's prepaid provider credit grants: remaining and spent USD, "
        "in-flight reservations, seconds to expiry, USD burned over the last 60 "
        "minutes, the USD/hour needed to use the rest before expiry, and pace_status "
        "(behind | on_pace | ahead | exhausted | expired | unknown). Read-only."
    )
    audience = Audience.PLATFORM

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "grant_id": {
                    "type": "string",
                    "description": "Only report this grant (default: every declared grant).",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            from madfam_inference.grants import get_grant_statuses
        except ImportError:
            return ToolResult(
                success=False,
                error="madfam_inference is not installed in this process; no grant meter.",
            )
        try:
            statuses = await get_grant_statuses()
        except Exception as exc:  # meter errors are already logged by the guard
            return ToolResult(
                success=False, error=f"Could not read the grant meter: {type(exc).__name__}"
            )
        grant_id = kwargs.get("grant_id")
        if grant_id:
            statuses = [s for s in statuses if s.id == grant_id]
        grants = [s.model_dump(mode="json") for s in statuses]
        if not grants:
            return ToolResult(
                output="No provider credit grant is declared"
                + (f" with id {grant_id!r}." if grant_id else "."),
                data={"grants": []},
            )
        lines = []
        for s in grants:
            if not s["meter_ok"]:
                lines.append(f"- {s['id']} ({s['provider']}): meter unavailable — status unknown")
                continue
            lines.append(
                f"- {s['id']} ({s['provider']}): {s['remaining_usd']:.2f} USD remaining of "
                f"{s['ceiling_usd']:.2f}; burn {s['burn_usd_per_hour_60m']:.2f}/h vs "
                f"required {s['required_usd_per_hour'] or 0:.2f}/h; "
                f"{s['seconds_to_expiry']} s to expiry; pace {s['pace_status']}"
            )
        return ToolResult(output="\n".join(lines), data={"grants": grants})


def get_inference_budget_tools() -> list[BaseTool]:
    return [InferenceBudgetStatusTool()]
