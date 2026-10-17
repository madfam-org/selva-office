"""Pure helpers for multi-step autopilot items: budget tally, prompts, JSON
parsing, and benchmark scoring/aggregation. No I/O.

An item runs as steps:

* ``fanout`` — one *target* per entry (a service, repo file, task type…),
  each its own call and its own child task.
* ``refine`` — per target: draft → critique (opus-tier critic against the
  item's acceptance criteria) → revise, ``refine_rounds`` times.
* ``benchmark`` — per eval prompt: one answer per candidate model, then one
  blind comparative judge call that scores every answer against the rubric.

Every step's USD is added to the item's ``SpendTally``; once the tally reaches
the item budget (``budget_share × ceiling``) no new step starts and the item
completes with what it has, so one item cannot eat the grant.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

#: Benchmark candidate label -> (provider, model). ``tenant_default`` is the
#: tenant's normal (global org-config) route, resolved at run time.
BENCHMARK_ANTHROPIC = {
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
}
EVAL_TASK_TYPES = ("planning", "coding", "review", "research", "crm", "support")


@dataclass
class SpendTally:
    """Item-level USD tally against the item budget."""

    budget_usd: float
    spent_usd: float = 0.0
    calls: int = 0

    def exhausted(self) -> bool:
        return self.spent_usd >= self.budget_usd

    def add(self, usd: float) -> None:
        self.spent_usd += max(0.0, usd)
        self.calls += 1


@dataclass(frozen=True)
class Target:
    id: str
    brief: str = ""
    context: tuple[tuple[str, str], ...] = ()


def targets_for(raw_fanout: Any, item_id: str) -> list[Target]:
    """Normalise an item's ``fanout`` list (absent -> one implicit target)."""
    if not raw_fanout:
        return [Target(id=item_id)]
    out: list[Target] = []
    seen: set[str] = set()
    for entry in raw_fanout:
        if isinstance(entry, str):
            entry = {"id": entry}
        if not isinstance(entry, Mapping) or not entry.get("id"):
            raise ValueError(f"{item_id}: fanout entries need an id")
        tid = str(entry["id"])
        if tid in seen:
            raise ValueError(f"{item_id}: duplicate fanout id {tid!r}")
        seen.add(tid)
        ctx = tuple(
            (str(c["repo"]), str(c["path"]))
            for c in entry.get("context") or []
            if isinstance(c, Mapping) and c.get("repo") and c.get("path")
        )
        out.append(
            Target(id=tid, brief=" ".join(str(entry.get("brief") or "").split()), context=ctx)
        )
    return out


def estimate_calls(
    n_targets: int, refine_rounds: int, *, mode: str = "generate", candidates: int = 4
) -> int:
    """Upper-bound call count for an item (used for docs and planning)."""
    if mode == "benchmark":
        return n_targets * (candidates + 1)
    if mode == "dispatch":
        return 3
    return n_targets * (1 + 2 * max(0, refine_rounds))


# -- prompts -------------------------------------------------------------------

DRAFT_SYSTEM = (
    "You are a senior engineer in MADFAM's own Selva tenant producing a reviewable draft. "
    "Output only the deliverable (Markdown; JSON/YAML in fenced blocks). Never invent "
    "endpoints, prices, customers or facts that are not in the context; list unknowns as "
    "open questions. Do not include monetary amounts."
)
CRITIC_SYSTEM = (
    "You are an exacting reviewer. Check the draft strictly against the acceptance criteria "
    "and the provided context. List concrete defects (unsupported claims, missing sections, "
    "invented facts, criteria not met) as numbered items with the fix for each. Do not "
    "rewrite the draft."
)
JUDGE_SYSTEM = (
    "You grade answers against a rubric. Score each labelled answer from 0.0 to 1.0 "
    "independently against the rubric and reference points; ignore length and style unless "
    "the rubric asks for them. Reply with JSON only: "
    '{"scores": {"A": 0.0, ...}, "notes": "one short sentence"}.'
)


def critique_prompt(acceptance: Sequence[str], draft: str, context_block: str) -> str:
    crit = "\n".join(f"- {a}" for a in acceptance) or "- (none stated)"
    return f"Acceptance criteria:\n{crit}\n\nDraft:\n\n{draft}\n\n" + (
        f"Context the draft must be faithful to:\n\n{context_block}" if context_block else ""
    )


def revise_prompt(base_prompt: str, draft: str, critique: str) -> str:
    return (
        f"{base_prompt}\n\nYour previous draft:\n\n{draft}\n\nReviewer findings to fix:\n\n"
        f"{critique}\n\nProduce the complete revised deliverable (not a diff)."
    )


def judge_prompt(item: Mapping[str, Any], labelled: Mapping[str, str]) -> str:
    answers = "\n\n".join(f"### Answer {label}\n{text}" for label, text in labelled.items())
    refs = item.get("reference_points") or []
    ref_block = "\n".join(f"- {r}" for r in refs) if isinstance(refs, list) else str(refs)
    return (
        f"Task type: {item.get('task_type')}\n\nPrompt:\n{item.get('prompt')}\n\n"
        f"Reference points:\n{ref_block}\n\nRubric:\n{item.get('rubric')}\n\n{answers}"
    )


# -- JSON ------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Parse the first JSON value in ``text`` (fenced or bare). Raises ValueError."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for chunk in candidates:
        chunk = chunk.strip()
        for opener, closer in (("[", "]"), ("{", "}")):
            start, end = chunk.find(opener), chunk.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(chunk[start : end + 1])
                except json.JSONDecodeError:
                    continue
    raise ValueError("no JSON value found")


def validate_eval_items(data: Any, task_type: str, min_items: int) -> list[dict[str, Any]]:
    """Return clean eval items for ``task_type`` or raise ValueError."""
    if isinstance(data, Mapping):
        data = data.get("items")
    if not isinstance(data, list):
        raise ValueError("expected a JSON list of eval items")
    items: list[dict[str, Any]] = []
    for n, raw in enumerate(data):
        if not isinstance(raw, Mapping):
            continue
        prompt, rubric = str(raw.get("prompt") or "").strip(), raw.get("rubric")
        if not prompt or not rubric:
            continue
        refs = raw.get("reference_points") or []
        items.append(
            {
                "id": f"{task_type}-{n + 1:03d}",
                "task_type": task_type,
                "prompt": prompt,
                "reference_points": [str(r) for r in refs] if isinstance(refs, list) else [],
                "rubric": rubric if isinstance(rubric, str) else json.dumps(rubric),
            }
        )
    if len(items) < min_items:
        raise ValueError(f"{task_type}: {len(items)} valid items < {min_items}")
    return items


# -- benchmark -------------------------------------------------------------------


def blind_labels(eval_id: str, candidates: Sequence[str]) -> dict[str, str]:
    """Deterministic shuffled label -> candidate map (judge never sees model names)."""
    order = sorted(candidates, key=lambda c: hashlib.sha256(f"{eval_id}:{c}".encode()).hexdigest())
    return {chr(ord("A") + i): c for i, c in enumerate(order)}


def parse_judge_scores(text: str, labels: Mapping[str, str]) -> dict[str, float]:
    """Map judge JSON back to candidate -> score in [0, 1]. Raises ValueError."""
    data = extract_json(text)
    scores = data.get("scores") if isinstance(data, Mapping) else None
    if not isinstance(scores, Mapping):
        raise ValueError("judge reply has no 'scores' object")
    out: dict[str, float] = {}
    for label, candidate in labels.items():
        value = scores.get(label)
        if value is None:
            continue
        out[candidate] = min(1.0, max(0.0, float(value)))
    if not out:
        raise ValueError("judge scored no answers")
    return out


@dataclass
class ModelStats:
    task_type: str
    candidate: str
    provider: str
    model: str
    qualities: list[float] = field(default_factory=list)
    latencies_ms: list[int] = field(default_factory=list)
    costs_usd: list[float] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.qualities)

    @property
    def mean_quality(self) -> float:
        return statistics.fmean(self.qualities) if self.qualities else 0.0

    @property
    def p50_latency_ms(self) -> float:
        return float(statistics.median(self.latencies_ms)) if self.latencies_ms else 0.0

    @property
    def total_usd(self) -> float:
        return sum(self.costs_usd)

    @property
    def mean_usd(self) -> float:
        return statistics.fmean(self.costs_usd) if self.costs_usd else 0.0

    @property
    def quality_per_dollar(self) -> float | None:
        return self.mean_quality / self.mean_usd if self.mean_usd > 0 else None


def aggregate(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, ModelStats]]:
    """rows: {task_type, candidate, provider, model, quality, latency_ms, cost_usd}."""
    table: dict[str, dict[str, ModelStats]] = {}
    for row in rows:
        if row.get("quality") is None:
            continue
        tt, cand = str(row["task_type"]), str(row["candidate"])
        stats = table.setdefault(tt, {}).setdefault(
            cand, ModelStats(tt, cand, str(row.get("provider", "")), str(row.get("model", "")))
        )
        stats.qualities.append(float(row["quality"]))
        stats.latencies_ms.append(int(row.get("latency_ms") or 0))
        stats.costs_usd.append(float(row.get("cost_usd") or 0.0))
    return table


def propose_assignments(
    table: Mapping[str, Mapping[str, ModelStats]], tolerance: float = 0.05, min_n: int = 5
) -> dict[str, dict[str, str]]:
    """Per task type: the cheapest model within ``tolerance`` of the best quality."""
    proposal: dict[str, dict[str, str]] = {}
    for tt, by_cand in sorted(table.items()):
        eligible = [s for s in by_cand.values() if s.n >= min_n]
        if not eligible:
            continue
        best = max(s.mean_quality for s in eligible)
        near = [s for s in eligible if s.mean_quality >= best - tolerance]
        pick = min(near, key=lambda s: (s.mean_usd, -s.mean_quality))
        proposal[tt] = {"provider": pick.provider, "model": pick.model}
    return proposal


def render_report(
    table: Mapping[str, Mapping[str, ModelStats]],
    proposal: Mapping[str, Mapping[str, str]],
    org_key: str,
) -> str:
    """Markdown table + proposed org_overrides YAML (the benchmark deliverable)."""
    import yaml

    lines = [
        "| task type | candidate | model | n | quality | p50 latency (ms) | USD total | USD/call "
        "| quality per USD |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for tt, by_cand in sorted(table.items()):
        for s in sorted(by_cand.values(), key=lambda x: -x.mean_quality):
            qpd = f"{s.quality_per_dollar:.1f}" if s.quality_per_dollar is not None else "n/a"
            lines.append(
                f"| {tt} | {s.candidate} | {s.model} | {s.n} | {s.mean_quality:.3f} | "
                f"{s.p50_latency_ms:.0f} | {s.total_usd:.4f} | {s.mean_usd:.5f} | {qpd} |"
            )
    overrides = {"org_overrides": {org_key: {"model_assignments": dict(proposal)}}}
    return (
        "## Routing benchmark\n\n" + "\n".join(lines) + "\n\n## Proposed org-config override "
        "(cheapest model within 0.05 of the best quality per task type)\n\n```yaml\n"
        + yaml.safe_dump(overrides, sort_keys=True)
        + "```\n"
    )
