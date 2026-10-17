"""Executor for multi-step autopilot items (fan-out, refine, benchmark).

Each item runs under one *parent* swarm task (label ``credit-autopilot``).
Every target (fan-out entry, or eval prompt for a benchmark) gets a completed
*child* task (``parent_task_id`` = parent) holding its output and its steps.
Every call is metered with the parent task id, and its USD (cost model
estimate) is added to the item's ``SpendTally``; once the tally reaches
``budget_share × ceiling`` no new step starts and the item completes with
what it has. The parent's ``payload.credit_autopilot.progress`` is rewritten
after each target — the live per-item status the owner sees in the task view.

A retried item (after a failure or a dead pod) skips targets that already
have a completed child task and starts its tally from their recorded spend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from .credit_autopilot import (
    _SET_ORG_SQL,
    GENERATE_GRAPH_TYPE,
    LABEL,
    _create_task,
    _finish_task,
    _load_line_context,
    autopilot_org,
    fetch_context,
)
from .credit_autopilot_policy import TIER_MODELS, Selection
from .credit_autopilot_steps import (
    CRITIC_SYSTEM,
    DRAFT_SYSTEM,
    SpendTally,
    Target,
    critique_prompt,
    extract_json,
    revise_prompt,
    validate_eval_items,
)

logger = logging.getLogger(__name__)

#: Worst-case list price (USD per 1M tokens) used when the cost model is
#: unavailable, so the item budget errs on the safe side.
_FALLBACK_PRICE = (10.0, 50.0)

_INSERT_CHILD_SQL = """
INSERT INTO swarm_tasks (
    id, title, description, graph_type, assigned_agent_ids, payload, status,
    kanban_status, priority, labels, depends_on, org_id, retry_count,
    parent_task_id, created_at, updated_at, started_at, completed_at
) VALUES (
    CAST(:id AS uuid), :title, :description, :graph_type, CAST('[]' AS json),
    CAST(:payload AS json), :status, :kanban_status, 'medium', CAST(:labels AS json),
    CAST('[]' AS json), :org, 0, CAST(:parent AS uuid), NOW(), NOW(), NOW(), NOW()
)
"""

_PRIOR_SQL = """
SELECT payload::jsonb -> 'credit_autopilot' ->> 'target_id' AS target_id,
       COALESCE((payload::jsonb -> 'credit_autopilot' ->> 'spend_usd')::float, 0) AS spend
  FROM swarm_tasks
 WHERE org_id = :org AND parent_task_id IS NOT NULL
   AND status = 'completed' AND labels::jsonb ? :item_label
"""

_CHILD_RESULTS_SQL = """
SELECT payload::jsonb -> 'result' AS result
  FROM swarm_tasks
 WHERE org_id = :org AND parent_task_id IS NOT NULL
   AND status = 'completed' AND labels::jsonb ? :item_label
"""

_PROGRESS_SQL = """
UPDATE swarm_tasks SET payload = CAST(:payload AS json), updated_at = NOW()
 WHERE id = CAST(:id AS uuid) AND org_id = :org
"""

_SOURCE_SQL = """
SELECT payload FROM swarm_tasks
 WHERE org_id = :org AND parent_task_id IS NULL AND status = 'completed'
   AND labels::jsonb ? :item_label
 ORDER BY completed_at DESC NULLS LAST LIMIT 1
"""


def step_cost(provider: str, model: str, usage: dict[str, Any]) -> float:
    inp, out = int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)
    cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)
    cache_write = int(usage.get("cache_creation_input_tokens", 0) or 0)
    try:
        from madfam_budget_gate.cost_model import estimate_cost

        return float(
            estimate_cost(
                provider,
                model,
                inp,
                out,
                cache_read_tokens=cache_read,
                cache_creation_tokens=cache_write,
            )
        )
    except Exception:
        billable_in = inp + cache_read + cache_write
        return (billable_in * _FALLBACK_PRICE[0] + out * _FALLBACK_PRICE[1]) / 1_000_000


async def call_model(
    *,
    provider: str,
    model: str | None,
    prompt: str,
    system: str,
    max_tokens: int,
    org: str | None,
    task_id: str,
    task_type: str | None = None,
) -> dict[str, Any]:
    """One pinned router call, metered to ``task_id``. Raises on failure/empty."""
    from madfam_inference.types import InferenceRequest, RoutingPolicy, Sensitivity

    from ..inference import get_model_router
    from ..metering import meter_inference_call

    fields: dict[str, Any] = {
        "sensitivity": Sensitivity.INTERNAL,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "task_type": task_type,
        "provider_allowlist": [provider],
        "provider_models": {provider: model} if model else {},
    }
    if org is not None:
        # The tenant org (LP's RoutingPolicy.org_id): selects the org override
        # and lets the grant guard admit the call. None = global routing.
        fields["org_id"] = org
    request = InferenceRequest(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=system,
        policy=RoutingPolicy(**fields),
    )
    started = time.monotonic()
    response = await get_model_router().complete(request)
    latency_ms = int((time.monotonic() - started) * 1000)
    if not (response.content or "").strip():
        raise RuntimeError("empty completion")
    usage = dict(response.usage or {})
    meter_org = org or (autopilot_org() or "madfam")
    if usage:
        await meter_inference_call(
            usage=usage,
            provider=response.provider,
            model=response.model,
            task_id=task_id,
            org_id=meter_org,
            task_type=task_type,
        )
    return {
        "content": response.content,
        "provider": response.provider,
        "model": response.model,
        "usage": usage,
        "latency_ms": latency_ms,
        "cost_usd": round(step_cost(response.provider, response.model, usage), 6),
    }


class ItemRun:
    """State for one parent task run."""

    def __init__(
        self, engine: Any, org: str, sel: Selection, grant: Any, parent_id: str, payload: dict
    ) -> None:
        self.engine, self.org, self.sel, self.grant = engine, org, sel, grant
        self.parent_id, self.payload = parent_id, payload
        budget = float(sel.item.budget_share) * float(getattr(grant, "ceiling_usd", 0.0))
        self.tally = SpendTally(budget_usd=budget)
        self.done: set[str] = set()
        self.outputs: dict[str, dict[str, Any]] = {}
        self.failed: dict[str, str] = {}
        self.skipped_budget: list[str] = []
        self.total_targets = 0
        self._lock = asyncio.Lock()

    @property
    def provider(self) -> str:
        return str(getattr(self.grant, "provider", "anthropic"))

    async def load_prior(self) -> None:
        from sqlalchemy import text

        async with self.engine.begin() as conn:
            await conn.execute(text(_SET_ORG_SQL), {"org": self.org})
            rows = (
                (
                    await conn.execute(
                        text(_PRIOR_SQL),
                        {"org": self.org, "item_label": f"item:{self.sel.item.id}"},
                    )
                )
                .mappings()
                .all()
            )
        for row in rows:
            if row["target_id"]:
                self.done.add(str(row["target_id"]))
                self.tally.spent_usd += float(row["spend"] or 0.0)

    async def child_results(self) -> list[dict[str, Any]]:
        """Results of every completed target of this item, across attempts."""
        from sqlalchemy import text

        async with self.engine.begin() as conn:
            await conn.execute(text(_SET_ORG_SQL), {"org": self.org})
            rows = (
                await conn.execute(
                    text(_CHILD_RESULTS_SQL),
                    {"org": self.org, "item_label": f"item:{self.sel.item.id}"},
                )
            ).all()
        out: list[dict[str, Any]] = []
        for (raw,) in rows:
            value = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(value, dict):
                out.append(value)
        return out

    def charge(self, step: dict[str, Any], *, grant_spend: bool = True) -> None:
        if grant_spend:
            self.tally.add(float(step.get("cost_usd") or 0.0))
        else:
            self.tally.calls += 1

    async def save_child(self, target_id: str, result: dict[str, Any], spend: float) -> None:
        from sqlalchemy import text

        item = self.sel.item
        payload = {
            "credit_autopilot": {
                "item_id": item.id,
                "target_id": target_id,
                "spend_usd": round(spend, 6),
                "parent_task_id": self.parent_id,
            },
            "result": result,
        }
        async with self.engine.begin() as conn:
            await conn.execute(text(_SET_ORG_SQL), {"org": self.org})
            await conn.execute(
                text(_INSERT_CHILD_SQL),
                {
                    "id": str(uuid.uuid4()),
                    "title": f"[{LABEL}] {item.id} / {target_id}"[:200],
                    "description": f"[{LABEL}] {item.id}: {target_id}",
                    "graph_type": GENERATE_GRAPH_TYPE,
                    "payload": json.dumps(payload),
                    "status": "completed",
                    "kanban_status": "review",
                    "labels": json.dumps([LABEL, f"item:{item.id}", f"target:{target_id}"]),
                    "org": self.org,
                    "parent": self.parent_id,
                },
            )

    def progress(self) -> dict[str, Any]:
        return {
            "targets_total": self.total_targets,
            "targets_done": len(self.done),
            "targets_failed": len(self.failed),
            "targets_skipped_budget": len(self.skipped_budget),
            "calls": self.tally.calls,
            "spend_usd": round(self.tally.spent_usd, 4),
            "budget_usd": round(self.tally.budget_usd, 4),
            "budget_reached": self.tally.exhausted(),
        }

    async def push_progress(self) -> None:
        from sqlalchemy import text

        self.payload["credit_autopilot"]["progress"] = self.progress()
        async with self.engine.begin() as conn:
            await conn.execute(text(_SET_ORG_SQL), {"org": self.org})
            await conn.execute(
                text(_PROGRESS_SQL),
                {"id": self.parent_id, "org": self.org, "payload": json.dumps(self.payload)},
            )


# -- generate (fan-out + refine) -------------------------------------------------


def _base_prompt(
    run: ItemRun, target: Target, files: list[tuple[str, str]], missing: list[str]
) -> str:
    item = run.sel.item
    context_block = "\n\n".join(f"### FILE {label}\n```\n{body}\n```" for label, body in files)
    acceptance = "\n".join(f"- {a}" for a in item.acceptance)
    target_line = f"Target: {target.id}. {target.brief}\n\n" if target.id != item.id else ""
    return (
        f"{_load_line_context(item.line)}\n\n{target_line}Objective: {item.objective}\n\n"
        f"Deliverable: {item.deliverable}\n\nAcceptance criteria:\n{acceptance}\n\n"
        + (f"Missing context (say so, do not invent): {', '.join(missing)}\n\n" if missing else "")
        + (f"Context files:\n\n{context_block}" if context_block else "")
    )


async def run_target(run: ItemRun, target: Target) -> None:
    item, sel = run.sel.item, run.sel
    if run.tally.exhausted():
        run.skipped_budget.append(target.id)
        return
    files, missing = await fetch_context(item.context + target.context)
    if (item.context or target.context) and not files:
        run.failed[target.id] = f"no context could be fetched: {', '.join(missing)}"
        return
    base = _base_prompt(run, target, files, missing)
    if item.output == "json":
        base += (
            f"\n\nReturn ONLY a JSON list of at least {item.json_min_items} objects with keys "
            '"prompt", "reference_points" (list of strings), "rubric" (string).'
        )
    context_block = "\n\n".join(f"### {label}\n{body}" for label, body in files)
    steps: list[dict[str, Any]] = []
    spend = 0.0

    async def step(kind: str, model: str, prompt: str, system: str) -> dict[str, Any]:
        nonlocal spend
        out = await call_model(
            provider=run.provider,
            model=model,
            prompt=prompt,
            system=system,
            max_tokens=item.max_output_tokens,
            org=run.org,
            task_id=run.parent_id,
        )
        async with run._lock:
            run.charge(out)
        spend += out["cost_usd"]
        steps.append(
            {k: out[k] for k in ("model", "usage", "latency_ms", "cost_usd")} | {"kind": kind}
        )
        return out

    try:
        draft = (await step("draft", sel.model, base, DRAFT_SYSTEM))["content"]
        critiques: list[str] = []
        result: dict[str, Any] = {}
        if item.output == "json":
            try:
                result["eval_items"] = validate_eval_items(
                    extract_json(draft), target.id, item.json_min_items
                )
            except ValueError as exc:
                if run.tally.exhausted():
                    raise
                repair = (
                    f"{base}\n\nYour previous reply was invalid ({exc}). "
                    "Reply with the JSON list only."
                )
                draft = (await step("repair", sel.model, repair, DRAFT_SYSTEM))["content"]
                result["eval_items"] = validate_eval_items(
                    extract_json(draft), target.id, item.json_min_items
                )
        else:
            for _ in range(item.refine_rounds):
                if run.tally.exhausted():
                    break
                critique = (
                    await step(
                        "critique",
                        TIER_MODELS["opus"],
                        critique_prompt(item.acceptance, draft, context_block),
                        CRITIC_SYSTEM,
                    )
                )["content"]
                critiques.append(critique)
                if run.tally.exhausted():
                    break
                draft = (
                    await step(
                        "revise", sel.model, revise_prompt(base, draft, critique), DRAFT_SYSTEM
                    )
                )["content"]
        result.update(
            {
                "content": draft,
                "critiques": critiques,
                "steps": steps,
                "context_files": [label for label, _ in files],
                "missing_context": missing,
            }
        )
    except Exception as exc:
        run.failed[target.id] = f"{exc.__class__.__name__}: {exc}"[:500]
        return
    await run.save_child(target.id, result, spend)
    run.done.add(target.id)
    run.outputs[target.id] = result


async def run_fanout(run: ItemRun) -> dict[str, Any]:
    targets = run.sel.item.targets()
    run.total_targets = len(targets)
    pending = [t for t in targets if t.id not in run.done]
    sem = asyncio.Semaphore(run.sel.item.parallel)

    async def guarded(target: Target) -> None:
        async with sem:
            await run_target(run, target)
            await run.push_progress()

    await asyncio.gather(*(guarded(t) for t in pending))
    result: dict[str, Any] = {"progress": run.progress(), "failed": run.failed}
    if run.sel.item.output == "json":
        results = await run.child_results() or list(run.outputs.values())
        result["eval_set"] = [e for out in results for e in out.get("eval_items", [])]
    if len(targets) == 1 and run.outputs:
        result["content"] = next(iter(run.outputs.values()))["content"]
    else:
        result["children"] = sorted(run.outputs)
    return result


async def run_item(engine: Any, org: str, sel: Selection, grant: Any) -> None:
    """Run one generate/benchmark item end to end under a parent task."""
    parent_id, payload = await _create_task(engine, org, sel, grant.id, generate=True)
    run = ItemRun(engine, org, sel, grant, parent_id, payload)
    try:
        await run.load_prior()
        if sel.item.mode == "benchmark":
            from .credit_autopilot_bench import run_benchmark

            result = await run_benchmark(run)
        else:
            result = await run_fanout(run)
    except Exception as exc:
        logger.warning("credit autopilot item %s failed: %s", sel.item.id, exc)
        payload["credit_autopilot"]["progress"] = run.progress()
        payload["result"] = {"error": f"{exc.__class__.__name__}: {exc}"[:2000]}
        await _finish_task(engine, org, parent_id, payload, ok=False, error=str(exc))
        return
    payload["credit_autopilot"]["progress"] = run.progress()
    payload["result"] = result
    ok = bool(run.done) or not run.failed
    await _finish_task(
        engine,
        org,
        parent_id,
        payload,
        ok=ok,
        error=None if ok else "; ".join(f"{k}: {v}" for k, v in run.failed.items())[:2000],
    )
    logger.info(
        "credit autopilot item %s finished (task %s): %s", sel.item.id, parent_id, run.progress()
    )
