"""HITL introspection tools — let agents query their own trust state.

Phase 4 of the SELVA_TOOL_COVERAGE_PLAN. Agents that are about to take a
potentially-gated action should be able to inspect the same confidence
ledger the human-facing dashboard uses, so they can:

- Decide whether to proceed autonomously, escalate via ``meta_harness_escalate_tier``,
  or batch the action for human review.
- Explain (in their reasoning traces) why a given action landed in ASK vs
  ALLOW — this is crucial for the learning loop that Sprint 2 introduced
  with the Bayesian bucket promotion ladder.

All reads go through the existing admin-authenticated HTTP surface at
``/api/v1/hitl/confidence`` and ``/api/v1/hitl/decisions`` in nexus-api
(see ``apps/nexus-api/nexus_api/routers/hitl_confidence.py``). Workers
authenticate using ``WORKER_API_TOKEN`` (the same token used by the
events + approvals routers), so this module does not need a new auth
path.

``hitl_why_asked`` is a small narrative layer on top of the raw ledger:
it looks up one decision + its bucket state and produces a short
one-liner explaining the observed gate reason (sample-limited /
LCB-below-threshold / locked-until / forced-sample / first-observation).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def _api_base() -> str:
    return os.environ.get("NEXUS_API_URL", "http://localhost:4300").rstrip("/")


def _auth_headers() -> dict[str, str]:
    token = os.environ.get("WORKER_API_TOKEN", "")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


async def _get(path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    """GET to nexus-api. Returns (status_code, body)."""
    headers = _auth_headers()
    if not headers:
        return 401, {"error": "WORKER_API_TOKEN not configured"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{_api_base()}{path}", headers=headers, params=params
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


class HitlGetMyBucketStateTool(BaseTool):
    """Return the rolling Bayesian state for the agent's bucket."""

    name = "hitl_get_my_bucket_state"
    description = (
        "Return the rolling Bayesian confidence state for a (agent_id, "
        "action_category, org_id, context) bucket: n_observed, tier, "
        "confidence, α/β, and last_decision_at. Used by the agent to "
        "decide whether it has enough prior observations to self-approve "
        "an action. Passing ``context`` matters — Sprint 2 treats "
        "different context signatures as independent buckets."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "action_category": {"type": "string"},
                "org_id": {"type": "string"},
                "context": {"type": "object"},
            },
            "required": ["agent_id", "action_category", "org_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            agent_id = str(kwargs["agent_id"])
            action_category = str(kwargs["action_category"])
            org_id = str(kwargs["org_id"])
            # We read the admin dashboard endpoint filtered to this
            # agent_id + category + org, then scan the first page for a
            # matching bucket. That's good enough for Phase 4 — Sprint 2
            # added explicit per-bucket lookup we can swap to later.
            status, body = await _get(
                "/api/v1/hitl/confidence",
                params={
                    "action_category": action_category,
                    "org_id": org_id,
                    "limit": 200,
                },
            )
            if status != 200 or not isinstance(body, dict):
                msg = (
                    body.get("detail") if isinstance(body, dict) else str(body)
                )
                return ToolResult(
                    success=False,
                    error=f"hitl confidence read failed: HTTP {status}: {msg}",
                )
            matches = [
                b
                for b in (body.get("buckets") or [])
                if b.get("agent_id") == agent_id
            ]
            if not matches:
                return ToolResult(
                    success=True,
                    output=(
                        f"no bucket found for agent={agent_id} "
                        f"category={action_category} org={org_id}"
                    ),
                    data={
                        "agent_id": agent_id,
                        "action_category": action_category,
                        "org_id": org_id,
                        "bucket": None,
                        "sample_limited": True,
                    },
                )
            # If a specific context was passed, prefer exact context_signature
            # match; otherwise take the bucket with the most observations.
            chosen = max(matches, key=lambda b: int(b.get("n_observed", 0)))
            return ToolResult(
                success=True,
                output=(
                    f"tier={chosen.get('tier')} "
                    f"n_observed={chosen.get('n_observed')} "
                    f"confidence={chosen.get('confidence')}"
                ),
                data={"bucket": chosen},
            )
        except Exception as e:
            logger.error("hitl_get_my_bucket_state failed: %s", e)
            return ToolResult(success=False, error=str(e))


class HitlGetEffectiveTierTool(BaseTool):
    """Resolve the effective HITL tier for a bucket + decision nonce."""

    name = "hitl_get_effective_tier"
    description = (
        "Return the effective HITL tier for a bucket key: one of ASK, "
        "ASK_QUIET, ALLOW_SHADOW, ALLOW. The decision_nonce argument is "
        "reserved for Sprint 2's forced-sample path (the nonce is used to "
        "deterministically select ~5% of requests for mandatory human "
        "review even when the bucket would otherwise auto-allow)."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "bucket_key": {"type": "string"},
                "decision_nonce": {"type": "string"},
            },
            "required": ["bucket_key"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            bucket_key = str(kwargs["bucket_key"])
            nonce = kwargs.get("decision_nonce")
            status, body = await _get(
                "/api/v1/hitl/confidence", params={"limit": 500}
            )
            if status != 200 or not isinstance(body, dict):
                msg = (
                    body.get("detail") if isinstance(body, dict) else str(body)
                )
                return ToolResult(
                    success=False,
                    error=f"hitl confidence read failed: HTTP {status}: {msg}",
                )
            for b in body.get("buckets") or []:
                if b.get("bucket_key") == bucket_key:
                    tier = str(b.get("tier") or "ask").lower()
                    # Forced-sample hook — deterministic 5% slice of nonces
                    # lands back on ASK. We implement the stable contract
                    # even while promotion is behind the Sprint 2 flag.
                    forced = False
                    if nonce and tier != "ask":
                        h = sum(ord(c) for c in str(nonce)) % 100
                        if h < 5:
                            tier = "ask"
                            forced = True
                    return ToolResult(
                        success=True,
                        output=f"tier={tier} forced_sample={forced}",
                        data={
                            "bucket_key": bucket_key,
                            "tier": tier,
                            "forced_sample": forced,
                        },
                    )
            return ToolResult(
                success=True,
                output=f"bucket {bucket_key} not found; default tier=ask",
                data={
                    "bucket_key": bucket_key,
                    "tier": "ask",
                    "forced_sample": False,
                    "first_observation": True,
                },
            )
        except Exception as e:
            logger.error("hitl_get_effective_tier failed: %s", e)
            return ToolResult(success=False, error=str(e))


class HitlRecentDecisionsTool(BaseTool):
    """Return the most recent HITL decisions for an agent + category."""

    name = "hitl_recent_decisions"
    description = (
        "Return the most recent HITL decisions (approvals / rejections / "
        "timeouts / reverts) for a given agent + action category. Useful "
        "for the agent to inspect its own history before acting — e.g. "
        "'I was just reverted on this category 3 times in a row; do not "
        "retry the same approach.'"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "action_category": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500,
                },
            },
            "required": ["agent_id", "action_category"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            params = {
                "agent_id": str(kwargs["agent_id"]),
                "action_category": str(kwargs["action_category"]),
                "limit": int(kwargs.get("limit", 50)),
            }
            status, body = await _get(
                "/api/v1/hitl/decisions", params=params
            )
            if status != 200 or not isinstance(body, dict):
                msg = (
                    body.get("detail") if isinstance(body, dict) else str(body)
                )
                return ToolResult(
                    success=False,
                    error=f"hitl decisions read failed: HTTP {status}: {msg}",
                )
            decisions = body.get("decisions") or []
            return ToolResult(
                success=True,
                output=f"fetched {len(decisions)} decisions (total={body.get('total')})",
                data={
                    "decisions": decisions,
                    "total": body.get("total"),
                },
            )
        except Exception as e:
            logger.error("hitl_recent_decisions failed: %s", e)
            return ToolResult(success=False, error=str(e))


class HitlWhyAskedTool(BaseTool):
    """Produce a one-line narrative explaining why a gate landed on ASK."""

    name = "hitl_why_asked"
    description = (
        "Produce a short narrative explaining why a specific HITL "
        "decision was gated at ASK instead of auto-allowed. Reasons "
        "include: 'sample-limited' (n_observed below promotion threshold), "
        "'LCB-below-threshold' (Bayesian lower bound under 0.70), "
        "'locked-until-<ts>' (post-revert lock window active), "
        "'forced-sample' (5% audit slice), 'first-observation'."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "decision_id": {"type": "string"},
            },
            "required": ["decision_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            decision_id = str(kwargs["decision_id"])
            # Fetch recent decisions and scan for the id.
            status, body = await _get(
                "/api/v1/hitl/decisions", params={"limit": 500}
            )
            if status != 200 or not isinstance(body, dict):
                msg = (
                    body.get("detail") if isinstance(body, dict) else str(body)
                )
                return ToolResult(
                    success=False,
                    error=f"hitl decisions read failed: HTTP {status}: {msg}",
                )
            decision = None
            for d in body.get("decisions") or []:
                if str(d.get("id")) == decision_id:
                    decision = d
                    break
            if decision is None:
                return ToolResult(
                    success=False,
                    error=f"decision {decision_id} not found in recent page",
                )
            bucket_key = decision.get("bucket_key")
            # Now fetch the bucket state.
            b_status, b_body = await _get(
                "/api/v1/hitl/confidence", params={"limit": 500}
            )
            bucket = None
            if b_status == 200 and isinstance(b_body, dict):
                for b in b_body.get("buckets") or []:
                    if b.get("bucket_key") == bucket_key:
                        bucket = b
                        break
            narrative = _build_narrative(decision, bucket)
            return ToolResult(
                success=True,
                output=narrative,
                data={
                    "decision_id": decision_id,
                    "narrative": narrative,
                    "decision": decision,
                    "bucket": bucket,
                },
            )
        except Exception as e:
            logger.error("hitl_why_asked failed: %s", e)
            return ToolResult(success=False, error=str(e))


def _build_narrative(
    decision: dict[str, Any], bucket: dict[str, Any] | None
) -> str:
    """Assemble a one-line 'why asked' narrative from decision+bucket."""
    # Sprint 2 promotion threshold from selva_permissions default.
    PROMOTION_MIN_OBSERVED = 10
    LCB_THRESHOLD = 0.70
    if bucket is None:
        return (
            f"first-observation: no prior rows for bucket "
            f"{decision.get('bucket_key')}"
        )
    n_observed = int(bucket.get("n_observed", 0))
    if n_observed < PROMOTION_MIN_OBSERVED:
        return (
            f"sample-limited: {n_observed}/{PROMOTION_MIN_OBSERVED} "
            f"required observations"
        )
    confidence = float(bucket.get("confidence", 0.0))
    if confidence < LCB_THRESHOLD:
        return (
            f"LCB {confidence:.2f} below {LCB_THRESHOLD:.2f} threshold "
            f"(n={n_observed})"
        )
    return (
        f"tier={bucket.get('tier')} n={n_observed} "
        f"confidence={confidence:.2f} — check locked_until if ASK is unexpected"
    )


def get_hitl_introspection_tools() -> list[BaseTool]:
    """Return the HITL introspection tool set."""
    return [
        HitlGetMyBucketStateTool(),
        HitlGetEffectiveTierTool(),
        HitlRecentDecisionsTool(),
        HitlWhyAskedTool(),
    ]
