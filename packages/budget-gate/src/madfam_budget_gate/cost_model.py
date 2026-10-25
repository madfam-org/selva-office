"""Hardcoded cost model for known LLM provider/model combinations.

Prices are USD per 1M tokens, sourced from each provider's public
pricing page as of 2026-Q2.  This is intentionally a small,
maintainable lookup — providers rarely add public price tiers and
when they do we want a code review on the bump.

When a (provider, model) pair is not found we **fall back to a
conservative high default** rather than 0 — the gate must err on the
side of overestimating spend, never under.  An unknown *Anthropic*
model is priced as claude-fable-5-1, the most expensive current model.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)


class _Price(NamedTuple):
    input_per_1m_usd: float
    output_per_1m_usd: float
    #: Prompt-cache read rate. ``None`` means "0.1x input", the provider's
    #: standard cache-read ratio, for rows whose list price does not state it.
    cache_read_per_1m_usd: float | None = None


#: Prompt-cache write (5-minute TTL) costs 1.25x the input rate.
CACHE_WRITE_MULTIPLIER = 1.25
#: Default cache-read ratio when a row does not state its own rate.
CACHE_READ_DEFAULT_RATIO = 0.1


# Lower-cased provider, lower-cased model fragment (matched as prefix on the
# normalised model string) → price.  We match on prefix so the table covers
# minor model-name variants like "claude-opus-4-7-20260301" or
# "anthropic.claude-opus-4-7-v1:0" (a leading "anthropic." / "anthropic/"
# vendor prefix is stripped before matching).
#
# IMPORTANT: order matters within a provider — longer / more specific
# prefixes must come BEFORE shorter ones.  Iteration uses first-match.
_PRICE_TABLE: dict[str, list[tuple[str, _Price]]] = {
    # Anthropic first-party list prices, USD per 1M tokens (input / output
    # / cache read). There are deliberately NO family catch-alls such as
    # "claude-opus": an Anthropic model this table does not name is priced
    # at the worst case (claude-fable-5-1) with a WARNING, so a spend
    # ceiling built on these numbers can only over-count, never under-count.
    "anthropic": [
        ("claude-fable-5-1", _Price(10.0, 50.0, 0.25)),
        ("claude-fable-5", _Price(10.0, 50.0, 0.25)),
        ("claude-opus-5-5", _Price(4.0, 20.0, 0.20)),
        ("claude-opus-5", _Price(5.0, 25.0)),
        ("claude-opus-4-8", _Price(5.0, 25.0)),
        ("claude-opus-4-7", _Price(5.0, 25.0)),
        ("claude-opus-4-6", _Price(5.0, 25.0)),
        ("claude-opus-4-5", _Price(5.0, 25.0)),
        # Opus 4 / 4.1 (legacy list price).
        ("claude-opus-4", _Price(15.0, 75.0)),
        ("claude-sonnet-5-5", _Price(2.0, 10.0, 0.20)),
        ("claude-sonnet-5", _Price(2.0, 10.0)),
        ("claude-sonnet-4-6", _Price(3.0, 15.0)),
        ("claude-sonnet-4", _Price(3.0, 15.0)),
        # Haiku 5.5 lists $0.50 / $2.50 above 100K prompt tokens; the base
        # tier is priced here (prompts that long are rare in Selva).
        ("claude-haiku-5-5", _Price(0.10, 0.50, 0.01)),
        ("claude-haiku-4-5", _Price(1.0, 5.0)),
    ],
    "openai": [
        ("gpt-4o-mini", _Price(0.15, 0.60)),
        ("gpt-4o", _Price(2.50, 10.0)),
        ("gpt-4-turbo", _Price(10.0, 30.0)),
        ("gpt-4", _Price(30.0, 60.0)),
        ("gpt-3.5-turbo", _Price(0.50, 1.50)),
        ("o1-mini", _Price(3.0, 12.0)),
        ("o1", _Price(15.0, 60.0)),
    ],
    # DeepInfra hosts many open-source models at heavily discounted rates.
    # We list the four we actually route to in production; everything
    # else under the 'deepinfra' key falls back to a conservative
    # mid-tier price.
    "deepinfra": [
        ("meta-llama/llama-3.3-70b-instruct", _Price(0.23, 0.40)),
        ("meta-llama/llama-3.1-70b-instruct", _Price(0.23, 0.40)),
        ("meta-llama/llama-3.1-8b-instruct", _Price(0.05, 0.08)),
        ("mistralai/mixtral-8x7b-instruct-v0.1", _Price(0.24, 0.24)),
    ],
    # Together / Fireworks / Groq host the same model families at
    # similar prices; we treat them as a single tier.
    "together": [
        ("meta-llama/llama-3.3-70b-instruct", _Price(0.88, 0.88)),
        ("meta-llama/llama-3.1-70b-instruct", _Price(0.88, 0.88)),
    ],
    "fireworks": [
        ("accounts/fireworks/models/llama-v3p1-70b-instruct", _Price(0.90, 0.90)),
    ],
    "groq": [
        ("llama-3.3-70b-versatile", _Price(0.59, 0.79)),
    ],
    "mistral": [
        ("mistral-large", _Price(2.0, 6.0)),
        ("mistral-small", _Price(0.20, 0.60)),
    ],
}

# Conservative fallback when the table doesn't know the provider at all.
# Picked to be the highest mainstream price (legacy Claude Opus) so the gate
# never *under*-estimates spend.
_DEFAULT_FALLBACK = _Price(15.0, 75.0)

#: Worst-case price for an Anthropic model the table does not name: the most
#: expensive current model (claude-fable-5-1), so a provider-credit ceiling
#: stays safe when Anthropic ships a new id before this table learns it.
ANTHROPIC_UNKNOWN_MODEL_PRICE = _Price(10.0, 50.0, 0.25)

_VENDOR_PREFIXES = ("anthropic.", "anthropic/", "us.anthropic.", "eu.anthropic.")


def estimate_cost(
    provider: str | None,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """Estimate USD cost of a single LLM call.

    Both ``provider`` and ``model`` are case-insensitive.  Unknown
    providers fall back to a deliberately high baseline; unknown
    Anthropic models are priced as claude-fable-5-1 (the worst case) and
    logged at WARNING so ops can backfill the table.

    ``input_tokens`` are the *uncached* prompt tokens (Anthropic's
    ``usage.input_tokens`` already excludes cache reads and writes).
    ``cache_read_tokens`` are billed at the row's cache-read rate (0.1x
    input when the row does not state one) and ``cache_creation_tokens``
    at 1.25x input (5-minute TTL).
    """
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts cannot be negative")
    if cache_read_tokens < 0 or cache_creation_tokens < 0:
        raise ValueError("cache token counts cannot be negative")

    price = _lookup(provider, model)
    cache_read_rate = (
        price.cache_read_per_1m_usd
        if price.cache_read_per_1m_usd is not None
        else price.input_per_1m_usd * CACHE_READ_DEFAULT_RATIO
    )
    cost = (
        input_tokens * price.input_per_1m_usd
        + output_tokens * price.output_per_1m_usd
        + cache_read_tokens * cache_read_rate
        + cache_creation_tokens * price.input_per_1m_usd * CACHE_WRITE_MULTIPLIER
    ) / 1_000_000
    return round(cost, 6)


def _normalise_model(model: str) -> str:
    m = model.strip().lower()
    for prefix in _VENDOR_PREFIXES:
        if m.startswith(prefix):
            return m[len(prefix) :]
    return m


def _price_family(provider: str) -> str:
    """The price-table key for a provider name.

    An extra Anthropic account registered as its own provider
    (``anthropic-<suffix>``, see ``madfam_inference.credentials``) is the same
    vendor at the same prices: it is priced as ``anthropic``. The provider
    name itself is kept everywhere else (ledger rows, grant meters), so each
    account's spend stays separately visible.
    """
    p = provider.strip().lower()
    if p.startswith("anthropic-"):
        return "anthropic"
    return p


def _lookup(provider: str | None, model: str | None) -> _Price:
    if provider is None or model is None:
        logger.debug("cost_model: missing provider/model, using fallback rate")
        return _DEFAULT_FALLBACK

    p = _price_family(provider)
    m = _normalise_model(model)
    table = _PRICE_TABLE.get(p)
    if table is None:
        logger.debug("cost_model: unknown provider %r, using fallback rate", provider)
        return _DEFAULT_FALLBACK
    for prefix, price in table:
        if m.startswith(prefix.lower()):
            return price
    if p == "anthropic":
        logger.warning(
            "cost_model: unknown Anthropic model %r — pricing it as claude-fable-5-1 "
            "(worst case) until the price table names it",
            model,
        )
        return ANTHROPIC_UNKNOWN_MODEL_PRICE
    logger.debug(
        "cost_model: unknown model %r for provider %r, using fallback rate", model, provider
    )
    return _DEFAULT_FALLBACK


def known_providers() -> list[str]:
    """Return the list of providers with explicit price entries."""
    return sorted(_PRICE_TABLE.keys())
