"""Selva inference → cost.event.v1: classification (RFC 0050 C13), rollup, contract shape.

Pure tests: no database, no network.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

os.environ.setdefault("ENVIRONMENT", "development")

from nexus_api.cost_events.config import (  # noqa: E402
    BUILTIN_PLATFORM_ORGS,
    CostEventsConfig,
    CostEventsConfigError,
    events_endpoint,
    load_config,
)
from nexus_api.cost_events.rollup import (  # noqa: E402
    FundingRules,
    GrantWindow,
    LedgerRow,
    civil_day,
    classify_funding,
    day_bounds_utc,
    event_id,
    occurred_at,
    rollup,
)

DAY = date(2026, 11, 3)
GRANT = GrantWindow(
    provider="anthropic",
    starts_at=datetime(2026, 11, 1, tzinfo=UTC),
    expires_at=datetime(2026, 12, 1, tzinfo=UTC),
    allowed_orgs=("madfam",),
)
RULES = FundingRules(
    grants=(GRANT,),
    required_providers=frozenset({"anthropic", "anthropic-ops"}),
    guard_platform_orgs=frozenset({"madfam"}),
    is_extra_credential=lambda p: p.startswith("anthropic-"),
)
LOCAL = frozenset({"ollama"})


def _row(
    *,
    at: datetime = datetime(2026, 11, 3, 18, 0, tzinfo=UTC),
    org: str = "madfam",
    caller: str | None = "svc",
    provider: str | None = "deepinfra",
    tokens: int = 1000,
    cost: str | None = "0.250000",
) -> LedgerRow:
    return LedgerRow(at, org, caller, provider, tokens, None if cost is None else Decimal(cost))


def _cfg(**kwargs: object) -> CostEventsConfig:
    base: dict[str, object] = {"platform_orgs": BUILTIN_PLATFORM_ORGS}
    base.update(kwargs)
    return CostEventsConfig(**base)  # type: ignore[arg-type]


# ── Dhanam's v1.0 contract (dhanam apps/api/src/modules/cost-events/cost-event.contract.ts)
TOP_LEVEL_V10 = {
    "schema", "id", "source", "kind", "occurred_at", "amount_minor", "currency", "fx",
    "cost_class", "basis", "quantity", "unit", "unit_value_minor", "taxes", "item",
    "attribution", "evidence", "status",
}  # fmt: skip
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?(Z|[+-]\d{2}:\d{2})$")
QUANTITY = re.compile(r"^-?\d{1,12}(\.\d{1,6})?$")


def assert_v10_event(event: dict[str, object]) -> None:
    assert set(event) <= TOP_LEVEL_V10, set(event) - TOP_LEVEL_V10
    assert event["schema"] == "cost.event.v1"
    assert ID.match(str(event["id"]))
    assert event["source"] == "selva"
    assert event["kind"] == "inference"
    assert RFC3339.match(str(event["occurred_at"]))
    amount = event["amount_minor"]
    assert isinstance(amount, int) and amount != 0 and abs(amount) < 10**13
    assert event["currency"] == "USD"
    assert event["cost_class"] in {"cogs", "opex", "capex", "financing"}
    assert event["basis"] == "estimate"
    assert QUANTITY.match(str(event["quantity"]))
    assert isinstance(event["unit"], str) and len(event["unit"]) <= 32
    item = event["item"]
    assert isinstance(item, dict) and set(item) <= {"sku", "material_code", "description"}
    assert len(item["description"]) <= 200
    attribution = event["attribution"]
    assert isinstance(attribution, dict)
    assert set(attribution) <= {"engagement", "order", "sku", "client_ref"}
    assert all(0 < len(v) <= 128 for v in attribution.values())
    if "engagement" in attribution:
        assert re.match(r"^eng:[a-z0-9][a-z0-9._-]{0,63}$", attribution["engagement"])


# ── who paid ──────────────────────────────────────────────────────────────────


def test_paid_provider_is_paid() -> None:
    assert classify_funding(_row(provider="deepinfra"), RULES, LOCAL) == "paid"


def test_local_model_is_compute_not_tokens() -> None:
    assert classify_funding(_row(provider="ollama"), RULES, LOCAL) == "local"
    assert classify_funding(_row(provider="Ollama"), RULES, LOCAL) == "local"


def test_grant_needs_provider_window_and_org() -> None:
    assert classify_funding(_row(provider="anthropic"), RULES, LOCAL) == "grant"
    # Before the window, another org, another provider name: not this grant.
    early = _row(provider="anthropic", at=datetime(2026, 10, 31, 23, 0, tzinfo=UTC))
    assert classify_funding(early, RULES, LOCAL) == "funding_unknown"
    assert classify_funding(_row(provider="anthropic", org="t1"), RULES, LOCAL) == (
        "funding_unknown"
    )


def test_grant_window_end_is_exclusive() -> None:
    at_end = _row(provider="anthropic", at=datetime(2026, 12, 1, tzinfo=UTC))
    assert classify_funding(at_end, RULES, LOCAL) == "funding_unknown"


def test_platform_alias_draws_on_platform_grant() -> None:
    rules = FundingRules(
        grants=(GRANT._replace(allowed_orgs=("platform-uuid",)),),
        guard_platform_orgs=frozenset({"platform-uuid"}),
    )
    assert classify_funding(_row(provider="anthropic", org="madfam"), rules, LOCAL) == "grant"


def test_required_provider_without_grant_is_never_guessed_paid() -> None:
    rules = FundingRules(required_providers=frozenset({"anthropic"}))
    assert classify_funding(_row(provider="anthropic"), rules, LOCAL) == "funding_unknown"
    extra = FundingRules(is_extra_credential=lambda p: p == "anthropic-ops")
    assert classify_funding(_row(provider="anthropic-ops"), extra, LOCAL) == "funding_unknown"


def test_unguarded_provider_with_grant_elsewhere_is_paid_outside_it() -> None:
    rules = FundingRules(grants=(GRANT._replace(provider="openai"),))
    assert classify_funding(_row(provider="openai", org="t1"), rules, LOCAL) == "paid"


# ── days ──────────────────────────────────────────────────────────────────────


def test_civil_day_is_mexico_city() -> None:
    # 05:59Z on the 4th is 23:59 on the 3rd in Mexico City (UTC-6).
    assert civil_day(datetime(2026, 11, 4, 5, 59, tzinfo=UTC)) == date(2026, 11, 3)
    assert civil_day(datetime(2026, 11, 4, 6, 0, tzinfo=UTC)) == date(2026, 11, 4)
    assert civil_day(datetime(2026, 11, 4, 5, 59)) == date(2026, 11, 3)  # naive = UTC
    start, end = day_bounds_utc(DAY)
    assert (start, end) == (
        datetime(2026, 11, 3, 6, tzinfo=UTC),
        datetime(2026, 11, 4, 6, tzinfo=UTC),
    )
    assert occurred_at(DAY) == "2026-11-03T23:59:59-06:00"


# ── rollup ────────────────────────────────────────────────────────────────────


def test_rollup_groups_per_day_org_provider_and_rounds_cents() -> None:
    rows = [
        _row(cost="0.004000"),
        _row(cost="0.004000", tokens=500),
        _row(org="t1", cost="1.234567"),
        _row(at=datetime(2026, 11, 4, 12, tzinfo=UTC), cost="9.00"),  # outside the days
    ]
    result = rollup(rows, _cfg(), FundingRules(), frozenset({DAY}))
    assert result.rows_seen == 4
    amounts = sorted(e["amount_minor"] for e in result.events.values())
    assert amounts == [1, 123]  # 0.008 → 1 cent (half up), 1.234567 → 123
    for event in result.events.values():
        assert_v10_event(event)
    platform = next(e for e in result.events.values() if e["amount_minor"] == 1)
    assert platform["quantity"] == "1500"
    assert platform["cost_class"] == "opex"  # MADFAM's own unattributed usage (C13)
    tenant = next(e for e in result.events.values() if e["amount_minor"] == 123)
    assert tenant["cost_class"] == "cogs"  # a Selva tenant: Selva serves a client (D3)
    assert tenant["attribution"]["client_ref"] == "selva-org:t1"
    assert result.built == {("paid", "opex"): 1, ("paid", "cogs"): 1}


def test_event_ids_are_deterministic_and_change_with_the_group() -> None:
    first = rollup([_row()], _cfg(), FundingRules(), frozenset({DAY}))
    again = rollup([_row(cost="0.900000")], _cfg(), FundingRules(), frozenset({DAY}))
    assert list(first.events) == list(again.events)
    other_provider = rollup([_row(provider="groq")], _cfg(), FundingRules(), frozenset({DAY}))
    assert list(first.events) != list(other_provider.events)
    (eid,) = first.events
    assert eid.startswith("selva:inference:20261103:")


def test_local_and_unknown_and_grant_are_withheld_by_default() -> None:
    rows = [
        _row(provider="ollama", tokens=7000, cost="0.900000"),
        _row(provider="anthropic", org="t1"),
        _row(provider="anthropic"),
    ]
    result = rollup(rows, _cfg(), RULES, frozenset({DAY}))
    assert result.events == {}
    assert result.withheld_events == {
        "local_compute": 1,
        "funding_unknown": 1,
        "grant_memo_unsupported": 1,
    }
    assert result.withheld_tokens["local_compute"] == 7000


def test_grant_memo_is_sent_as_non_cash_opex_once_dhanam_accepts_it() -> None:
    cfg = _cfg(features=frozenset({"funding_memo"}))
    result = rollup([_row(provider="anthropic", org="madfam")], cfg, RULES, frozenset({DAY}))
    (event,) = result.events.values()
    assert event["funding"] == "grant"
    assert event["cost_class"] == "opex"  # C13: never COGS
    assert event["basis"] == "estimate"
    assert result.built == {("grant", "opex"): 1}


def test_unpriced_rows_are_counted_never_guessed() -> None:
    rows = [_row(cost=None, tokens=40), _row(cost=None, provider="groq")]
    result = rollup(rows, _cfg(), FundingRules(), frozenset({DAY}))
    assert result.events == {}
    assert result.withheld_events["unpriced"] == 2
    mixed = rollup([_row(cost=None, tokens=40), _row()], _cfg(), FundingRules(), frozenset({DAY}))
    (event,) = mixed.events.values()
    assert event["quantity"] == "1000"
    assert mixed.withheld_calls["unpriced"] == 1
    assert mixed.withheld_tokens["unpriced"] == 40


def test_below_one_cent_and_rows_without_provider() -> None:
    rows = [_row(cost="0.004000"), _row(provider=None, cost=None)]
    result = rollup(rows, _cfg(), FundingRules(), frozenset({DAY}))
    assert result.events == {}
    assert result.withheld_events["below_one_cent"] == 1
    assert result.rows_without_provider == 1


def test_engagement_and_product_attribution() -> None:
    cfg = _cfg(
        engagement_by_org={"t2": "acme-pilot"},
        product_by_caller={"svc-tezca": "tezca"},
    )
    rows = [_row(org="t2"), _row(caller="svc-tezca")]
    result = rollup(rows, cfg, FundingRules(), frozenset({DAY}))
    events = sorted(result.events.values(), key=lambda e: e["attribution"]["client_ref"])
    for event in events:
        assert_v10_event(event)  # v1.0: no product field without the feature
        assert event["cost_class"] == "cogs"
    by_org = {e["attribution"]["client_ref"]: e for e in events}
    assert by_org["selva-org:t2"]["attribution"]["engagement"] == "eng:acme-pilot"
    product_cfg = _cfg(
        product_by_caller={"svc-tezca": "tezca"}, features=frozenset({"attribution_product"})
    )
    product_result = rollup(
        [_row(caller="svc-tezca")], product_cfg, FundingRules(), frozenset({DAY})
    )
    (event,) = product_result.events.values()
    assert event["attribution"]["product"] == "tezca"


def test_mapped_and_unmapped_callers_of_one_org_are_two_events() -> None:
    cfg = _cfg(product_by_caller={"svc-tezca": "tezca"})
    rows = [_row(caller="svc-tezca"), _row(caller="other")]
    result = rollup(rows, cfg, FundingRules(), frozenset({DAY}))
    classes = sorted(e["cost_class"] for e in result.events.values())
    assert classes == ["cogs", "opex"]


def test_long_org_ids_become_an_opaque_reference() -> None:
    result = rollup([_row(org="x" * 200)], _cfg(), FundingRules(), frozenset({DAY}))
    (event,) = result.events.values()
    assert event["attribution"]["client_ref"].startswith("selva-org-sha256:")
    assert_v10_event(event)


def test_event_id_helper_matches_contract_grammar() -> None:
    from nexus_api.cost_events.rollup import GroupKey

    key = GroupKey(DAY, "o" * 255, "p", "e", "anthropic-ops", "grant")
    assert ID.match(event_id(key))


# ── config ────────────────────────────────────────────────────────────────────


def test_config_defaults_are_off_and_v10() -> None:
    cfg = load_config({})
    assert cfg.enabled is False
    assert cfg.features == frozenset()
    assert cfg.local_providers == frozenset({"ollama"})
    assert cfg.lookback_days == 7
    assert set(cfg.missing_for_send()) == {
        "SELVA_DHANAM_COST_EVENTS_CLIENT_ID",
        "SELVA_DHANAM_COST_EVENTS_CLIENT_SECRET",
        "JANUA_ISSUER_URL",
        "DHANAM_API_URL",
    }


def test_config_full() -> None:
    cfg = load_config(
        {
            "SELVA_COST_EVENTS_EMIT_ENABLED": "true",
            "SELVA_DHANAM_COST_EVENTS_CLIENT_ID": "cid",
            "SELVA_DHANAM_COST_EVENTS_CLIENT_SECRET": "s3cr3t-value",
            "JANUA_ISSUER_URL": "https://auth.example.test/",
            "DHANAM_API_URL": "https://api.example.test",
            "PLATFORM_ORG_ID": "org-uuid",
            "SELVA_COST_EVENTS_CONTRACT_FEATURES": "attribution_product, funding_memo",
            "SELVA_COST_EVENTS_ENGAGEMENT_BY_ORG": '{"t2": "acme-pilot"}',
        }
    )
    assert cfg.enabled and cfg.missing_for_send() == []
    assert cfg.token_url == "https://auth.example.test/api/v1/oauth/token"
    assert cfg.events_url == "https://api.example.test/v1/cost-events"
    assert "org-uuid" in cfg.platform_orgs and "madfam" in cfg.platform_orgs
    assert cfg.engagement_by_org == {"t2": "acme-pilot"}
    assert "s3cr3t-value" not in repr(cfg)  # the secret never prints
    assert events_endpoint("https://api.example.test/v1") == (
        "https://api.example.test/v1/cost-events"
    )


@pytest.mark.parametrize(
    ("env", "names"),
    [
        ({"SELVA_COST_EVENTS_LOOKBACK_DAYS": "0"}, "SELVA_COST_EVENTS_LOOKBACK_DAYS"),
        ({"SELVA_COST_EVENTS_LOOKBACK_DAYS": "abc"}, "SELVA_COST_EVENTS_LOOKBACK_DAYS"),
        ({"SELVA_COST_EVENTS_START_DATE": "2026-02-30"}, "SELVA_COST_EVENTS_START_DATE"),
        ({"SELVA_COST_EVENTS_CONTRACT_FEATURES": "nonsense"}, "CONTRACT_FEATURES"),
        ({"SELVA_COST_EVENTS_PRODUCT_BY_CALLER": "[]"}, "SELVA_COST_EVENTS_PRODUCT_BY_CALLER"),
        ({"SELVA_COST_EVENTS_ENGAGEMENT_BY_ORG": '{"a": "Bad Slug"}'}, "ENGAGEMENT_BY_ORG"),
        ({"SELVA_COST_EVENTS_ENGAGEMENT_BY_ORG": "{"}, "ENGAGEMENT_BY_ORG"),
        ({"DHANAM_API_URL": "http://api.example.test"}, "DHANAM_API_URL"),
    ],
)
def test_config_errors_name_the_variable_not_the_value(env: dict[str, str], names: str) -> None:
    with pytest.raises(CostEventsConfigError) as caught:
        load_config(env)
    assert names in str(caught.value)
    for value in env.values():
        if len(value) > 3:
            assert value not in str(caught.value)
