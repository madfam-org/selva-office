"""Pure tests for the HITL confidence module (no DB)."""

from __future__ import annotations

import pytest

from selva_permissions import (
    INITIAL_BUCKET_STATE,
    BucketState,
    ConfidenceTier,
    DecisionOutcome,
    apply_decision,
    compute_bucket_key,
    compute_signature,
    current_tier,
    features_for,
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
        after_approve = apply_decision(
            INITIAL_BUCKET_STATE, DecisionOutcome.APPROVED_CLEAN
        )
        assert after_approve.n_observed == 1
        after_revert = apply_decision(
            after_approve, DecisionOutcome.DOWNSTREAM_REVERTED
        )
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
            outcome = (
                DecisionOutcome.APPROVED_CLEAN
                if i % 5 != 0
                else DecisionOutcome.REJECTED
            )
            s = apply_decision(s, outcome)
        assert s.n_observed == 100
        assert s.n_approved_clean == 80
        assert s.n_rejected == 20
        # Beta(81, 21) mean ~= 0.794 — bounded around 0.79-0.80.
        assert 0.78 < s.confidence < 0.81

    def test_sprint1_tier_stays_ask_always(self) -> None:
        """No matter the decision sequence, tier stays ASK in Sprint 1."""
        s = INITIAL_BUCKET_STATE
        for _ in range(100):
            s = apply_decision(s, DecisionOutcome.APPROVED_CLEAN)
            assert s.tier is ConfidenceTier.ASK


class TestCurrentTier:
    def test_none_state_returns_ask(self) -> None:
        assert current_tier(None) is ConfidenceTier.ASK

    def test_populated_state_still_returns_ask(self) -> None:
        """Sprint 1 is observe-only: even a high-confidence bucket gates."""
        s = BucketState(
            n_observed=1000,
            n_approved_clean=1000,
            n_approved_modified=0,
            n_rejected=0,
            n_timeout=0,
            n_reverted=0,
            beta_alpha=1001.0,
            beta_beta=1.0,
            tier=ConfidenceTier.ALLOW,  # even if someone else set it
        )
        assert current_tier(s) is ConfidenceTier.ASK


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
        assert compute_signature("email_send", ctx) == compute_signature(
            "email_send", ctx
        )

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
        short = compute_signature(
            "email_send", {**base_ctx, "body_length": 100}
        )
        xlong = compute_signature(
            "email_send", {**base_ctx, "body_length": 6000}
        )
        assert short != xlong

    def test_deploy_signature_includes_migration_flag(self) -> None:
        base = {"repo": "nexus-api", "environment": "production"}
        without = compute_signature(
            "deploy", {**base, "changed_paths": ["src/api.py"]}
        )
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
        a = compute_signature(
            "deploy", {**base, "changed_paths": ["tests/test_foo.py"]}
        )
        b = compute_signature(
            "deploy", {**base, "changed_paths": ["tests/test_bar.py"]}
        )
        assert a == b

    def test_unknown_category_uses_generic_features(self) -> None:
        sig = compute_signature(
            "totally_new_action", {"agent_role": "some_agent"}
        )
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

    def test_bucket_key_is_deterministic(self) -> None:
        args = ("agent-1", "email_send", "org-1", "fakesig")
        assert compute_bucket_key(*args) == compute_bucket_key(*args)
