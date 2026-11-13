"""The MCP-vs-API coverage contract (RFC 0051 standard §3).

Every route under ``GUARDED_PREFIXES`` (the API surfaces that read or write
the compute token ledger, usage, billing or provider spend) is listed here by
``"<METHOD> <path>"`` as COVERED by a tool or EXEMPTED with a reason.
``tests/test_mcp_coverage.py`` walks the live FastAPI app and fails when a
route is neither (a new endpoint cannot ship undecided), when an entry names a
route that no longer exists, or when a covered entry names a tool that does
not exist.
"""

from __future__ import annotations

GUARDED_PREFIXES: tuple[str, ...] = (
    "/api/v1/billing",
    "/api/v1/metrics",
    "/api/v1/convergence",
    "/api/v1/providers",
)

WRITE = "writes the ledger or billing state; Phase A is read-only (RFC 0051 §5)"
MONEY = "starts a customer payment or billing session (money movement, RFC 0051 §5)"
WEBHOOK = "signed inbound webhook from the billing service, not a read"
REVENUE = "revenue-side (what tenants are billed or subscribe to), not a cost input; Dhanam owns it"
BUDGET = "per-day token-budget gate, not a monthly usage read; inference_usage is the COGS read"
OPS = "trailing-window operations dashboard; the monthly ledger read is inference_usage"
ROW_LEVEL = "row-level per-task list for its own consumer; the monthly aggregate is inference_usage"
PLATFORM_ADMIN = (
    "MADFAM-private provider balances and credit grants (platform administrators only); "
    "not exposed to machine clients in Phase A"
)

COVERED: dict[str, str] = {
    "GET /api/v1/billing/inference-usage": "inference_usage",
}

EXEMPTED: dict[str, str] = {
    "GET /api/v1/billing/status": REVENUE,
    "GET /api/v1/billing/usage": BUDGET,
    "GET /api/v1/billing/tokens": BUDGET,
    "POST /api/v1/billing/portal": MONEY,
    "GET /api/v1/billing/agent-hours": REVENUE,
    "GET /api/v1/billing/tiers": REVENUE,
    "POST /api/v1/billing/checkout": MONEY,
    "POST /api/v1/billing/webhooks/dhanam": WEBHOOK,
    "POST /api/v1/billing/record": WRITE,
    "POST /api/v1/billing/check-budget": BUDGET,
    "GET /api/v1/metrics/dashboard": OPS,
    "GET /api/v1/metrics/roi": OPS,
    "GET /api/v1/convergence/ai-tasks": ROW_LEVEL,
    "GET /api/v1/providers/balance": PLATFORM_ADMIN,
    "GET /api/v1/providers/grants": PLATFORM_ADMIN,
}
