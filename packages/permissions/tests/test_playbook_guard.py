"""Tests for the PlaybookGuard bounded autonomous execution system.

Covers PlaybookDefinition dataclass, PlaybookExecutionState budget tracking,
and PlaybookGuard evaluation logic including:
- Allowed/denied action categories
- Token budget enforcement
- Financial cap enforcement
- require_approval override
- State recording via record_action
"""

from __future__ import annotations

import pytest

from autoswarm_permissions.playbook import (
    PlaybookDefinition,
    PlaybookExecutionState,
    PlaybookGuard,
)
from autoswarm_permissions.types import ActionCategory, PermissionLevel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def lead_response_playbook() -> PlaybookDefinition:
    """A playbook that allows CRM and email actions with moderate budgets."""
    return PlaybookDefinition(
        id="pb-lead-001",
        name="Lead Response",
        trigger_event="crm:hot_lead",
        allowed_actions={"api_call", "email_send", "crm_update"},
        token_budget=50,
        financial_cap_cents=500,
    )


@pytest.fixture()
def zero_financial_playbook() -> PlaybookDefinition:
    """A playbook with no financial exposure allowed."""
    return PlaybookDefinition(
        id="pb-content-001",
        name="Content Publish",
        trigger_event="content:scheduled_post",
        allowed_actions={"api_call"},
        token_budget=30,
        financial_cap_cents=0,
    )


@pytest.fixture()
def hitl_playbook() -> PlaybookDefinition:
    """A playbook that requires HITL approval despite having allowed actions."""
    return PlaybookDefinition(
        id="pb-migration-001",
        name="DB Migration Runner",
        trigger_event="infra:migration_pending",
        allowed_actions={"infrastructure_exec", "database_migration"},
        token_budget=30,
        financial_cap_cents=0,
        require_approval=True,
    )


# ---------------------------------------------------------------------------
# PlaybookDefinition
# ---------------------------------------------------------------------------


class TestPlaybookDefinition:
    """Verify dataclass construction and default values."""

    def test_defaults(self) -> None:
        pb = PlaybookDefinition(
            id="test",
            name="Test",
            trigger_event="test:event",
            allowed_actions={"api_call"},
            token_budget=10,
            financial_cap_cents=0,
        )
        assert pb.require_approval is False

    def test_require_approval_override(self, hitl_playbook: PlaybookDefinition) -> None:
        assert hitl_playbook.require_approval is True


# ---------------------------------------------------------------------------
# PlaybookExecutionState
# ---------------------------------------------------------------------------


class TestPlaybookExecutionState:
    """Verify budget tracking properties."""

    def test_tokens_remaining_initial(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        assert state.tokens_remaining == 50
        assert state.is_budget_exhausted is False

    def test_tokens_remaining_after_usage(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook, tokens_used=30)
        assert state.tokens_remaining == 20

    def test_tokens_remaining_at_limit(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook, tokens_used=50)
        assert state.tokens_remaining == 0
        assert state.is_budget_exhausted is True

    def test_tokens_remaining_over_limit(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook, tokens_used=60)
        assert state.tokens_remaining == 0
        assert state.is_budget_exhausted is True

    def test_dollars_remaining_initial(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        assert state.dollars_remaining_cents == 500

    def test_dollars_remaining_after_exposure(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(
            playbook=lead_response_playbook,
            dollars_exposed_cents=200,
        )
        assert state.dollars_remaining_cents == 300

    def test_dollars_remaining_at_zero_cap(self, zero_financial_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=zero_financial_playbook)
        assert state.dollars_remaining_cents == 0

    def test_actions_taken_default_empty(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        assert state.actions_taken == []


# ---------------------------------------------------------------------------
# PlaybookGuard — Action Category Checks
# ---------------------------------------------------------------------------


class TestPlaybookGuardActionCategory:
    """Check 1: is the action category in the allowed set?"""

    def test_allowed_action_returns_allow(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.EMAIL_SEND)
        assert result == PermissionLevel.ALLOW

    def test_disallowed_action_returns_deny(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.DEPLOY)
        assert result == PermissionLevel.DENY

    def test_api_call_allowed(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.API_CALL)
        assert result == PermissionLevel.ALLOW

    def test_crm_update_allowed(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.CRM_UPDATE)
        assert result == PermissionLevel.ALLOW

    def test_file_write_denied(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.FILE_WRITE)
        assert result == PermissionLevel.DENY


# ---------------------------------------------------------------------------
# PlaybookGuard — Token Budget Enforcement
# ---------------------------------------------------------------------------


class TestPlaybookGuardTokenBudget:
    """Check 2: token budget enforcement."""

    def test_within_budget_allows(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook, tokens_used=20)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.API_CALL, token_cost=10)
        assert result == PermissionLevel.ALLOW

    def test_exactly_at_budget_allows(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook, tokens_used=40)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.API_CALL, token_cost=10)
        assert result == PermissionLevel.ALLOW

    def test_over_budget_denies(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook, tokens_used=45)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.API_CALL, token_cost=10)
        assert result == PermissionLevel.DENY

    def test_zero_token_cost_ignores_budget(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook, tokens_used=50)
        guard = PlaybookGuard(state)
        # Zero cost should pass even when budget is exhausted
        result = guard.evaluate(ActionCategory.API_CALL, token_cost=0)
        assert result == PermissionLevel.ALLOW


# ---------------------------------------------------------------------------
# PlaybookGuard — Financial Cap Enforcement
# ---------------------------------------------------------------------------


class TestPlaybookGuardFinancialCap:
    """Check 3: financial cap enforcement."""

    def test_within_cap_allows(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook, dollars_exposed_cents=100)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.API_CALL, financial_exposure_cents=200)
        assert result == PermissionLevel.ALLOW

    def test_exactly_at_cap_allows(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook, dollars_exposed_cents=300)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.API_CALL, financial_exposure_cents=200)
        assert result == PermissionLevel.ALLOW

    def test_over_cap_denies(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook, dollars_exposed_cents=400)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.API_CALL, financial_exposure_cents=200)
        assert result == PermissionLevel.DENY

    def test_zero_cap_denies_any_financial_action(
        self, zero_financial_playbook: PlaybookDefinition
    ) -> None:
        state = PlaybookExecutionState(playbook=zero_financial_playbook)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.API_CALL, financial_exposure_cents=1)
        assert result == PermissionLevel.DENY

    def test_zero_exposure_ignores_cap(
        self, zero_financial_playbook: PlaybookDefinition
    ) -> None:
        state = PlaybookExecutionState(playbook=zero_financial_playbook)
        guard = PlaybookGuard(state)
        # Zero financial exposure should pass even with $0 cap
        result = guard.evaluate(ActionCategory.API_CALL, financial_exposure_cents=0)
        assert result == PermissionLevel.ALLOW


# ---------------------------------------------------------------------------
# PlaybookGuard — require_approval Override
# ---------------------------------------------------------------------------


class TestPlaybookGuardRequireApproval:
    """When require_approval is True, guard falls through to ASK."""

    def test_require_approval_returns_ask(self, hitl_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=hitl_playbook)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.DATABASE_MIGRATION)
        assert result == PermissionLevel.ASK

    def test_require_approval_even_for_allowed_action(
        self, hitl_playbook: PlaybookDefinition
    ) -> None:
        """Even an action in the allowed set returns ASK when require_approval is set."""
        state = PlaybookExecutionState(playbook=hitl_playbook)
        guard = PlaybookGuard(state)
        result = guard.evaluate(ActionCategory.INFRASTRUCTURE_EXEC)
        assert result == PermissionLevel.ASK


# ---------------------------------------------------------------------------
# PlaybookGuard — record_action
# ---------------------------------------------------------------------------


class TestPlaybookGuardRecordAction:
    """Verify that record_action correctly deducts from budgets."""

    def test_record_deducts_tokens(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)
        guard.record_action(ActionCategory.API_CALL, token_cost=10)
        assert state.tokens_used == 10
        assert state.tokens_remaining == 40

    def test_record_deducts_financial(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)
        guard.record_action(ActionCategory.API_CALL, financial_cents=100)
        assert state.dollars_exposed_cents == 100
        assert state.dollars_remaining_cents == 400

    def test_record_appends_action(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)
        guard.record_action(ActionCategory.EMAIL_SEND, token_cost=5)
        guard.record_action(ActionCategory.CRM_UPDATE, token_cost=3)
        assert state.actions_taken == ["email_send", "crm_update"]
        assert state.tokens_used == 8

    def test_multiple_records_accumulate(self, lead_response_playbook: PlaybookDefinition) -> None:
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)
        guard.record_action(ActionCategory.API_CALL, token_cost=10, financial_cents=50)
        guard.record_action(ActionCategory.API_CALL, token_cost=15, financial_cents=100)
        assert state.tokens_used == 25
        assert state.dollars_exposed_cents == 150


# ---------------------------------------------------------------------------
# PlaybookGuard + PermissionEngine Integration
# ---------------------------------------------------------------------------


class TestPlaybookEngineIntegration:
    """Verify that PlaybookGuard integrates correctly with PermissionEngine.evaluate()."""

    def test_playbook_relaxes_ask_to_allow(
        self, lead_response_playbook: PlaybookDefinition
    ) -> None:
        """When the matrix says ASK and the playbook allows, result is ALLOW."""
        from autoswarm_permissions.engine import PermissionEngine

        engine = PermissionEngine()
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)

        # EMAIL_SEND is ASK by default; playbook should relax to ALLOW
        result = engine.evaluate(ActionCategory.EMAIL_SEND, playbook_guard=guard)
        assert result.level == PermissionLevel.ALLOW
        assert "auto-approved by playbook" in result.reason

    def test_playbook_does_not_override_deny(
        self, lead_response_playbook: PlaybookDefinition
    ) -> None:
        """When the matrix says DENY, playbook cannot relax it."""
        from autoswarm_permissions.engine import PermissionEngine

        engine = PermissionEngine(
            overrides={ActionCategory.EMAIL_SEND: PermissionLevel.DENY}
        )
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)

        result = engine.evaluate(ActionCategory.EMAIL_SEND, playbook_guard=guard)
        assert result.level == PermissionLevel.DENY

    def test_playbook_does_not_affect_already_allowed(
        self, lead_response_playbook: PlaybookDefinition
    ) -> None:
        """When the matrix already says ALLOW, playbook is not consulted."""
        from autoswarm_permissions.engine import PermissionEngine

        engine = PermissionEngine()
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)

        # API_CALL is ALLOW by default in matrix
        result = engine.evaluate(ActionCategory.API_CALL, playbook_guard=guard)
        assert result.level == PermissionLevel.ALLOW
        # Reason should be from default policy, not playbook
        assert "allowed by default policy" in result.reason

    def test_playbook_denied_action_stays_ask(
        self, lead_response_playbook: PlaybookDefinition
    ) -> None:
        """When playbook denies an action, engine ASK default persists."""
        from autoswarm_permissions.engine import PermissionEngine

        engine = PermissionEngine()
        state = PlaybookExecutionState(playbook=lead_response_playbook)
        guard = PlaybookGuard(state)

        # DEPLOY is ASK by default but NOT in playbook's allowed actions
        result = engine.evaluate(ActionCategory.DEPLOY, playbook_guard=guard)
        assert result.level == PermissionLevel.ASK
        assert result.requires_approval is True
