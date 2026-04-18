"""Tests for context-aware permission rules."""

from __future__ import annotations

from datetime import UTC, datetime

from selva_permissions import (
    DEFAULT_CONTEXT_RULES,
    DEFAULT_PERMISSION_MATRIX,
    ROLE_PERMISSION_MATRICES,
    PermissionContext,
    PermissionEngine,
    RiskScoreRule,
    RoleMatrixRule,
    TimeOfDayRule,
    TrustLevelRule,
)
from selva_permissions.types import ActionCategory, PermissionLevel


class TestTimeOfDayRule:
    """TimeOfDayRule blocks destructive actions outside business hours."""

    def test_blocks_deploy_after_hours(self) -> None:
        rule = TimeOfDayRule()
        ctx = PermissionContext(time_utc=datetime(2025, 6, 1, 23, 0, tzinfo=UTC))
        result = rule.evaluate(ActionCategory.DEPLOY, PermissionLevel.ALLOW, ctx)
        assert result == PermissionLevel.ASK

    def test_escalates_ask_to_deny_after_hours(self) -> None:
        rule = TimeOfDayRule()
        ctx = PermissionContext(time_utc=datetime(2025, 6, 1, 3, 0, tzinfo=UTC))
        result = rule.evaluate(ActionCategory.GIT_PUSH, PermissionLevel.ASK, ctx)
        assert result == PermissionLevel.DENY

    def test_allows_during_business_hours(self) -> None:
        rule = TimeOfDayRule()
        ctx = PermissionContext(time_utc=datetime(2025, 6, 1, 14, 0, tzinfo=UTC))
        result = rule.evaluate(ActionCategory.DEPLOY, PermissionLevel.ALLOW, ctx)
        assert result is None

    def test_no_effect_on_non_destructive(self) -> None:
        rule = TimeOfDayRule()
        ctx = PermissionContext(time_utc=datetime(2025, 6, 1, 23, 0, tzinfo=UTC))
        result = rule.evaluate(ActionCategory.FILE_READ, PermissionLevel.ALLOW, ctx)
        assert result is None


class TestTrustLevelRule:
    """TrustLevelRule escalates ALLOW to ASK for low-level agents."""

    def test_escalates_low_level_agent(self) -> None:
        rule = TrustLevelRule()
        ctx = PermissionContext(agent_level=1)
        result = rule.evaluate(ActionCategory.GIT_PUSH, PermissionLevel.ALLOW, ctx)
        assert result == PermissionLevel.ASK

    def test_no_effect_on_high_level_agent(self) -> None:
        rule = TrustLevelRule()
        ctx = PermissionContext(agent_level=5)
        result = rule.evaluate(ActionCategory.GIT_PUSH, PermissionLevel.ALLOW, ctx)
        assert result is None

    def test_no_effect_on_non_destructive(self) -> None:
        rule = TrustLevelRule()
        ctx = PermissionContext(agent_level=1)
        result = rule.evaluate(ActionCategory.FILE_READ, PermissionLevel.ALLOW, ctx)
        assert result is None


class TestRiskScoreRule:
    """RiskScoreRule forces ASK when risk score exceeds threshold."""

    def test_forces_ask_above_threshold(self) -> None:
        rule = RiskScoreRule()
        ctx = PermissionContext(risk_score=0.9)
        result = rule.evaluate(ActionCategory.API_CALL, PermissionLevel.ALLOW, ctx)
        assert result == PermissionLevel.ASK

    def test_no_effect_below_threshold(self) -> None:
        rule = RiskScoreRule()
        ctx = PermissionContext(risk_score=0.3)
        result = rule.evaluate(ActionCategory.API_CALL, PermissionLevel.ALLOW, ctx)
        assert result is None


class TestRoleMatrixRule:
    """RoleMatrixRule applies per-role permission overrides."""

    def test_reviewer_cannot_push(self) -> None:
        rule = RoleMatrixRule(ROLE_PERMISSION_MATRICES)
        ctx = PermissionContext(agent_role="reviewer")
        result = rule.evaluate(ActionCategory.GIT_PUSH, PermissionLevel.ASK, ctx)
        assert result == PermissionLevel.DENY

    def test_researcher_cannot_email(self) -> None:
        rule = RoleMatrixRule(ROLE_PERMISSION_MATRICES)
        ctx = PermissionContext(agent_role="researcher")
        result = rule.evaluate(ActionCategory.EMAIL_SEND, PermissionLevel.ASK, ctx)
        assert result == PermissionLevel.DENY

    def test_coder_cannot_update_crm(self) -> None:
        rule = RoleMatrixRule(ROLE_PERMISSION_MATRICES)
        ctx = PermissionContext(agent_role="coder")
        result = rule.evaluate(ActionCategory.CRM_UPDATE, PermissionLevel.ASK, ctx)
        assert result == PermissionLevel.DENY

    def test_unknown_role_no_effect(self) -> None:
        rule = RoleMatrixRule(ROLE_PERMISSION_MATRICES)
        ctx = PermissionContext(agent_role="wizard")
        result = rule.evaluate(ActionCategory.GIT_PUSH, PermissionLevel.ALLOW, ctx)
        assert result is None

    def test_never_relaxes_permission(self) -> None:
        """A role matrix entry that would relax DENY -> ALLOW is ignored."""
        rule = RoleMatrixRule({"lax_role": {ActionCategory.DEPLOY: PermissionLevel.ALLOW}})
        ctx = PermissionContext(agent_role="lax_role")
        result = rule.evaluate(ActionCategory.DEPLOY, PermissionLevel.DENY, ctx)
        assert result is None


class TestRuleComposition:
    """Rules compose: strictest wins."""

    def test_strictest_wins(self) -> None:
        """After-hours on an ASK action should escalate to DENY."""
        engine = PermissionEngine(
            matrix={ActionCategory.GIT_PUSH: PermissionLevel.ASK},
            context_rules=DEFAULT_CONTEXT_RULES,
        )
        ctx = PermissionContext(
            time_utc=datetime(2025, 6, 1, 2, 0, tzinfo=UTC),
            agent_level=1,
        )
        result = engine.evaluate(ActionCategory.GIT_PUSH, context=ctx)
        # TimeOfDayRule escalates ASK -> DENY for after-hours destructive actions
        assert result.level == PermissionLevel.DENY

    def test_context_with_role_matrix(self) -> None:
        """RoleMatrixRule combined with default rules."""
        rule = RoleMatrixRule(ROLE_PERMISSION_MATRICES)
        engine = PermissionEngine(
            matrix=DEFAULT_PERMISSION_MATRIX,
            context_rules=[*DEFAULT_CONTEXT_RULES, rule],
        )
        ctx = PermissionContext(
            time_utc=datetime(2025, 6, 1, 14, 0, tzinfo=UTC),
            agent_role="reviewer",
        )
        result = engine.evaluate(ActionCategory.GIT_PUSH, context=ctx)
        assert result.level == PermissionLevel.DENY
        assert not result.requires_approval
