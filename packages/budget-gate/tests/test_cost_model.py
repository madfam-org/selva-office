"""Unit tests for the cost model lookup table."""

from __future__ import annotations

import pytest

from madfam_budget_gate.cost_model import estimate_cost, known_providers


def test_known_providers_includes_core_set() -> None:
    providers = set(known_providers())
    assert {"anthropic", "openai", "deepinfra"}.issubset(providers)


def test_anthropic_opus_pricing() -> None:
    # 1M input + 1M output tokens at $5/$25 per 1M = $30 (current list price).
    cost = estimate_cost("anthropic", "claude-opus-4-7", 1_000_000, 1_000_000)
    assert cost == pytest.approx(30.0)


def test_anthropic_sonnet_pricing() -> None:
    cost = estimate_cost("anthropic", "claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost == pytest.approx(18.0)


def test_anthropic_sonnet_5_5_has_its_own_price() -> None:
    # $2 / $10 per 1M — not the generic "claude-sonnet" row ($3 / $15).
    cost = estimate_cost("anthropic", "claude-sonnet-5-5", 1_000_000, 1_000_000)
    assert cost == pytest.approx(12.0)
    dated = estimate_cost("anthropic", "claude-sonnet-5-5-20260901", 1_000_000, 0)
    assert dated == pytest.approx(2.0)


def test_anthropic_haiku_pricing() -> None:
    cost = estimate_cost("anthropic", "claude-haiku-4-5", 1_000_000, 1_000_000)
    assert cost == pytest.approx(6.0)


def test_openai_gpt4o_mini_pricing() -> None:
    cost = estimate_cost("openai", "gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.75)


def test_unknown_anthropic_model_uses_fable_worst_case(caplog: pytest.LogCaptureFixture) -> None:
    """An Anthropic model the table does not name is priced as claude-fable-5-1."""
    with caplog.at_level("WARNING", logger="madfam_budget_gate.cost_model"):
        cost = estimate_cost("anthropic", "claude-fictional-9000", 1_000_000, 1_000_000)
    assert cost == pytest.approx(60.0)
    assert any("unknown Anthropic model" in r.getMessage() for r in caplog.records)


def test_unknown_provider_uses_opus_fallback() -> None:
    cost = estimate_cost("never-heard-of-it", "model-x", 1_000_000, 0)
    assert cost == pytest.approx(15.0)


def test_missing_provider_or_model_uses_fallback() -> None:
    cost = estimate_cost(None, None, 1_000_000, 0)
    assert cost == pytest.approx(15.0)


def test_negative_tokens_rejected() -> None:
    with pytest.raises(ValueError):
        estimate_cost("anthropic", "claude-opus-4-7", -1, 0)
    with pytest.raises(ValueError):
        estimate_cost("anthropic", "claude-opus-4-7", 0, -1)


def test_case_insensitive_lookup() -> None:
    a = estimate_cost("Anthropic", "Claude-Opus-4-7", 100_000, 0)
    b = estimate_cost("anthropic", "claude-opus-4-7", 100_000, 0)
    assert a == b


def test_prefix_match_handles_versioned_model_strings() -> None:
    """Model strings often include version suffixes; prefix match must catch them."""
    cost = estimate_cost("anthropic", "claude-sonnet-4-6-20260301", 1_000_000, 0)
    # Should match the claude-sonnet-4-6 entry: $3 per 1M input.
    assert cost == pytest.approx(3.0)


# ── Current Anthropic list prices (C3) ─────────────────────────────────────

ANTHROPIC_PRICES = [
    # model, input $/MTok, output $/MTok, cache read $/MTok
    ("claude-fable-5-1", 10.0, 50.0, 0.25),
    ("claude-opus-5-5", 4.0, 20.0, 0.20),
    ("claude-sonnet-5-5", 2.0, 10.0, 0.20),
    ("claude-haiku-5-5", 0.10, 0.50, 0.01),
    ("claude-opus-5", 5.0, 25.0, 0.50),
    ("claude-opus-4-8", 5.0, 25.0, 0.50),
    ("claude-opus-4-7", 5.0, 25.0, 0.50),
    ("claude-sonnet-5", 2.0, 10.0, 0.20),
    ("claude-sonnet-4-6", 3.0, 15.0, 0.30),
    ("claude-haiku-4-5", 1.0, 5.0, 0.10),
]


@pytest.mark.parametrize(("model", "inp", "out", "_read"), ANTHROPIC_PRICES)
def test_anthropic_list_prices(model: str, inp: float, out: float, _read: float) -> None:
    assert estimate_cost("anthropic", model, 1_000_000, 0) == pytest.approx(inp)
    assert estimate_cost("anthropic", model, 0, 1_000_000) == pytest.approx(out)


@pytest.mark.parametrize(("model", "inp", "_out", "read"), ANTHROPIC_PRICES)
def test_anthropic_cache_rates(model: str, inp: float, _out: float, read: float) -> None:
    assert estimate_cost("anthropic", model, 0, 0, cache_read_tokens=1_000_000) == pytest.approx(
        read
    )
    # 5-minute cache writes cost 1.25x input.
    assert estimate_cost(
        "anthropic", model, 0, 0, cache_creation_tokens=1_000_000
    ) == pytest.approx(inp * 1.25)


def test_family_prefixes_do_not_shadow_specific_rows() -> None:
    # claude-opus-5-5 must not match the claude-opus-5 row, nor sonnet-5-5 the
    # sonnet-5 row; dated suffixes still resolve to the specific row.
    assert estimate_cost("anthropic", "claude-opus-5-5-20261001", 1_000_000, 0) == pytest.approx(
        4.0
    )
    assert estimate_cost("anthropic", "claude-opus-5-20260601", 1_000_000, 0) == pytest.approx(5.0)
    assert estimate_cost("anthropic", "claude-sonnet-5-20260601", 1_000_000, 0) == pytest.approx(
        2.0
    )


def test_vendor_prefixed_model_ids_resolve() -> None:
    assert estimate_cost("anthropic", "anthropic/claude-opus-5-5", 1_000_000, 0) == pytest.approx(
        4.0
    )
    assert estimate_cost(
        "anthropic", "anthropic.claude-opus-4-7-v1:0", 1_000_000, 0
    ) == pytest.approx(5.0)


def test_mixed_cache_call_math() -> None:
    # Opus 5.5: 2K uncached in, 50K cache read, 10K cache write, 1K out.
    cost = estimate_cost(
        "anthropic",
        "claude-opus-5-5",
        2_000,
        1_000,
        cache_read_tokens=50_000,
        cache_creation_tokens=10_000,
    )
    expected = (2_000 * 4.0 + 1_000 * 20.0 + 50_000 * 0.20 + 10_000 * 4.0 * 1.25) / 1_000_000
    assert cost == pytest.approx(expected)


def test_cache_args_default_to_zero_keep_old_signature() -> None:
    # Positional 4-arg calls (gate.record, nexus ledger) are unchanged.
    assert estimate_cost("anthropic", "claude-sonnet-5-5", 1_000, 1_000) == estimate_cost(
        "anthropic", "claude-sonnet-5-5", 1_000, 1_000, cache_read_tokens=0, cache_creation_tokens=0
    )


def test_negative_cache_tokens_rejected() -> None:
    with pytest.raises(ValueError):
        estimate_cost("anthropic", "claude-opus-5-5", 0, 0, cache_read_tokens=-1)
    with pytest.raises(ValueError):
        estimate_cost("anthropic", "claude-opus-5-5", 0, 0, cache_creation_tokens=-1)


def test_non_anthropic_unknown_model_keeps_generic_fallback() -> None:
    assert estimate_cost("openai", "gpt-unknown", 1_000_000, 0) == pytest.approx(15.0)
