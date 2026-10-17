"""Benchmark mode for the credit autopilot (see credit_autopilot_exec).

Takes the eval set produced by the item named in ``benchmark.source_item``,
answers every prompt with each candidate (opus / sonnet / haiku under the
grant, plus the tenant's normal route for comparison), grades all answers in
one blind comparative call per judge (opus primary, optional sonnet second
judge with inter-judge agreement) per prompt, and writes a per-task-
type table (quality, latency, USD, quality per USD) plus a proposed
``org_overrides`` block as the item's deliverable.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .credit_autopilot import _SET_ORG_SQL
from .credit_autopilot_exec import _SOURCE_SQL, ItemRun, call_model
from .credit_autopilot_policy import TIER_MODELS
from .credit_autopilot_steps import (
    BENCHMARK_ANTHROPIC,
    JUDGE_SYSTEM,
    aggregate,
    blind_labels,
    judge_agreement,
    judge_prompt,
    parse_judge_scores,
    propose_assignments,
    render_report,
)


def tenant_default_route(task_type: str) -> tuple[str, str] | None:
    """The tenant's normal (global org-config) provider/model for a task type."""
    from ..inference import get_model_router

    org_config = getattr(get_model_router(), "_org_config", None)
    assignments = getattr(org_config, "model_assignments", None) or {}
    assignment = assignments.get(task_type) if hasattr(assignments, "get") else None
    if assignment is None:
        return None
    return str(assignment.provider), str(assignment.model)


async def _load_eval_set(run: ItemRun, source_item: str) -> list[dict[str, Any]]:
    from sqlalchemy import text

    async with run.engine.begin() as conn:
        await conn.execute(text(_SET_ORG_SQL), {"org": run.org})
        row = (
            await conn.execute(
                text(_SOURCE_SQL), {"org": run.org, "item_label": f"item:{source_item}"}
            )
        ).first()
    if row is None:
        raise RuntimeError(f"no completed {source_item} task to benchmark")
    payload = row[0] if not isinstance(row[0], str) else json.loads(row[0])
    items = ((payload or {}).get("result") or {}).get("eval_set") or []
    if not items:
        raise RuntimeError(f"{source_item} produced no eval_set")
    return list(items)


async def bench_prompt(
    run: ItemRun,
    ev: dict[str, Any],
    candidates: dict[str, tuple[str, str]],
    judges: tuple[str, ...] = ("opus",),
) -> None:
    if run.tally.exhausted():
        run.skipped_budget.append(ev["id"])
        return
    answers: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    spend = 0.0
    for cand, (provider, model) in candidates.items():
        grant_call = provider == run.provider
        try:
            out = await call_model(
                provider=provider,
                model=model,
                prompt=str(ev["prompt"]),
                system="Answer the task as well as you can.",
                max_tokens=2000,
                org=run.org if grant_call else None,
                task_id=run.parent_id,
                task_type=str(ev["task_type"]),
            )
        except Exception as exc:
            answers[cand] = {"error": f"{exc.__class__.__name__}: {exc}"[:300]}
            continue
        async with run._lock:
            run.charge(out, grant_spend=grant_call)
        spend += out["cost_usd"] if grant_call else 0.0
        answers[cand] = out
    answered = [c for c, a in answers.items() if "content" in a]
    # Judges: the first is primary (drives the proposal); the others are
    # reported alongside it with inter-judge agreement.
    scores_by_judge: dict[str, dict[str, float]] = {}
    judge_meta: dict[str, Any] = {}
    if answered:
        labels = blind_labels(str(ev["id"]), answered)
        prompt = judge_prompt(ev, {lab: answers[c]["content"] for lab, c in labels.items()})
        judge_meta["labels"] = labels
        for judge_tier in judges:
            if run.tally.exhausted():
                break
            try:
                judge = await call_model(
                    provider=run.provider,
                    model=TIER_MODELS[judge_tier],
                    prompt=prompt,
                    system=JUDGE_SYSTEM,
                    max_tokens=600,
                    org=run.org,
                    task_id=run.parent_id,
                )
                async with run._lock:
                    run.charge(judge)
                spend += judge["cost_usd"]
                scores_by_judge[judge_tier] = parse_judge_scores(judge["content"], labels)
                judge_meta[judge_tier] = {
                    "cost_usd": judge["cost_usd"],
                    "raw": judge["content"][:1000],
                }
            except Exception as exc:
                judge_meta[judge_tier] = {"error": f"{exc.__class__.__name__}: {exc}"[:300]}
    primary = scores_by_judge.get(judges[0], {}) if judges else {}
    for cand in answered:
        a = answers[cand]
        rows.append(
            {
                "task_type": ev["task_type"],
                "candidate": cand,
                "provider": a["provider"],
                "model": a["model"],
                "quality": primary.get(cand),
                "quality_by_judge": {j: sc.get(cand) for j, sc in scores_by_judge.items()},
                "latency_ms": a["latency_ms"],
                "cost_usd": a["cost_usd"],
            }
        )
    result = {
        "eval_id": ev["id"],
        "rows": rows,
        "answers": {c: {k: v for k, v in a.items() if k != "usage"} for c, a in answers.items()},
        "judge": judge_meta,
    }
    await run.save_child(str(ev["id"]), result, spend)
    run.done.add(str(ev["id"]))
    run.outputs[str(ev["id"])] = result


async def run_benchmark(run: ItemRun) -> dict[str, Any]:
    cfg = dict(run.sel.item.benchmark)
    evals = await _load_eval_set(run, str(cfg["source_item"]))
    per_type = int(cfg.get("per_task_type", 20))
    picked: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for ev in evals:
        tt = str(ev.get("task_type"))
        if counts.get(tt, 0) < per_type:
            counts[tt] = counts.get(tt, 0) + 1
            picked.append(ev)
    run.total_targets = len(picked)
    tiers = [str(t) for t in cfg.get("models", ["opus", "sonnet", "haiku"])]
    judges = tuple(str(j) for j in cfg.get("judges", ["opus"]) if str(j) in TIER_MODELS)
    sem = asyncio.Semaphore(run.sel.item.parallel)

    async def guarded(ev: dict[str, Any]) -> None:
        candidates = {
            t: (run.provider, BENCHMARK_ANTHROPIC[t]) for t in tiers if t in BENCHMARK_ANTHROPIC
        }
        if cfg.get("tenant_default", True):
            route = tenant_default_route(str(ev["task_type"]))
            if route is not None and route[0] != run.provider:
                candidates["tenant_default"] = route
        async with sem:
            await bench_prompt(run, ev, candidates, judges or ("opus",))
            await run.push_progress()

    await asyncio.gather(*(guarded(ev) for ev in picked if str(ev["id"]) not in run.done))
    results = await run.child_results() or list(run.outputs.values())
    rows = [r for out in results for r in out.get("rows", [])]
    table = aggregate(rows)
    proposal = propose_assignments(table)
    agreement = judge_agreement(rows, judges)
    return {
        "content": render_report(table, proposal, run.org, agreement=agreement, judges=judges),
        "judge_agreement": agreement,
        "proposal": proposal,
        "progress": run.progress(),
        "prompts_scored": len(results),
    }
