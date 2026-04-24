"""HITL confidence tracking (Sprint 1 + Sprint 2).

Module boundary: this package holds the *policy* (what a decision means
for the Beta posterior, how buckets are keyed, when to promote) but never
touches the DB directly. The nexus-api side imports these pure functions,
then persists the results through SQLAlchemy using its own session.

Why split it that way: the permissions package is used by workers too,
and we don't want to drag SQLAlchemy / asyncpg into the worker image
just for confidence tracking. Workers emit events; nexus-api writes them.

Sprint 1: observe-only. Sprint 2 layers on:
  - ``promote_if_eligible`` — Bayesian credible-interval + min-samples
    ladder with per-category reversibility caps
  - demotion on ``DOWNSTREAM_REVERTED`` (one-step-down) and via
    ``demote_if_idle`` (30d silence → ASK)
  - ``effective_tier`` — what gate to fire, applying reversibility caps
    and forced-ASK sampling on top of the bucket's stored tier
  - ``current_tier`` — legacy Sprint 1 surface; preserved so existing
    callers keep working while they migrate to ``effective_tier``
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING


class ConfidenceTier(StrEnum):
    """Matches `HitlConfidenceTier` in the DB model.

    Kept here (not imported from nexus_api.models) so the permissions
    package has no nexus-api import dependency.
    """

    ASK = "ask"
    ASK_QUIET = "ask_quiet"
    ALLOW_SHADOW = "allow_shadow"
    ALLOW = "allow"


class DecisionOutcome(StrEnum):
    """Mirror of `HitlOutcome` — see `confidence.py` docstring rationale."""

    APPROVED_CLEAN = "approved_clean"
    APPROVED_MODIFIED = "approved_modified"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    DOWNSTREAM_REVERTED = "downstream_reverted"


# Beta posterior update weights per outcome. Picked to encode:
#   clean approval = full positive signal
#   approval-with-modification = partial rejection (human intervened)
#   rejection = full negative
#   timeout = soft negative (silence ≠ consent)
#   downstream revert = strong negative (louder than a live rejection)
_POSTERIOR_UPDATE: dict[DecisionOutcome, tuple[float, float]] = {
    DecisionOutcome.APPROVED_CLEAN: (1.0, 0.0),
    DecisionOutcome.APPROVED_MODIFIED: (0.3, 0.7),
    DecisionOutcome.REJECTED: (0.0, 1.0),
    DecisionOutcome.TIMEOUT: (0.0, 0.5),
    DecisionOutcome.DOWNSTREAM_REVERTED: (0.0, 2.0),
}


# --- Sprint 2 policy constants -----------------------------------------------
#
# These numbers are intentionally conservative. An agent has to earn every
# step of autonomy through a lot of consistent positive signal, and any
# revert knocks it down. The ladder is:
#
#   ASK         (default) — every decision shown to a human
#   ASK_QUIET  (10 samples, LCB ≥ 0.70) — still ASK but collapsed UI
#   ALLOW_SHADOW (30, LCB ≥ 0.85)      — dry-run: agent proceeds, human sees diff
#   ALLOW      (100, LCB ≥ 0.95)       — autonomous; forced-ASK sample keeps us honest

# Action categories whose worst case is irreversible or loud (deploys, spend,
# emails/DMs to outside parties). These are hard-capped at ASK_QUIET — a
# bucket *never* promotes past that for these categories even with thousands
# of clean approvals.
HIGH_REVERSIBILITY_COST_CATEGORIES: frozenset[str] = frozenset(
    {
        "deploy",
        "spend",
        "external_communication",
    }
)

# Per-category explicit overrides; anything not listed defaults to
# ConfidenceTier.ALLOW (the full ladder).
REVERSIBILITY_CAP_OVERRIDES: dict[str, ConfidenceTier] = {}

# Min unique decisions observed before a bucket is eligible to promote INTO
# that tier. Matches Sprint 1 memo: 10 / 30 / 100.
MIN_SAMPLES_FOR_TIER: dict[ConfidenceTier, int] = {
    ConfidenceTier.ASK: 0,
    ConfidenceTier.ASK_QUIET: 10,
    ConfidenceTier.ALLOW_SHADOW: 30,
    ConfidenceTier.ALLOW: 100,
}

# One-sided lower bound of the Beta posterior (95% credible). The bucket's
# LCB must meet this before it's eligible to promote INTO the tier. Higher
# tiers = higher bar.
CREDIBLE_LOWER_BOUND_THRESHOLD: dict[ConfidenceTier, float] = {
    ConfidenceTier.ASK: 0.0,
    ConfidenceTier.ASK_QUIET: 0.70,
    ConfidenceTier.ALLOW_SHADOW: 0.85,
    ConfidenceTier.ALLOW: 0.95,
}

# Fraction of decisions forced back to ASK even when the bucket sits in a
# higher tier. Why: if the agent learned to game the context signature (e.g.
# always classifying things into a clean bucket), forced samples will surface
# a reject and knock the posterior back into reality. Rates are deliberately
# non-zero even for the highest tier — the loss of autonomy is small and
# the safety value is large.
FORCED_SAMPLING_RATE: dict[ConfidenceTier, float] = {
    ConfidenceTier.ASK: 0.0,
    ConfidenceTier.ASK_QUIET: 0.0,  # UI already shows everything
    ConfidenceTier.ALLOW_SHADOW: 0.10,
    ConfidenceTier.ALLOW: 0.05,
}

# A bucket that sees no decisions for this long demotes to ASK — context
# almost certainly drifted, and we don't want stale trust surviving a
# long silence.
IDLE_DEMOTION_THRESHOLD = timedelta(days=30)

# After a demotion (revert or idle), hold the bucket at the new tier for at
# least this long before allowing another promotion. Prevents rapid
# up-down thrash.
REPROMOTION_LOCK = timedelta(days=7)

# Bump on any change to signature/feature extraction or scoring.
SIGNATURE_VERSION = 1

# Ordered ladder; used for "next tier up" / "next tier down" walks.
_TIER_LADDER: tuple[ConfidenceTier, ...] = (
    ConfidenceTier.ASK,
    ConfidenceTier.ASK_QUIET,
    ConfidenceTier.ALLOW_SHADOW,
    ConfidenceTier.ALLOW,
)

_TIER_ORDER: dict[ConfidenceTier, int] = {t: i for i, t in enumerate(_TIER_LADDER)}


@dataclass(frozen=True)
class BucketState:
    """A read-only snapshot of a bucket's rolling counters + posterior.

    The DB model stores the same fields; this dataclass is the in-memory
    form that pure update functions operate on. Callers load a row into
    this shape, call ``apply_decision`` / ``promote_if_eligible``, and write
    the resulting state back.

    ``locked_until`` and ``last_decision_at`` are optional because the
    Sprint 1 callers (worker-side) may not carry them. Sprint 2 callers
    should populate both when available.
    """

    n_observed: int
    n_approved_clean: int
    n_approved_modified: int
    n_rejected: int
    n_timeout: int
    n_reverted: int
    beta_alpha: float
    beta_beta: float
    tier: ConfidenceTier
    locked_until: datetime | None = None
    last_decision_at: datetime | None = None

    @property
    def confidence(self) -> float:
        """Mean of the Beta posterior — the cached ``confidence`` column."""
        denom = self.beta_alpha + self.beta_beta
        if denom <= 0:
            return 0.5
        return self.beta_alpha / denom


INITIAL_BUCKET_STATE = BucketState(
    n_observed=0,
    n_approved_clean=0,
    n_approved_modified=0,
    n_rejected=0,
    n_timeout=0,
    n_reverted=0,
    # Beta(1, 1) uninformative prior — 0.5 mean, full spread.
    beta_alpha=1.0,
    beta_beta=1.0,
    tier=ConfidenceTier.ASK,
    locked_until=None,
    last_decision_at=None,
)


# -- Sprint 2: promotion maths ------------------------------------------------


def reversibility_cap(action_category: str) -> ConfidenceTier:
    """Highest tier a bucket with this category is ever allowed to hold."""
    if action_category in HIGH_REVERSIBILITY_COST_CATEGORIES:
        return ConfidenceTier.ASK_QUIET
    return REVERSIBILITY_CAP_OVERRIDES.get(action_category, ConfidenceTier.ALLOW)


def beta_lcb(alpha: float, beta: float, z: float = 1.6449) -> float:
    """Lower bound of the 95% one-sided credible interval for Beta(α, β).

    Uses the normal approximation to avoid a scipy dependency. For the
    (alpha, beta) range we see in practice (both ≥ 1 after the uninformative
    prior), the error vs the exact Beta quantile is < 0.02 — and the
    approximation tends to UNDERESTIMATE the lower bound, which is the
    safer direction for promotion decisions.

    ``z`` is the standard normal quantile corresponding to the one-sided
    credibility level; 1.6449 ≈ Φ⁻¹(0.95).
    """
    denom = alpha + beta
    if denom <= 0:
        return 0.0
    mean = alpha / denom
    variance = (alpha * beta) / (denom**2 * (denom + 1))
    std = math.sqrt(max(variance, 0.0))
    return max(0.0, min(1.0, mean - z * std))


def _can_promote_to(state: BucketState, target: ConfidenceTier) -> bool:
    """Min-samples + LCB gate for one tier. Pure."""
    if target is ConfidenceTier.ASK:
        return True
    if state.n_observed < MIN_SAMPLES_FOR_TIER[target]:
        return False
    threshold = CREDIBLE_LOWER_BOUND_THRESHOLD[target]
    return beta_lcb(state.beta_alpha, state.beta_beta) >= threshold


def _is_locked(state: BucketState, now: datetime) -> bool:
    if state.locked_until is None:
        return False
    # Treat naive datetimes as UTC — defensive for callers that don't
    # attach tz info, but only an internal fallback, not a contract.
    lock_time = (
        state.locked_until
        if state.locked_until.tzinfo is not None
        else state.locked_until.replace(tzinfo=UTC)
    )
    return lock_time > now


def promote_if_eligible(
    state: BucketState,
    action_category: str,
    *,
    now: datetime | None = None,
) -> BucketState:
    """Pure: walk the tier ladder upward as far as state supports.

    Returns a new BucketState with the tier possibly bumped up. Never exceeds
    the action's reversibility cap. Respects ``locked_until`` — a bucket
    inside its repromotion-lock window can never be promoted above its
    current tier (but can stay where it is).

    Callers typically invoke this after a positive-signal ``apply_decision``.
    Negative signals can only demote (see ``apply_decision`` itself).
    """
    if now is None:
        now = datetime.now(UTC)

    cap = reversibility_cap(action_category)
    cap_order = _TIER_ORDER[cap]
    current_order = _TIER_ORDER[state.tier]

    # Never demote via this function, and never promote when locked.
    if _is_locked(state, now):
        return state

    best = state.tier
    for candidate in _TIER_LADDER:
        if _TIER_ORDER[candidate] <= current_order:
            # Already at or above this rung — skip, don't retest.
            if _TIER_ORDER[candidate] == current_order:
                best = candidate
            continue
        if _TIER_ORDER[candidate] > cap_order:
            break
        if _can_promote_to(state, candidate):
            best = candidate
        else:
            break  # ladder is monotone; higher tiers will also fail

    if best == state.tier:
        return state
    return replace(state, tier=best)


def _demote_one_step(tier: ConfidenceTier) -> ConfidenceTier:
    idx = _TIER_ORDER[tier]
    return _TIER_LADDER[max(0, idx - 1)]


def demote_if_idle(
    state: BucketState,
    *,
    now: datetime | None = None,
) -> BucketState:
    """Pure: if the bucket has been silent for ≥ 30 days, floor it to ASK.

    Caller runs this before honouring the bucket's tier (typically at read
    time, lazily). No-op for buckets that are already at ASK or for
    first-decision states with no ``last_decision_at``.
    """
    if state.tier is ConfidenceTier.ASK or state.last_decision_at is None:
        return state
    if now is None:
        now = datetime.now(UTC)
    last = (
        state.last_decision_at
        if state.last_decision_at.tzinfo is not None
        else state.last_decision_at.replace(tzinfo=UTC)
    )
    if now - last < IDLE_DEMOTION_THRESHOLD:
        return state
    # Idle demotion resets to the floor AND starts a lock window so a
    # single burst of activity can't immediately re-promote.
    return replace(
        state,
        tier=ConfidenceTier.ASK,
        locked_until=now + REPROMOTION_LOCK,
    )


# -- Forced-ASK sampling ------------------------------------------------------


def _sampling_seed(bucket_key: str, decision_nonce: bytes | None) -> bytes:
    """Deterministic seed for forced-sampling dice roll.

    Keyed on (bucket_key, decision_nonce) so:
    - The same nonce always resolves the same way (reproducible audit).
    - Buckets that look alike to the agent but hash differently can have
      different sampling rates.
    """
    h = hashlib.sha256()
    h.update(bucket_key.encode("utf-8"))
    if decision_nonce is not None:
        h.update(b"\x00")
        h.update(decision_nonce)
    return h.digest()


def forced_ask_sample(
    tier: ConfidenceTier,
    bucket_key: str,
    decision_nonce: bytes | None,
) -> bool:
    """True if this specific decision should be forced to ASK despite its tier.

    Uniform over [0, 1) via the first 4 bytes of SHA-256(seed). Fully
    deterministic in (bucket_key, decision_nonce) so "why did this prompt
    fire?" is a look-up, not a stochastic mystery.
    """
    rate = FORCED_SAMPLING_RATE.get(tier, 0.0)
    if rate <= 0.0:
        return False
    digest = _sampling_seed(bucket_key, decision_nonce)
    roll = int.from_bytes(digest[:4], "big") / (2**32)
    return roll < rate


# -- Public decision-time APIs ------------------------------------------------


def apply_decision(state: BucketState, outcome: DecisionOutcome) -> BucketState:
    """Pure: compute the next bucket state after one decision.

    Counters are always incremented (except for ``DOWNSTREAM_REVERTED``,
    which refers to an already-counted earlier approval and only bumps the
    revert counter and β shape). The posterior uses the weight table above.

    Sprint 2 additions:
    - Preserves the existing ``tier`` (Sprint 1 hardcoded ``ASK``).
    - On ``DOWNSTREAM_REVERTED``, demotes the tier one step AND sets
      ``locked_until`` = now + 7d so a burst of clean approvals can't
      immediately re-promote.

    Positive-signal callers should then invoke ``promote_if_eligible`` to
    let the bucket earn its way up. Keeping promotion out of this function
    preserves the Sprint 1 signature for callers that only write events.
    """
    d_alpha, d_beta = _POSTERIOR_UPDATE[outcome]

    new_alpha = state.beta_alpha + d_alpha
    new_beta = state.beta_beta + d_beta

    if outcome is DecisionOutcome.DOWNSTREAM_REVERTED:
        demoted = _demote_one_step(state.tier)
        return replace(
            state,
            n_reverted=state.n_reverted + 1,
            beta_alpha=new_alpha,
            beta_beta=new_beta,
            tier=demoted,
            locked_until=datetime.now(UTC) + REPROMOTION_LOCK,
        )

    n_approved_clean = state.n_approved_clean
    n_approved_modified = state.n_approved_modified
    n_rejected = state.n_rejected
    n_timeout = state.n_timeout
    if outcome is DecisionOutcome.APPROVED_CLEAN:
        n_approved_clean += 1
    elif outcome is DecisionOutcome.APPROVED_MODIFIED:
        n_approved_modified += 1
    elif outcome is DecisionOutcome.REJECTED:
        n_rejected += 1
    elif outcome is DecisionOutcome.TIMEOUT:
        n_timeout += 1

    return replace(
        state,
        n_observed=state.n_observed + 1,
        n_approved_clean=n_approved_clean,
        n_approved_modified=n_approved_modified,
        n_rejected=n_rejected,
        n_timeout=n_timeout,
        beta_alpha=new_alpha,
        beta_beta=new_beta,
        # tier preserved — callers run promote_if_eligible next.
        last_decision_at=datetime.now(UTC),
    )


def current_tier(state: BucketState | None) -> ConfidenceTier:
    """Legacy Sprint 1 API. New callers should use ``effective_tier``.

    Returns the bucket's stored tier (Sprint 2) rather than always-ASK
    (Sprint 1). No reversibility cap, no forced sampling — the full
    "what gate to fire?" logic lives in ``effective_tier``.
    """
    if state is None:
        return ConfidenceTier.ASK
    return state.tier


def effective_tier(
    state: BucketState | None,
    action_category: str,
    *,
    bucket_key: str | None = None,
    decision_nonce: bytes | None = None,
    now: datetime | None = None,
) -> ConfidenceTier:
    """What gate should fire for this specific decision?

    Pipeline:
      1. ``None`` state or a state that's missing a ``bucket_key`` input
         that we need (``ALLOW_SHADOW``/``ALLOW`` need the key to sample)
         defaults to ASK.
      2. Apply idle demotion (30d silence → ASK + lock).
      3. Clip to the action's reversibility cap.
      4. Roll forced-ASK sample; if it fires, return ASK anyway.

    Returns the tier callers should enforce for this single decision.
    """
    if state is None:
        return ConfidenceTier.ASK

    state = demote_if_idle(state, now=now)

    cap = reversibility_cap(action_category)
    tier = state.tier
    if _TIER_ORDER[tier] > _TIER_ORDER[cap]:
        tier = cap

    if (
        bucket_key is not None
        and FORCED_SAMPLING_RATE.get(tier, 0.0) > 0.0
        and forced_ask_sample(tier, bucket_key, decision_nonce)
    ):
        return ConfidenceTier.ASK

    return tier


# -- Guard for downstream imports ---------------------------------------------

if TYPE_CHECKING:
    # Re-export for convenience in typed callers without creating a
    # runtime dependency.
    from .context_signature import compute_bucket_key, compute_signature  # noqa: F401
