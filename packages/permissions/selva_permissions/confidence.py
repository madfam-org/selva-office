"""HITL confidence tracking (Sprint 1 — observe only).

Module boundary: this package holds the *policy* (what a decision means
for the Beta posterior, how buckets are keyed) but never touches the DB
directly. The nexus-api side imports these pure functions, then persists
the results through SQLAlchemy using its own session.

Why split it that way: the permissions package is used by workers too,
and we don't want to drag SQLAlchemy / asyncpg into the worker image
just for confidence tracking. Workers emit events; nexus-api writes them.

Sprint 1 scope: no tier changes. ``current_tier()`` always returns
``ASK``. ``apply_decision()`` is a pure function that takes an existing
bucket state and a decision, returning the next state — callers persist
it. Sprint 2 (promotion) layers a policy check on top of the same
function surface.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class BucketState:
    """A read-only snapshot of a bucket's rolling counters + posterior.

    The DB model stores the same fields; this dataclass is the in-memory
    form that pure update functions operate on. Callers load a row into
    this shape, call ``apply_decision``, and write the resulting state back.
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
)


def apply_decision(state: BucketState, outcome: DecisionOutcome) -> BucketState:
    """Pure: compute the next bucket state after one decision.

    The caller is responsible for persisting the returned state. Counters
    are always incremented; the posterior uses the weight table above.
    Tier is never changed by Sprint 1 — always returns ``ASK``.

    Downstream-revert rows refer to an earlier approved decision, so we
    do NOT re-increment ``n_observed`` (the original approve was already
    counted); we only bump ``n_reverted`` and the β shape. This matters
    for Sprint 2's promotion maths — n_observed has to mean unique
    decisions, not unique events.
    """
    d_alpha, d_beta = _POSTERIOR_UPDATE[outcome]

    new_alpha = state.beta_alpha + d_alpha
    new_beta = state.beta_beta + d_beta

    if outcome is DecisionOutcome.DOWNSTREAM_REVERTED:
        return BucketState(
            n_observed=state.n_observed,
            n_approved_clean=state.n_approved_clean,
            n_approved_modified=state.n_approved_modified,
            n_rejected=state.n_rejected,
            n_timeout=state.n_timeout,
            n_reverted=state.n_reverted + 1,
            beta_alpha=new_alpha,
            beta_beta=new_beta,
            tier=ConfidenceTier.ASK,  # Sprint 1 never promotes.
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

    return BucketState(
        n_observed=state.n_observed + 1,
        n_approved_clean=n_approved_clean,
        n_approved_modified=n_approved_modified,
        n_rejected=n_rejected,
        n_timeout=n_timeout,
        n_reverted=state.n_reverted,
        beta_alpha=new_alpha,
        beta_beta=new_beta,
        tier=ConfidenceTier.ASK,
    )


def current_tier(state: BucketState | None) -> ConfidenceTier:
    """Sprint 1: everything is ASK. Sprint 2 will honour the bucket's tier.

    Kept as a distinct function so callers that want "what gate should
    fire?" don't have to know that Sprint 1 is a no-op. When Sprint 2
    ships, only this function needs to change.
    """
    if state is None:
        return ConfidenceTier.ASK
    # Even once the promotion rules land, we'll keep ASK as the floor
    # until the data model has the tier column populated — paranoid but
    # cheap, and it's the right default for a freshly migrated DB.
    return ConfidenceTier.ASK


# -- Guard for downstream imports ---------------------------------------------

if TYPE_CHECKING:
    # Re-export for convenience in typed callers without creating a
    # runtime dependency.
    from .context_signature import compute_bucket_key, compute_signature  # noqa: F401
