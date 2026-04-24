"""Per-action-category context signatures for HITL confidence buckets.

A bucket is meaningful only if "approved 20 times" refers to the *same
kind* of request. Hashing the full payload defeats aggregation (every
request is unique); hashing nothing collapses all actions into one
bucket (one ``ALLOW`` authorises everything). The middle ground is a
**normalised feature vector** per action category.

Each signature function takes a context dict and returns a stable,
hash-friendly dict of feature→bucket mappings. The signature itself is
the sha256 of the canonically-serialised features, so callers never
need to touch the feature values directly.

Schemas are versioned: incrementing ``SIGNATURE_VERSION`` for a category
invalidates every historical bucket under the old version, which is the
safe-fail behaviour (lost history → re-observe from scratch, not
carry-over potentially wrong trust). Sprint 1 uses version 1 everywhere.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

SIGNATURE_VERSION: int = 1


# -- Bucketing helpers --------------------------------------------------------


def _body_length_bucket(n: int) -> str:
    """Collapse body-length into buckets so subtle variance doesn't shard buckets."""
    if n < 200:
        return "short"
    if n < 1000:
        return "medium"
    if n < 4000:
        return "long"
    return "xlong"


def _budget_bucket_cents(amount_cents: int | None) -> str:
    """Token / dollar spend buckets for LLM calls."""
    if amount_cents is None:
        return "unknown"
    if amount_cents < 100:
        return "under_1usd"
    if amount_cents < 1000:
        return "under_10usd"
    if amount_cents < 10_000:
        return "under_100usd"
    return "over_100usd"


_DOMAIN_RE = re.compile(r"^[^@\s]+@([^@\s]+)$")


def _recipient_domain(email: str | None) -> str:
    if not email:
        return "unknown"
    m = _DOMAIN_RE.match(email.strip().lower())
    if not m:
        return "malformed"
    return m.group(1)


def _glob_bucket(paths: list[str] | None) -> str:
    """Summarise a changed-file list as a coarse bucket.

    We don't want per-file shards, but we do want to distinguish "migration
    touched" from "tests only" — those have very different blast radiuses.
    """
    if not paths:
        return "none"
    joined = " ".join(paths).lower()
    has_migration = "migrations/" in joined or "alembic/" in joined
    has_prod_code = any(not p.startswith(("tests/", "test/", "docs/")) for p in paths)
    has_tests_only = all(p.startswith(("tests/", "test/")) for p in paths)
    if has_migration:
        return "migration"
    if has_tests_only:
        return "tests_only"
    if has_prod_code:
        return "prod_code"
    return "other"


# -- Per-category signature functions -----------------------------------------


def email_send_features(ctx: dict[str, Any]) -> dict[str, Any]:
    """Features for email_send decisions.

    Buckets are built from stable template + audience shape. Subject-line
    wording variance does NOT change the bucket — that's the whole point
    of the signature. If the sender, template, audience domain, and agent
    role all match a previously-approved pattern, we're looking at the
    same kind of decision.
    """
    return {
        "version": SIGNATURE_VERSION,
        "category": "email_send",
        "template_id": ctx.get("template_id") or "inline",
        "recipient_domain": _recipient_domain(ctx.get("recipient_email")),
        "lead_stage": ctx.get("lead_stage") or "unknown",
        "agent_role": ctx.get("agent_role") or "unknown",
        "has_attachments": bool(ctx.get("attachments")),
        "body_length": _body_length_bucket(int(ctx.get("body_length") or 0)),
    }


def deploy_features(ctx: dict[str, Any]) -> dict[str, Any]:
    """Features for deploy decisions.

    Repo + environment + kind-of-change is the signature. "Deploy web to
    staging after editing test files" is a different bucket from "deploy
    web to production after touching a migration".
    """
    return {
        "version": SIGNATURE_VERSION,
        "category": "deploy",
        "repo": ctx.get("repo") or "unknown",
        "environment": ctx.get("environment") or "unknown",
        "changed_paths_bucket": _glob_bucket(ctx.get("changed_paths")),
        "has_db_migration": bool(ctx.get("has_db_migration")),
    }


def llm_call_features(ctx: dict[str, Any]) -> dict[str, Any]:
    """Features for llm_call decisions.

    Provider + model + task + rough spend bucket. The budget bucket is
    a coarse cents estimate — not the exact cost — so pennies of drift
    don't create new buckets.
    """
    return {
        "version": SIGNATURE_VERSION,
        "category": "llm_call",
        "provider": ctx.get("provider") or "unknown",
        "model": ctx.get("model") or "unknown",
        "task_type": ctx.get("task_type") or "unknown",
        "budget": _budget_bucket_cents(ctx.get("estimated_cost_cents")),
    }


def generic_features(action_category: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """Fallback for action categories with no dedicated featuriser yet.

    Uses a coarse shape: action + org + a handful of whitelisted keys
    the caller thought were relevant. Intentionally conservative — when
    in doubt, group more aggressively. A too-narrow bucket that never
    accumulates N is a promotion-prevention bug; a too-wide bucket is
    a safety bug. Wide is better until we have a dedicated featuriser.
    """
    return {
        "version": SIGNATURE_VERSION,
        "category": action_category,
        "role": ctx.get("agent_role") or "unknown",
    }


_FEATURISERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "email_send": email_send_features,
    "deploy": deploy_features,
    "llm_call": llm_call_features,
}


def features_for(action_category: str, ctx: dict[str, Any]) -> dict[str, Any]:
    fn = _FEATURISERS.get(action_category)
    if fn is not None:
        return fn(ctx)
    return generic_features(action_category, ctx)


def signature_hash(features: dict[str, Any]) -> str:
    """Stable sha256 over the canonical JSON form of the features.

    Sorting keys ensures different orderings of the same features hash
    to the same value. Truncated to 32 hex chars (128 bits) — collisions
    at that width are astronomically rare for the bucket volume we'll see.
    """
    canonical = json.dumps(features, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def compute_signature(action_category: str, ctx: dict[str, Any]) -> str:
    """One-shot: features → hash. The signature callers actually use."""
    return signature_hash(features_for(action_category, ctx))


def compute_bucket_key(
    agent_id: str | None,
    action_category: str,
    org_id: str,
    context_signature: str,
) -> str:
    """Stable per-bucket key. Agent-less decisions use ``*`` as the agent slot."""
    agent = agent_id or "*"
    raw = f"{agent}|{action_category}|{org_id}|{context_signature}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
