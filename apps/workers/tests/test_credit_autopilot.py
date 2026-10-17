"""Tests for the credit-investment autopilot: selection, pacing, guards."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from selva_workers.jobs import credit_autopilot as ap
from selva_workers.jobs.credit_autopilot_policy import (
    TIER_MODELS,
    AutopilotConfig,
    BacklogError,
    BacklogItem,
    GrantView,
    ItemState,
    choose_grant,
    choose_tier,
    parse_backlog,
    plan_dispatch,
    stop_reason,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKLOG = REPO_ROOT / "data" / "credit-investment" / "backlog.yaml"
CFG = AutopilotConfig(floor_usd=2.0, max_concurrency=2, max_attempts=2)


def grant(**kw: Any) -> GrantView:
    base = GrantView(
        id="example-grant",
        provider="anthropic",
        ceiling_usd=100.0,
        remaining_usd=80.0,
        seconds_to_expiry=10 * 3600,
        pace_status="behind",
        burn_usd_per_hour_60m=5.0,
        required_usd_per_hour=8.0,
        autopilot=True,
    )
    return replace(base, **kw)


def item(item_id: str = "a", rank: int = 10, **kw: Any) -> BacklogItem:
    base = BacklogItem(
        id=item_id,
        rank=rank,
        line="faap",
        mode="generate",
        tiers=("opus", "sonnet"),
        budget_share=0.05,
    )
    return replace(base, **kw)


# -- backlog file -----------------------------------------------------------


def test_repo_backlog_is_valid_and_public_safe() -> None:
    items = parse_backlog(yaml.safe_load(BACKLOG.read_text(encoding="utf-8")))
    assert len(items) >= 10
    assert {i.line for i in items} >= {"software", "geometry", "physical", "faap"}
    assert sum(i.budget_share for i in items) <= 1.0
    # Priority (a) first: the manifest schema leads the queue.
    assert sorted(items, key=lambda i: i.rank)[0].id == "fm-schema-v1"
    text = BACKLOG.read_text(encoding="utf-8")
    assert "$" not in text and "amount_usd" not in text


def test_backlog_rejects_forbidden_tool() -> None:
    doc = {
        "schema": "selva.credit-investment-backlog/v1",
        "forbidden_tools": ["send_email"],
        "items": [
            {
                "id": "x",
                "mode": "generate",
                "tiers": ["opus"],
                "budget_share": 0.1,
                "allowed_tools": ["send_email"],
            }
        ],
    }
    with pytest.raises(BacklogError, match="forbidden"):
        parse_backlog(doc)


def test_backlog_rejects_amount_keys_and_overcommitted_shares() -> None:
    base = {"schema": "selva.credit-investment-backlog/v1"}
    with pytest.raises(BacklogError, match="not allowed"):
        parse_backlog(
            {
                **base,
                "items": [
                    {
                        "id": "x",
                        "mode": "generate",
                        "tiers": ["opus"],
                        "budget_share": 0.1,
                        "amount_usd": 5,
                    }
                ],
            }
        )
    over = [
        {"id": f"i{n}", "mode": "generate", "tiers": ["opus"], "budget_share": 0.6}
        for n in range(2)
    ]
    with pytest.raises(BacklogError, match="add up"):
        parse_backlog({**base, "items": over})


# -- grant choice + stop rules ---------------------------------------------


def test_choose_grant_needs_autopilot_provider_and_life() -> None:
    assert choose_grant([grant(autopilot=False)]) is None
    assert choose_grant([grant(provider="openai")]) is None
    assert choose_grant([grant(pace_status="expired")]) is None
    soon = grant(id="soon", seconds_to_expiry=3600)
    later = grant(id="later")
    assert choose_grant([later, soon]) == soon
    # C2 statuses may arrive as mappings.
    as_dict = {**grant().__dict__}
    assert choose_grant([as_dict]) == grant()


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"pace_status": "exhausted"}, "grant exhausted"),
        ({"pace_status": "expired"}, "grant expired"),
        ({"pace_status": "ahead"}, "pace ahead: no new work"),
        ({"remaining_usd": 2.0}, "remaining at or below floor"),
        ({"seconds_to_expiry": 600}, "too close to expiry"),
    ],
)
def test_stop_reasons(kw: dict[str, Any], expected: str) -> None:
    assert stop_reason(grant(**kw), CFG) == expected
    decision = plan_dispatch(grant(**kw), [item()], {}, CFG)
    assert decision.run is False and decision.selections == []


def test_spends_while_behind_or_on_pace() -> None:
    assert stop_reason(grant(pace_status="behind"), CFG) is None
    assert stop_reason(grant(pace_status="on_pace"), CFG) is None


# -- tier selection ----------------------------------------------------------


def test_preferred_tier_by_default() -> None:
    tier, _ = choose_tier(item(tiers=("sonnet", "opus")), grant(pace_status="on_pace"), CFG) or (
        "",
        "",
    )
    assert tier == "sonnet"


def test_upgrade_only_within_allowed_tiers_when_far_behind() -> None:
    far = grant(pace_status="behind", required_usd_per_hour=30.0, burn_usd_per_hour_60m=1.0)
    choice = choose_tier(item(tiers=("sonnet", "opus", "haiku")), far, CFG)
    assert choice is not None and choice[0] == "opus"
    # No opus allowed -> stays within the item's tiers.
    choice = choose_tier(item(tiers=("haiku", "sonnet"), budget_share=0.001), far, CFG)
    assert choice is not None and choice[0] == "sonnet"
    # budget_share is sized for the preferred tier: an upgrade that the
    # remaining budget cannot cover is walked back down.
    choice = choose_tier(item(tiers=("haiku", "sonnet"), budget_share=0.05), far, CFG)
    assert choice is not None and choice[0] == "haiku"


def test_downgrade_when_time_is_short() -> None:
    short = grant(seconds_to_expiry=1800)
    choice = choose_tier(item(tiers=("opus", "sonnet")), short, CFG)
    assert choice is not None and choice[0] == "sonnet"


def test_downgrade_when_grant_nearly_used() -> None:
    low = grant(remaining_usd=10.0)  # 10% of ceiling < 15%
    choice = choose_tier(item(tiers=("opus", "sonnet", "haiku"), budget_share=0.01), low, CFG)
    assert choice is not None and choice[0] == "sonnet"


def test_downgrade_until_item_fits_remaining_or_skip() -> None:
    tight = grant(remaining_usd=5.0, ceiling_usd=100.0)  # spendable 3.0
    # opus est 10.0, sonnet 5.0, haiku 0.25 -> haiku
    choice = choose_tier(item(tiers=("opus", "sonnet", "haiku"), budget_share=0.10), tight, CFG)
    assert choice is not None and choice[0] == "haiku"
    assert choose_tier(item(tiers=("opus",), budget_share=0.10), tight, CFG) is None


# -- dispatch planning --------------------------------------------------------


def test_bounded_concurrency_and_rank_order() -> None:
    items = [item("c", 30), item("a", 10), item("b", 20)]
    decision = plan_dispatch(grant(), items, {}, CFG)
    assert [s.item.id for s in decision.selections] == ["a", "b"]
    assert all(s.model in TIER_MODELS.values() for s in decision.selections)

    busy = {"a": ItemState("a", "running"), "b": ItemState("b", "queued")}
    decision = plan_dispatch(grant(), items, busy, CFG)
    assert decision.selections == [] and "no free slot" in decision.reason


def test_done_items_skipped_failed_items_retried_until_max_attempts() -> None:
    items = [item("a", 10), item("b", 20), item("c", 30)]
    states = {
        "a": ItemState("a", "completed"),
        "b": ItemState("b", "failed", attempts=1),
        "c": ItemState("c", "failed", attempts=2),
    }
    decision = plan_dispatch(grant(), items, states, CFG)
    assert [s.item.id for s in decision.selections] == ["b"]
    assert decision.skipped["c"] == "max attempts reached"


def test_dispatch_mode_only_for_safe_graphs_and_not_when_time_short() -> None:
    unsafe = item("x", mode="dispatch", graph="coding")
    safe = item("y", 20, mode="dispatch", graph="research")
    decision = plan_dispatch(grant(), [unsafe, safe], {}, CFG)
    assert [s.item.id for s in decision.selections] == ["y"]
    assert "not allowed" in decision.skipped["x"]
    decision = plan_dispatch(grant(seconds_to_expiry=1800), [safe], {}, CFG)
    assert decision.selections == [] and decision.skipped["y"] == "time short for a graph run"


def test_summarise_states_counts_attempts_and_stale_rows() -> None:
    rows = [
        {"item_id": "a", "status": "failed"},
        {"item_id": "a", "status": "running", "stale": True},
        {"item_id": "b", "status": "running", "stale": False},
        {"item_id": None, "status": "completed"},
    ]
    states = ap.summarise_states(rows)
    assert states["a"].attempts == 2 and states["a"].status in {"failed", "stale"}
    assert states["b"].status == "running"


# -- loop guards ---------------------------------------------------------------


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CREDIT_AUTOPILOT_ENABLED", raising=False)
    assert ap.is_enabled() is False
    assert asyncio.run(ap.tick(set())) is None


def test_org_is_pinned_to_platform_org(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLATFORM_ORG_ID", raising=False)
    monkeypatch.delenv("CREDIT_AUTOPILOT_ORG_ID", raising=False)
    assert ap.autopilot_org() == "madfam"
    monkeypatch.setenv("PLATFORM_ORG_ID", "org-platform")
    assert ap.autopilot_org() == "org-platform"
    monkeypatch.setenv("CREDIT_AUTOPILOT_ORG_ID", "some-tenant")
    assert ap.autopilot_org() is None


def test_noop_when_grants_module_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREDIT_AUTOPILOT_ENABLED", "true")

    def _missing(name: str) -> Any:
        raise ImportError(name)

    monkeypatch.setattr(ap.importlib, "import_module", _missing)
    assert asyncio.run(ap.load_grant_statuses()) is None
    assert asyncio.run(ap.tick(set())) is None


def test_load_grant_statuses_accepts_sync_and_async(monkeypatch: pytest.MonkeyPatch) -> None:
    class SyncMod:
        @staticmethod
        def get_grant_statuses() -> list[dict[str, Any]]:
            return [{"id": "g"}]

    class AsyncMod:
        @staticmethod
        async def get_grant_statuses() -> list[dict[str, Any]]:
            return [{"id": "h"}]

    monkeypatch.setattr(ap.importlib, "import_module", lambda _n: SyncMod)
    assert asyncio.run(ap.load_grant_statuses()) == [{"id": "g"}]
    monkeypatch.setattr(ap.importlib, "import_module", lambda _n: AsyncMod)
    assert asyncio.run(ap.load_grant_statuses()) == [{"id": "h"}]


def test_idle_when_no_autopilot_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREDIT_AUTOPILOT_ENABLED", "true")

    async def _statuses() -> list[Any]:
        return [grant(autopilot=False)]

    monkeypatch.setattr(ap, "load_grant_statuses", _statuses)
    assert asyncio.run(ap.tick(set())) is None


def test_fetch_context_rejects_paths_outside_org() -> None:
    bad = item(context=(("other/repo", "README.md"), ("selva-office", "../etc/passwd")))
    files, missing = asyncio.run(ap.fetch_context(bad))
    assert files == [] and len(missing) == 2 and all("rejected" in m for m in missing)
