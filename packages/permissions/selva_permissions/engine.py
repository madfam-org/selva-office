"""Permission evaluation engine for the HITL system."""

from __future__ import annotations

from .context_rules import ContextRule, PermissionContext
from .matrix import DEFAULT_PERMISSION_MATRIX
from .playbook import PlaybookGuard
from .types import ActionCategory, PermissionLevel, PermissionResult


class PermissionEngine:
    """Evaluates permission requests against a configurable matrix.

    The engine looks up the requested action category in its internal
    matrix and returns a ``PermissionResult`` indicating whether the
    action is allowed, requires approval, or is denied.

    When a ``PermissionContext`` is supplied, registered context rules
    can escalate the decision (ALLOW -> ASK, ASK -> DENY) but never
    relax it.
    """

    def __init__(
        self,
        matrix: dict[ActionCategory, PermissionLevel] | None = None,
        overrides: dict[ActionCategory, PermissionLevel] | None = None,
        context_rules: list[ContextRule] | None = None,
    ) -> None:
        self._matrix: dict[ActionCategory, PermissionLevel] = dict(
            matrix or DEFAULT_PERMISSION_MATRIX
        )
        if overrides:
            self._matrix.update(overrides)
        self._context_rules: list[ContextRule] = context_rules or []

    def evaluate(
        self,
        category: ActionCategory,
        context: PermissionContext | dict | None = None,
        playbook_guard: PlaybookGuard | None = None,
    ) -> PermissionResult:
        """Evaluate whether an action is permitted.

        Args:
            category: The action category to evaluate.
            context: Optional ``PermissionContext`` (or raw dict) for
                     context-aware rule evaluation.
            playbook_guard: Optional ``PlaybookGuard`` for bounded autonomous
                     execution. Playbooks can relax ASK→ALLOW within their
                     declared boundaries, but NEVER override DENY.

        Returns:
            A ``PermissionResult`` with the decision and reasoning.
        """
        level = self._matrix.get(category, PermissionLevel.ASK)

        # Playbook check: if a playbook is active and the default level is ASK,
        # the playbook can relax it to ALLOW within its boundaries.
        # Playbooks NEVER override DENY (safety first).
        if playbook_guard is not None and level == PermissionLevel.ASK:
            playbook_level = playbook_guard.evaluate(category)
            if playbook_level == PermissionLevel.ALLOW:
                return PermissionResult(
                    action_category=category,
                    level=PermissionLevel.ALLOW,
                    requires_approval=False,
                    reason=(
                        f"Action '{category.value}' auto-approved by playbook "
                        f"'{playbook_guard.state.playbook.name}' "
                        f"(tokens: {playbook_guard.state.tokens_used}/{playbook_guard.state.playbook.token_budget})."
                    ),
                )

        # Apply context rules if context is provided.
        perm_context: PermissionContext | None = None
        if context is not None:
            if isinstance(context, PermissionContext):
                perm_context = context
            elif isinstance(context, dict):
                perm_context = PermissionContext(**context)

        escalation_reasons: list[str] = []
        if perm_context is not None and self._context_rules:
            for rule in self._context_rules:
                new_level = rule.evaluate(category, level, perm_context)
                if new_level is not None and new_level != level:
                    escalation_reasons.append(
                        f"{type(rule).__name__} escalated {level.value} -> {new_level.value}"
                    )
                    level = new_level

        if level == PermissionLevel.ALLOW:
            return PermissionResult(
                action_category=category,
                level=level,
                requires_approval=False,
                reason=f"Action '{category.value}' is allowed by default policy.",
            )

        if level == PermissionLevel.DENY:
            reason = f"Action '{category.value}' is denied by policy."
            if escalation_reasons:
                reason += " " + "; ".join(escalation_reasons)
            return PermissionResult(
                action_category=category,
                level=level,
                requires_approval=False,
                reason=reason,
            )

        # ASK / ASK_DUAL — both require approval; ASK_DUAL additionally
        # requires a second distinct approver, enforced by the approval
        # queue consumer (not this engine). Keeping the distinction in
        # the returned `level` lets callers render the right UI.
        if level == PermissionLevel.ASK_DUAL:
            reason = (
                f"Action '{category.value}' requires TWO distinct "
                "human approvers before execution."
            )
        else:
            reason = f"Action '{category.value}' requires human approval before execution."
        if escalation_reasons:
            reason += " " + "; ".join(escalation_reasons)
        return PermissionResult(
            action_category=category,
            level=level,
            requires_approval=True,
            reason=reason,
        )

    def update_permission(
        self,
        category: ActionCategory,
        level: PermissionLevel,
    ) -> None:
        """Update the permission level for a specific action category."""
        self._matrix[category] = level

    def should_interrupt(self, category: ActionCategory) -> bool:
        """Return ``True`` if the action requires a human-in-the-loop check."""
        level = self._matrix.get(category, PermissionLevel.ASK)
        return level in (PermissionLevel.ASK, PermissionLevel.ASK_DUAL)
