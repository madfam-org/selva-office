"""Tests for multi-step autopilot items: fan-out, refine, budget stop, benchmark."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Any

import pytest

from selva_workers.jobs import credit_autopilot_bench as bench
from selva_workers.jobs import credit_autopilot_exec as ex
from selva_workers.jobs.credit_autopilot_policy import (
    TIER_MODELS,
    AutopilotConfig,
    BacklogError,
    BacklogItem,
    GrantView,
    ItemState,
    Selection,
    parse_backlog,
    plan_dispatch,
)
from selva_workers.jobs.credit_autopilot_steps import (
    SpendTally,
    Target,
    aggregate,
    blind_labels,
    estimate_calls,
    extract_json,
    judge_agreement,
    parse_judge_scores,
    propose_assignments,
    render_report,
    targets_for,
    validate_eval_items,
)

GRANT = GrantView("g", "anthropic", 100.0, 80.0, 36000, "behind", 5.0, 8.0, True)


def make_item(**kw: Any) -> BacklogItem:
    base = BacklogItem(
        id="it",
        rank=1,
        line="software",
        mode="generate",
        tiers=("sonnet", "opus"),
        budget_share=0.10,
        acceptance=("criterion",),
    )
    return replace(base, **kw)


class FakeModel:
    """Stands in for ``call_model``: records calls, returns canned replies."""

    def __init__(self, cost: float = 1.0, replies: dict[str, str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.cost = cost
        self.replies = replies or {}

    async def __call__(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        content = self.replies.get(kw["system"][:12], f"reply {len(self.calls)}")
        return {
            "content": content,
            "provider": kw["provider"],
            "model": kw["model"] or "default",
            "usage": {"input_tokens": 10, "output_tokens": 10},
            "latency_ms": 100 + len(self.calls),
            "cost_usd": self.cost,
        }


def make_run(item: BacklogItem, monkeypatch: pytest.MonkeyPatch, model: FakeModel) -> ex.ItemRun:
    sel = Selection(item=item, tier="sonnet", model=TIER_MODELS["sonnet"], reason="test")
    run = ex.ItemRun(None, "madfam", sel, GRANT, "parent-1", {"credit_autopilot": {}})
    saved: dict[str, Any] = {}

    async def save_child(target_id: str, result: dict[str, Any], spend: float) -> None:
        saved[target_id] = {"result": result, "spend": spend}

    async def noop() -> None:
        return None

    async def no_children() -> list[dict[str, Any]]:
        return [v["result"] for v in saved.values()]

    async def fetch(_ctx: Any) -> tuple[list[tuple[str, str]], list[str]]:
        return [("repo/file", "code")], []

    monkeypatch.setattr(run, "save_child", save_child)
    monkeypatch.setattr(run, "push_progress", noop)
    monkeypatch.setattr(run, "child_results", no_children)
    monkeypatch.setattr(ex, "fetch_context", fetch)
    monkeypatch.setattr(ex, "call_model", model)
    monkeypatch.setattr(bench, "call_model", model)
    monkeypatch.setattr(ex, "_load_line_context", lambda _l: "")
    run.saved = saved  # type: ignore[attr-defined]
    return run


# -- fan-out ---------------------------------------------------------------------


def test_targets_for_normalises_and_rejects_duplicates() -> None:
    assert targets_for(None, "x") == [Target(id="x")]
    got = targets_for(
        ["a", {"id": "b", "brief": "  two  words ", "context": [{"repo": "r", "path": "p"}]}], "x"
    )
    assert got[1] == Target(id="b", brief="two words", context=(("r", "p"),))
    with pytest.raises(ValueError, match="duplicate"):
        targets_for(["a", "a"], "x")


def test_fanout_runs_one_call_per_target_and_records_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = FakeModel(cost=0.5)
    item = make_item(fanout=(Target("a"), Target("b"), Target("c")))
    run = make_run(item, monkeypatch, model)
    result = asyncio.run(ex.run_fanout(run))
    assert len(model.calls) == 3
    assert sorted(run.saved) == ["a", "b", "c"]  # type: ignore[attr-defined]
    assert result["children"] == ["a", "b", "c"]
    assert run.tally.calls == 3 and run.tally.spent_usd == pytest.approx(1.5)
    # Every call is metered to the parent (item) task.
    assert {c["task_id"] for c in model.calls} == {"parent-1"}


def test_resume_skips_targets_completed_in_earlier_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = FakeModel()
    run = make_run(make_item(fanout=(Target("a"), Target("b"))), monkeypatch, model)
    run.done.add("a")
    asyncio.run(ex.run_fanout(run))
    assert len(model.calls) == 1 and "b" in run.saved  # type: ignore[attr-defined]


# -- refine ----------------------------------------------------------------------


def test_refine_drafts_critiques_with_opus_and_revises(monkeypatch: pytest.MonkeyPatch) -> None:
    model = FakeModel(cost=0.1)
    run = make_run(make_item(refine_rounds=2), monkeypatch, model)
    result = asyncio.run(ex.run_fanout(run))
    kinds = [c["system"][:12] for c in model.calls]
    assert len(model.calls) == 5  # draft + 2 × (critique + revise)
    critic_calls = [c for c in model.calls if c["system"].startswith("You are an exacting")]
    assert len(critic_calls) == 2 and all(c["model"] == TIER_MODELS["opus"] for c in critic_calls)
    drafts = [c for c in model.calls if c not in critic_calls]
    assert all(c["model"] == TIER_MODELS["sonnet"] for c in drafts)
    assert result["content"] == "reply 5"  # the last revision
    child = run.saved["it"]["result"]  # type: ignore[attr-defined]
    assert [s["kind"] for s in child["steps"]] == [
        "draft",
        "critique",
        "revise",
        "critique",
        "revise",
    ]
    assert len(child["critiques"]) == 2 and kinds


# -- per-item budget stop -----------------------------------------------------------


def test_item_stops_starting_steps_at_its_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    # budget = 0.10 × 100 = 10 USD; each call costs 4 USD.
    model = FakeModel(cost=4.0)
    item = make_item(fanout=tuple(Target(f"t{n}") for n in range(6)), parallel=1, refine_rounds=0)
    run = make_run(item, monkeypatch, model)
    result = asyncio.run(ex.run_fanout(run))
    assert len(model.calls) == 3  # 4 + 4 + 4 crosses 10, then no new step
    assert result["progress"]["budget_reached"] is True
    assert result["progress"]["targets_skipped_budget"] == 3


def test_budget_stop_cuts_refine_rounds_short(monkeypatch: pytest.MonkeyPatch) -> None:
    model = FakeModel(cost=6.0)
    run = make_run(make_item(refine_rounds=3), monkeypatch, model)
    asyncio.run(ex.run_fanout(run))
    assert len(model.calls) == 2  # draft (6) + critique (12 ≥ 10) -> stop before revise


def test_spend_tally() -> None:
    tally = SpendTally(budget_usd=1.0)
    tally.add(0.4)
    tally.add(-5)  # never negative
    assert not tally.exhausted() and tally.calls == 2
    tally.add(0.6)
    assert tally.exhausted()


# -- json eval set ----------------------------------------------------------------


def test_eval_set_items_validated_with_one_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    good = json.dumps(
        [{"prompt": f"p{n}", "rubric": "r", "reference_points": ["x"]} for n in range(3)]
    )
    replies = iter(["not json", good])

    class Seq(FakeModel):
        async def __call__(self, **kw: Any) -> dict[str, Any]:
            out = await super().__call__(**kw)
            out["content"] = next(replies)
            return out

    model = Seq()
    item = make_item(output="json", json_min_items=3, fanout=(Target("coding"),))
    run = make_run(item, monkeypatch, model)
    result = asyncio.run(ex.run_fanout(run))
    assert len(model.calls) == 2
    assert [e["id"] for e in result["eval_set"]] == ["coding-001", "coding-002", "coding-003"]


def test_validate_eval_items_rejects_short_sets() -> None:
    with pytest.raises(ValueError, match="< 2"):
        validate_eval_items([{"prompt": "p", "rubric": "r"}, {"prompt": ""}], "crm", 2)
    assert extract_json('text ```json\n{"a": 1}\n``` more') == {"a": 1}


# -- benchmark --------------------------------------------------------------------


def test_blind_labels_are_deterministic_and_hide_names() -> None:
    labels = blind_labels("e1", ["opus", "sonnet", "haiku", "tenant_default"])
    assert labels == blind_labels("e1", ["haiku", "opus", "tenant_default", "sonnet"])
    assert sorted(labels) == ["A", "B", "C", "D"]
    assert sorted(labels.values()) == ["haiku", "opus", "sonnet", "tenant_default"]


def test_parse_judge_scores_clamps_and_maps_back() -> None:
    labels = {"A": "opus", "B": "haiku"}
    scores = parse_judge_scores('```json\n{"scores": {"A": 1.4, "B": 0.25}}\n```', labels)
    assert scores == {"opus": 1.0, "haiku": 0.25}
    with pytest.raises(ValueError):
        parse_judge_scores('{"nope": 1}', labels)


def _rows() -> list[dict[str, Any]]:
    rows = []
    for n in range(6):
        rows += [
            {
                "task_type": "coding",
                "candidate": "opus",
                "provider": "anthropic",
                "model": "claude-opus-5-5",
                "quality": 0.90,
                "latency_ms": 900,
                "cost_usd": 0.02,
            },
            {
                "task_type": "coding",
                "candidate": "sonnet",
                "provider": "anthropic",
                "model": "claude-sonnet-5-5",
                "quality": 0.88,
                "latency_ms": 500,
                "cost_usd": 0.01,
            },
            {
                "task_type": "coding",
                "candidate": "haiku",
                "provider": "anthropic",
                "model": "claude-haiku-5-5",
                "quality": 0.60,
                "latency_ms": 200 + n,
                "cost_usd": 0.0005,
            },
            {
                "task_type": "crm",
                "candidate": "tenant_default",
                "provider": "deepinfra",
                "model": "llama",
                "quality": 0.70,
                "latency_ms": 300,
                "cost_usd": 0.0002,
            },
            {
                "task_type": "crm",
                "candidate": "opus",
                "provider": "anthropic",
                "model": "claude-opus-5-5",
                "quality": 0.72,
                "latency_ms": 800,
                "cost_usd": 0.02,
            },
        ]
    rows.append(
        {
            "task_type": "crm",
            "candidate": "haiku",
            "provider": "anthropic",
            "model": "claude-haiku-5-5",
            "quality": None,
            "latency_ms": 1,
            "cost_usd": 0.0,
        }
    )
    return rows


def test_aggregate_and_propose_cheapest_within_tolerance() -> None:
    table = aggregate(_rows())
    coding = table["coding"]
    assert coding["opus"].n == 6 and coding["opus"].mean_quality == pytest.approx(0.90)
    assert coding["sonnet"].quality_per_dollar == pytest.approx(88.0)
    assert "haiku" not in table["crm"]  # unjudged rows are excluded
    proposal = propose_assignments(table)
    assert proposal["coding"] == {"provider": "anthropic", "model": "claude-sonnet-5-5"}
    assert proposal["crm"] == {"provider": "deepinfra", "model": "llama"}
    report = render_report(table, proposal, "madfam")
    assert "| coding | sonnet | claude-sonnet-5-5 | 6 |" in report
    assert "org_overrides:" in report and "madfam:" in report


def test_bench_prompt_scores_all_candidates_and_keeps_tenant_spend_off_the_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = {
        "opus": ("anthropic", "claude-opus-5-5"),
        "tenant_default": ("deepinfra", "llama"),
    }
    labels = blind_labels("coding-001", list(candidates))
    inv = {v: k for k, v in labels.items()}
    judge_reply = json.dumps({"scores": {inv["opus"]: 0.9, inv["tenant_default"]: 0.5}})
    model = FakeModel(cost=0.01, replies={"You grade an": judge_reply})
    item = make_item(mode="benchmark", benchmark=(("source_item", "ev"),))
    run = make_run(item, monkeypatch, model)
    ev = {"id": "coding-001", "task_type": "coding", "prompt": "p", "rubric": "r"}
    asyncio.run(bench.bench_prompt(run, ev, candidates))
    assert len(model.calls) == 3  # two answers + one judge
    rows = run.saved["coding-001"]["result"]["rows"]  # type: ignore[attr-defined]
    assert {r["candidate"]: r["quality"] for r in rows} == {"opus": 0.9, "tenant_default": 0.5}
    # Grant tally counts the opus answer + judge only, not the DeepInfra call.
    assert run.tally.spent_usd == pytest.approx(0.02) and run.tally.calls == 3
    tenant_call = next(c for c in model.calls if c["provider"] == "deepinfra")
    assert tenant_call["org"] is None and tenant_call["task_type"] == "coding"


# -- policy / backlog -------------------------------------------------------------


def test_depends_on_waits_for_completion() -> None:
    a = make_item(id="a", rank=1)
    b = make_item(id="b", rank=2, depends_on=("a",))
    cfg = AutopilotConfig()
    decision = plan_dispatch(GRANT, [a, b], {}, cfg)
    assert [s.item.id for s in decision.selections] == ["a"]
    assert decision.skipped["b"] == "waiting on a"
    decision = plan_dispatch(GRANT, [a, b], {"a": ItemState("a", "completed")}, cfg)
    assert [s.item.id for s in decision.selections] == ["b"]


def test_default_concurrency_is_six() -> None:
    assert AutopilotConfig().max_concurrency == 6


def test_backlog_rejects_unknown_dependency_and_benchmark_without_source() -> None:
    base = {"schema": "selva.credit-investment-backlog/v1"}
    with pytest.raises(BacklogError, match="unknown"):
        parse_backlog(
            {
                **base,
                "items": [
                    {
                        "id": "x",
                        "mode": "generate",
                        "tiers": ["opus"],
                        "budget_share": 0.1,
                        "depends_on": ["nope"],
                    }
                ],
            }
        )
    with pytest.raises(BacklogError, match="source_item"):
        parse_backlog(
            {
                **base,
                "items": [{"id": "x", "mode": "benchmark", "tiers": ["opus"], "budget_share": 0.1}],
            }
        )


def test_repo_backlog_scale_and_value_order() -> None:
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[3] / "data" / "credit-investment" / "backlog.yaml"
    all_items = parse_backlog(yaml.safe_load(path.read_text(encoding="utf-8")))
    # Top-up items rerun a subset of an original item's targets; the scale and
    # order invariants below are about the original backlog.
    topups = [i for i in all_items if i.id.endswith("-topup")]
    items = [i for i in all_items if not i.id.endswith("-topup")]
    by_id = {i.id: i for i in items}
    for t in topups:
        if t.mode == "benchmark":
            assert t.depends_on and t.depends_on[0].endswith("-topup")
            continue
        source_ids = {
            c.id
            for i in items
            for c in i.targets()
            if t.id.startswith(i.id) or t.id == "fm-manifests-topup"
        }
        assert {c.id for c in t.targets()} <= source_ids, t.id
    assert "review-janua-auth" in by_id
    calls = 0
    for it in items:
        if it.mode == "benchmark":
            cfg = dict(it.benchmark)
            calls += estimate_calls(
                int(cfg.get("per_task_type", 20)) * 6,
                0,
                mode="benchmark",
                judges=len(cfg.get("judges", ["opus"])),
            )
        else:
            calls += estimate_calls(len(it.targets()), it.refine_rounds, mode=it.mode)
    assert 1500 <= calls <= 2500
    ranked = sorted(items, key=lambda i: i.rank)
    reviews = [i for i in ranked if i.id.startswith("review-")]
    assert ranked[: len(reviews)] == reviews and len(reviews) == 5
    files = {c for r in reviews for t in r.targets() for c in t.context}
    assert len(files) >= 120
    assert all(r.tiers == ("opus",) and r.refine_rounds == 2 for r in reviews)
    assert [i.id for i in ranked[-2:]] == ["positioning-internal", "research-factory-landscape"]
    eval_item = next(i for i in items if i.id == "eval-set-text-routing")
    assert eval_item.json_min_items >= 40 and len(eval_item.targets()) == 6
    bench_item = next(i for i in items if i.mode == "benchmark")
    assert bench_item.depends_on == ("eval-set-text-routing",)
    assert dict(bench_item.benchmark)["judges"] == ["opus", "sonnet"]
    assert dict(bench_item.benchmark)["per_task_type"] == 40
    tests = next(i for i in items if i.id == "test-gap-drafts")
    assert len(tests.targets()) == 30
    for iid in ("fm-manifests-software", "skills-factory-lines"):
        it = next(i for i in items if i.id == iid)
        assert it.tiers == ("opus", "sonnet") and it.refine_rounds == 2


def test_judge_agreement_and_two_judge_report() -> None:
    rows = []
    for n in range(4):
        rows.append(
            {
                "task_type": "coding",
                "candidate": "opus",
                "provider": "anthropic",
                "model": "claude-opus-5-5",
                "quality": 0.8 + n * 0.05,
                "quality_by_judge": {"opus": 0.8 + n * 0.05, "sonnet": 0.75 + n * 0.05},
                "latency_ms": 100,
                "cost_usd": 0.02,
            }
        )
        rows.append(
            {
                "task_type": "coding",
                "candidate": "haiku",
                "provider": "anthropic",
                "model": "claude-haiku-5-5",
                "quality": 0.4,
                "quality_by_judge": {"opus": 0.4, "sonnet": 0.9},
                "latency_ms": 50,
                "cost_usd": 0.001,
            }
        )
    agreement = judge_agreement(rows, ["opus", "sonnet"])
    entry = agreement["coding"]
    assert entry["sonnet_n"] == 8
    assert entry["sonnet_mean_abs_diff"] == pytest.approx((4 * 0.05 + 4 * 0.5) / 8)
    assert entry["sonnet_within_0_2"] == pytest.approx(0.5)
    assert judge_agreement(rows, ["opus"]) == {}
    table = aggregate(rows)
    assert table["coding"]["haiku"].alt_mean("sonnet") == pytest.approx(0.9)
    report = render_report(table, {}, "madfam", agreement=agreement, judges=("opus", "sonnet"))
    assert "quality (sonnet judge)" in report and "Inter-judge agreement" in report


def test_bench_prompt_runs_both_judges(monkeypatch: pytest.MonkeyPatch) -> None:
    candidates = {
        "opus": ("anthropic", "claude-opus-5-5"),
        "haiku": ("anthropic", "claude-haiku-5-5"),
    }
    labels = blind_labels("crm-001", list(candidates))
    inv = {v: k for k, v in labels.items()}
    reply = json.dumps({"scores": {inv["opus"]: 0.8, inv["haiku"]: 0.6}})
    model = FakeModel(cost=0.01, replies={"You grade an": reply})
    run = make_run(
        make_item(mode="benchmark", benchmark=(("source_item", "ev"),)), monkeypatch, model
    )
    ev = {"id": "crm-001", "task_type": "crm", "prompt": "p", "rubric": "r"}
    asyncio.run(bench.bench_prompt(run, ev, candidates, ("opus", "sonnet")))
    judge_models = [c["model"] for c in model.calls if c["system"].startswith("You grade")]
    assert judge_models == [TIER_MODELS["opus"], TIER_MODELS["sonnet"]]
    rows = run.saved["crm-001"]["result"]["rows"]  # type: ignore[attr-defined]
    assert all(set(r["quality_by_judge"]) == {"opus", "sonnet"} for r in rows)


def test_step_cost_uses_current_prices_and_cache_args() -> None:
    m = 1_000_000
    assert ex.step_cost("anthropic", "claude-opus-5-5", {"input_tokens": m}) == pytest.approx(4.0)
    assert ex.step_cost("anthropic", "claude-sonnet-5-5", {"output_tokens": m}) == pytest.approx(
        10.0
    )
    cached = ex.step_cost("anthropic", "claude-opus-5-5", {"cache_read_input_tokens": m})
    assert cached == pytest.approx(0.20)
