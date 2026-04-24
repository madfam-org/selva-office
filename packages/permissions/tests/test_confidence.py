"""Pure tests for the HITL confidence module (no DB)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from selva_permissions import (
    FORCED_SAMPLING_RATE,
    HIGH_REVERSIBILITY_COST_CATEGORIES,
    INITIAL_BUCKET_STATE,
    BucketState,
    ConfidenceTier,
    DecisionOutcome,
    apply_decision,
    beta_lcb,
    compute_bucket_key,
    compute_signature,
    current_tier,
    demote_if_idle,
    effective_tier,
    features_for,
    forced_ask_sample,
    promote_if_eligible,
    reversibility_cap,
)

# -- Beta posterior updates ---------------------------------------------------


class TestApplyDecision:
    def test_initial_state_is_uninformative(self) -> None:
        s = INITIAL_BUCKET_STATE
        assert s.n_observed == 0
        assert s.beta_alpha == 1.0
        assert s.beta_beta == 1.0
        assert s.confidence == 0.5

    def test_approved_clean_increments_alpha_and_counter(self) -> None:
        s = apply_decision(INITIAL_BUCKET_STATE, DecisionOutcome.APPROVED_CLEAN)
        assert s.n_observed == 1
        assert s.n_approved_clean == 1
        assert s.beta_alpha == pytest.approx(2.0)
        assert s.beta_beta == pytest.approx(1.0)
        # Mean of Beta(2,1) = 2/3.
        assert s.confidence == pytest.approx(2 / 3)

    def test_rejected_increments_beta_and_counter(self) -> None:
        s = apply_decision(INITIAL_BUCKET_STATE, DecisionOutcome.REJECTED)
        assert s.n_observed == 1
        assert s.n_rejected == 1
        assert s.beta_alpha == pytest.approx(1.0)
        assert s.beta_beta == pytest.approx(2.0)
        assert s.confidence == pytest.approx(1 / 3)

    def test_approved_modified_is_partial(self) -> None:
        """0.3 alpha + 0.7 beta — modification is a partial rejection."""
        s = apply_decision(INITIAL_BUCKET_STATE, DecisionOutcome.APPROVED_MODIFIED)
        assert s.n_approved_modified == 1
        assert s.beta_alpha == pytest.approx(1.3)
        assert s.beta_beta == pytest.approx(1.7)

    def test_timeout_is_soft_negative(self) -> None:
        s = apply_decision(INITIAL_BUCKET_STATE, DecisionOutcome.TIMEOUT)
        assert s.n_timeout == 1
        assert s.beta_alpha == pytest.approx(1.0)
        assert s.beta_beta == pytest.approx(1.5)

    def test_downstream_revert_does_not_bump_observed(self) -> None:
        """Reverts refer to an already-counted approval."""
        after_approve = apply_decision(INITIAL_BUCKET_STATE, DecisionOutcome.APPROVED_CLEAN)
        assert after_approve.n_observed == 1
        after_revert = apply_decision(after_approve, DecisionOutcome.DOWNSTREAM_REVERTED)
        assert after_revert.n_observed == 1  # unchanged
        assert after_revert.n_reverted == 1
        assert after_revert.beta_beta == pytest.approx(3.0)  # β += 2.0

    def test_sequence_many_approvals_grows_confidence_monotonically(self) -> None:
        s = INITIAL_BUCKET_STATE
        prev = 0.5
        for _ in range(10):
            s = apply_decision(s, DecisionOutcome.APPROVED_CLEAN)
            assert s.confidence >= prev
            prev = s.confidence
        # After 10 clean approvals, mean should be > 0.9.
        assert s.confidence > 0.9
        assert s.n_observed == 10

    def test_mixed_sequence_converges_to_expected_ratio(self) -> None:
        """80% clean, 20% rejected over 100 decisions → mean ~ 0.80."""
        s = INITIAL_BUCKET_STATE
        for i in range(100):
            outcome = DecisionOutcome.APPROVED_CLEAN if i % 5 != 0 else DecisionOutcome.REJECTED
            s = apply_decision(s, outcome)
        assert s.n_observed == 100
        assert s.n_approved_clean == 80
        assert s.n_rejected == 20
        # Beta(81, 21) mean ~= 0.794 — bounded around 0.79-0.80.
        assert 0.78 < s.confidence < 0.81

    def test_apply_decision_preserves_tier(self) -> None:
        """apply_decision updates counters + posterior but never bumps tier.

        Promotion is the caller's responsibility via promote_if_eligible;
        demotion is this function's job only on DOWNSTREAM_REVERTED.
        """
        s = INITIAL_BUCKET_STATE
        for _ in range(100):
            s = apply_decision(s, DecisionOutcome.APPROVED_CLEAN)
            assert s.tier is ConfidenceTier.ASK  # never auto-promoted


class TestCurrentTier:
    def test_none_state_returns_ask(self) -> None:
        assert current_tier(None) is ConfidenceTier.ASK

    def test_returns_stored_tier(self) -> None:
        """Legacy API: returns whatever tier the bucket stores (Sprint 2)."""
        s = BucketState(
            n_observed=1000,
            n_approved_clean=1000,
            n_approved_modified=0,
            n_rejected=0,
            n_timeout=0,
            n_reverted=0,
            beta_alpha=1001.0,
            beta_beta=1.0,
            tier=ConfidenceTier.ALLOW,
        )
        assert current_tier(s) is ConfidenceTier.ALLOW


# -- Context signatures -------------------------------------------------------


class TestContextSignature:
    def test_same_features_produce_same_signature(self) -> None:
        ctx = {
            "template_id": "welcome",
            "recipient_email": "alice@example.com",
            "lead_stage": "new",
            "agent_role": "heraldo",
            "body_length": 450,
        }
        assert compute_signature("email_send", ctx) == compute_signature("email_send", ctx)

    def test_different_templates_produce_different_signatures(self) -> None:
        a = compute_signature(
            "email_send",
            {"template_id": "welcome", "recipient_email": "a@b.com"},
        )
        b = compute_signature(
            "email_send",
            {"template_id": "followup", "recipient_email": "a@b.com"},
        )
        assert a != b

    def test_subject_line_variance_doesnt_shard(self) -> None:
        """Two emails with the same template + audience should share a bucket."""
        base_ctx = {
            "template_id": "welcome",
            "recipient_email": "alice@example.com",
            "lead_stage": "new",
            "agent_role": "heraldo",
        }
        sig_a = compute_signature(
            "email_send", {**base_ctx, "body_length": 300, "subject": "Hi Alice!"}
        )
        sig_b = compute_signature(
            "email_send", {**base_ctx, "body_length": 320, "subject": "Hello Alice!"}
        )
        assert sig_a == sig_b  # same bucket — subject isn't a feature

    def test_body_length_buckets_fold_nearby_sizes(self) -> None:
        """200-char and 900-char bodies both land in `medium`."""
        base_ctx = {
            "template_id": "welcome",
            "recipient_email": "alice@example.com",
            "agent_role": "heraldo",
        }
        a = compute_signature("email_send", {**base_ctx, "body_length": 250})
        b = compute_signature("email_send", {**base_ctx, "body_length": 900})
        assert a == b

    def test_body_length_across_bucket_boundary_shards(self) -> None:
        """200-char (medium) and 5000-char (xlong) must be different buckets."""
        base_ctx = {
            "template_id": "welcome",
            "recipient_email": "alice@example.com",
            "agent_role": "heraldo",
        }
        short = compute_signature("email_send", {**base_ctx, "body_length": 100})
        xlong = compute_signature("email_send", {**base_ctx, "body_length": 6000})
        assert short != xlong

    def test_deploy_signature_includes_migration_flag(self) -> None:
        base = {"repo": "nexus-api", "environment": "production"}
        without = compute_signature("deploy", {**base, "changed_paths": ["src/api.py"]})
        with_mig = compute_signature(
            "deploy",
            {
                **base,
                "changed_paths": ["src/api.py", "migrations/0018_foo.py"],
                "has_db_migration": True,
            },
        )
        assert without != with_mig

    def test_deploy_tests_only_buckets_together(self) -> None:
        base = {"repo": "nexus-api", "environment": "production"}
        a = compute_signature("deploy", {**base, "changed_paths": ["tests/test_foo.py"]})
        b = compute_signature("deploy", {**base, "changed_paths": ["tests/test_bar.py"]})
        assert a == b

    def test_unknown_category_uses_generic_features(self) -> None:
        sig = compute_signature("totally_new_action", {"agent_role": "some_agent"})
        assert isinstance(sig, str)
        assert len(sig) == 32  # 32 hex chars = 128-bit truncated sha256

    def test_features_exposes_version_field(self) -> None:
        for category in ("email_send", "deploy", "llm_call", "brand_new"):
            features = features_for(category, {})
            assert "version" in features


class TestBucketKey:
    def test_distinct_dimensions_produce_distinct_keys(self) -> None:
        sig = compute_signature("email_send", {"template_id": "welcome"})
        k1 = compute_bucket_key("agent-1", "email_send", "org-1", sig)
        k2 = compute_bucket_key("agent-2", "email_send", "org-1", sig)
        k3 = compute_bucket_key("agent-1", "email_send", "org-2", sig)
        k4 = compute_bucket_key("agent-1", "deploy", "org-1", sig)
        assert k1 != k2 != k3 != k4
        assert len({k1, k2, k3, k4}) == 4

    def test_none_agent_uses_wildcard_slot(self) -> None:
        sig = compute_signature("deploy", {})
        assert compute_bucket_key(None, "deploy", "org-1", sig) == compute_bucket_key(
            None, "deploy", "org-1", sig
        )


# -- Sprint 2: Beta LCB ------------------------------------------------------


class TestBetaLCB:
    def test_uniform_prior_is_below_mean(self) -> None:
        # Beta(1,1) mean=0.5, LCB strictly < 0.5 at 95%.
        lcb = beta_lcb(1.0, 1.0)
        assert 0.0 <= lcb < 0.5

    def test_heavy_positive_pulls_lcb_up(self) -> None:
        # 100 cleans / 0 rejects → very tight posterior, LCB ≥ 0.95.
        lcb = beta_lcb(101.0, 1.0)
        assert lcb >= 0.95

    def test_balanced_stays_near_mean(self) -> None:
        # 10 pos / 10 neg → mean 0.5, moderate spread.
        lcb = beta_lcb(11.0, 11.0)
        assert 0.3 < lcb < 0.5

    def test_degenerate_zero_mass_returns_zero(self) -> None:
        assert beta_lcb(0.0, 0.0) == 0.0


# -- Sprint 2: reversibility caps --------------------------------------------


class TestReversibilityCap:
    def test_high_cost_categories_cap_at_ask_quiet(self) -> None:
        for category in HIGH_REVERSIBILITY_COST_CATEGORIES:
            assert reversibility_cap(category) is ConfidenceTier.ASK_QUIET

    def test_arbitrary_category_defaults_to_allow(self) -> None:
        assert reversibility_cap("llm_call") is ConfidenceTier.ALLOW
        assert reversibility_cap("file_write") is ConfidenceTier.ALLOW


# -- Sprint 2: promote_if_eligible -------------------------------------------


def _saturate_clean(n: int) -> BucketState:
    """Shortcut: bucket with n clean approvals and nothing else."""
    s = INITIAL_BUCKET_STATE
    for _ in range(n):
        s = apply_decision(s, DecisionOutcome.APPROVED_CLEAN)
    return s


class TestPromoteIfEligible:
    def test_fresh_bucket_stays_ask(self) -> None:
        s = promote_if_eligible(INITIAL_BUCKET_STATE, "llm_call")
        assert s.tier is ConfidenceTier.ASK

    def test_min_samples_blocks_promotion_below_threshold(self) -> None:
        # 9 cleans → LCB might be high but sample count is still 9 < 10.
        s = _saturate_clean(9)
        s = promote_if_eligible(s, "llm_call")
        assert s.tier is ConfidenceTier.ASK

    def test_reaches_ask_quiet_at_10_clean(self) -> None:
        s = _saturate_clean(10)
        s = promote_if_eligible(s, "llm_call")
        assert s.tier is ConfidenceTier.ASK_QUIET

    def test_reaches_allow_shadow_at_30_clean(self) -> None:
        s = _saturate_clean(30)
        s = promote_if_eligible(s, "llm_call")
        assert s.tier is ConfidenceTier.ALLOW_SHADOW

    def test_reaches_allow_at_100_clean(self) -> None:
        s = _saturate_clean(100)
        s = promote_if_eligible(s, "llm_call")
        assert s.tier is ConfidenceTier.ALLOW

    def test_high_reversibility_category_hard_capped_at_ask_quiet(self) -> None:
        s = _saturate_clean(1000)
        s = promote_if_eligible(s, "deploy")
        assert s.tier is ConfidenceTier.ASK_QUIET

    def test_spend_capped_at_ask_quiet(self) -> None:
        s = _saturate_clean(1000)
        s = promote_if_eligible(s, "spend")
        assert s.tier is ConfidenceTier.ASK_QUIET

    def test_external_communication_capped_at_ask_quiet(self) -> None:
        s = _saturate_clean(1000)
        s = promote_if_eligible(s, "external_communication")
        assert s.tier is ConfidenceTier.ASK_QUIET

    def test_locked_bucket_does_not_promote(self) -> None:
        s = _saturate_clean(100)
        s = replace(s, locked_until=datetime.now(UTC) + timedelta(days=1))
        s = promote_if_eligible(s, "llm_call")
        assert s.tier is ConfidenceTier.ASK  # stayed where it was

    def test_expired_lock_allows_promotion(self) -> None:
        s = _saturate_clean(100)
        s = replace(s, locked_until=datetime.now(UTC) - timedelta(days=1))
        s = promote_if_eligible(s, "llm_call")
        assert s.tier is ConfidenceTier.ALLOW

    def test_rejections_block_promotion_via_lcb(self) -> None:
        # 30 cleans + 30 rejects → LCB < 0.7, should not promote.
        s = INITIAL_BUCKET_STATE
        for _ in range(30):
            s = apply_decision(s, DecisionOutcome.APPROVED_CLEAN)
        for _ in range(30):
            s = apply_decision(s, DecisionOutcome.REJECTED)
        s = promote_if_eligible(s, "llm_call")
        assert s.tier is ConfidenceTier.ASK


# -- Sprint 2: downstream-revert demotion ------------------------------------


class TestApplyDecisionRevertDemotes:
    def test_revert_drops_tier_one_step(self) -> None:
        s = _saturate_clean(100)
        s = promote_if_eligible(s, "llm_call")
        assert s.tier is ConfidenceTier.ALLOW
        s = apply_decision(s, DecisionOutcome.DOWNSTREAM_REVERTED)
        assert s.tier is ConfidenceTier.ALLOW_SHADOW

    def test_revert_at_ask_stays_at_ask(self) -> None:
        s = apply_decision(INITIAL_BUCKET_STATE, DecisionOutcome.DOWNSTREAM_REVERTED)
        assert s.tier is ConfidenceTier.ASK

    def test_revert_sets_locked_until(self) -> None:
        s = _saturate_clean(100)
        s = promote_if_eligible(s, "llm_call")
        before = datetime.now(UTC)
        s = apply_decision(s, DecisionOutcome.DOWNSTREAM_REVERTED)
        assert s.locked_until is not None
        assert s.locked_until > before


# -- Sprint 2: idle demotion -------------------------------------------------


class TestDemoteIfIdle:
    def test_fresh_bucket_no_op(self) -> None:
        s = _saturate_clean(100)
        s = promote_if_eligible(s, "llm_call")  # now has last_decision_at
        out = demote_if_idle(s, now=s.last_decision_at + timedelta(minutes=1))
        assert out.tier is ConfidenceTier.ALLOW

    def test_idle_30d_demotes_to_ask(self) -> None:
        s = _saturate_clean(100)
        s = promote_if_eligible(s, "llm_call")
        far_future = s.last_decision_at + timedelta(days=31)
        out = demote_if_idle(s, now=far_future)
        assert out.tier is ConfidenceTier.ASK

    def test_idle_demotion_sets_lock(self) -> None:
        s = _saturate_clean(100)
        s = promote_if_eligible(s, "llm_call")
        far = s.last_decision_at + timedelta(days=40)
        out = demote_if_idle(s, now=far)
        assert out.locked_until is not None
        assert out.locked_until > far

    def test_ask_state_noop(self) -> None:
        s = INITIAL_BUCKET_STATE
        out = demote_if_idle(s, now=datetime.now(UTC))
        assert out is s  # same object, unchanged


# -- Sprint 2: forced-ASK sampling -------------------------------------------


class TestForcedAskSample:
    def test_ask_tier_never_samples(self) -> None:
        for i in range(100):
            assert not forced_ask_sample(ConfidenceTier.ASK, "bk", str(i).encode())

    def test_ask_quiet_never_samples(self) -> None:
        # FORCED_SAMPLING_RATE is 0 for ASK_QUIET — UI already shows everything.
        for i in range(100):
            assert not forced_ask_sample(ConfidenceTier.ASK_QUIET, "bk", str(i).encode())

    def test_allow_samples_near_configured_rate(self) -> None:
        rate = FORCED_SAMPLING_RATE[ConfidenceTier.ALLOW]
        hits = sum(
            forced_ask_sample(ConfidenceTier.ALLOW, "bk", str(i).encode()) for i in range(2000)
        )
        empirical = hits / 2000
        # 2000 trials at p=0.05 — 95% CI ≈ ±0.01. Generous ±0.02.
        assert abs(empirical - rate) < 0.02

    def test_deterministic_same_nonce(self) -> None:
        r1 = forced_ask_sample(ConfidenceTier.ALLOW, "bk", b"decision-xyz")
        r2 = forced_ask_sample(ConfidenceTier.ALLOW, "bk", b"decision-xyz")
        assert r1 == r2

    def test_different_buckets_resolve_independently(self) -> None:
        # Very small chance of collision by design — just confirm it CAN differ.
        bucket_a = [
            forced_ask_sample(ConfidenceTier.ALLOW, "bucket-a", str(i).encode()) for i in range(100)
        ]
        bucket_b = [
            forced_ask_sample(ConfidenceTier.ALLOW, "bucket-b", str(i).encode()) for i in range(100)
        ]
        assert bucket_a != bucket_b


# -- Sprint 2: effective_tier composition ------------------------------------


class TestEffectiveTier:
    def test_none_state_returns_ask(self) -> None:
        assert effective_tier(None, "llm_call") is ConfidenceTier.ASK

    def test_allow_tier_in_deploy_drops_to_ask_quiet(self) -> None:
        s = _saturate_clean(100)
        s = promote_if_eligible(s, "llm_call")  # ALLOW
        assert effective_tier(s, "deploy") is ConfidenceTier.ASK_QUIET

    def test_idle_demotion_applied_at_read(self) -> None:
        s = _saturate_clean(100)
        s = promote_if_eligible(s, "llm_call")
        # Simulate reading the bucket 31 days later.
        far = s.last_decision_at + timedelta(days=31)
        assert effective_tier(s, "llm_call", now=far) is ConfidenceTier.ASK

    def test_forced_sampling_returns_ask(self) -> None:
        """Find a nonce that triggers a forced sample."""
        s = _saturate_clean(100)
        s = promote_if_eligible(s, "llm_call")  # ALLOW
        # 5% rate → in 100 tries we'll almost certainly hit one.
        found_sample = False
        for i in range(200):
            nonce = f"try-{i}".encode()
            if forced_ask_sample(ConfidenceTier.ALLOW, "bucket-1", nonce):
                result = effective_tier(
                    s,
                    "llm_call",
                    bucket_key="bucket-1",
                    decision_nonce=nonce,
                )
                assert result is ConfidenceTier.ASK
                found_sample = True
                break
        assert found_sample, "expected at least one forced sample in 200 tries"

    def test_nonce_that_doesnt_sample_returns_tier(self) -> None:
        s = _saturate_clean(100)
        s = promote_if_eligible(s, "llm_call")
        # Find a nonce that does NOT trigger.
        for i in range(200):
            nonce = f"try-{i}".encode()
            if not forced_ask_sample(ConfidenceTier.ALLOW, "bucket-1", nonce):
                result = effective_tier(
                    s,
                    "llm_call",
                    bucket_key="bucket-1",
                    decision_nonce=nonce,
                )
                assert result is ConfidenceTier.ALLOW
                return
        pytest.fail("could not find a non-sampling nonce in 200 tries")

    def test_bucket_key_is_deterministic(self) -> None:
        args = ("agent-1", "email_send", "org-1", "fakesig")
        assert compute_bucket_key(*args) == compute_bucket_key(*args)
