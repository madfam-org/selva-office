"""Tests for permission engine wiring (Gap 4)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from selva_permissions.types import ActionCategory, PermissionLevel, PermissionResult


class TestCheckPermission:
    """check_permission() helper returns correct results."""

    def test_returns_allow_for_file_read(self) -> None:
        from selva_workers.graphs.base import check_permission

        result = check_permission({"agent_skill_ids": []}, "file_read")

        assert isinstance(result, PermissionResult)
        assert result.level == PermissionLevel.ALLOW

    def test_returns_result_for_file_write(self) -> None:
        from selva_workers.graphs.base import check_permission

        result = check_permission({"agent_skill_ids": []}, "file_write")

        assert isinstance(result, PermissionResult)
        assert result.action_category == ActionCategory.FILE_WRITE

    def test_falls_back_to_api_call_for_unknown_category(self) -> None:
        from selva_workers.graphs.base import check_permission

        result = check_permission({}, "nonexistent_category")

        assert result.action_category == ActionCategory.API_CALL

    def test_uses_skill_overrides_when_available(self) -> None:
        from selva_workers.graphs.base import check_permission

        # Mock skill registry to allow file_write
        mock_registry = MagicMock()
        mock_registry.get_allowed_tools.return_value = ["file_write"]

        with patch(
            "selva_skills.get_skill_registry",
            return_value=mock_registry,
        ):
            result = check_permission(
                {"agent_skill_ids": ["skill-1"]},
                "file_write",
            )

        assert result.level == PermissionLevel.ALLOW


class TestImplementPermissionCheck:
    """implement() respects permission engine decisions."""

    def test_implement_blocked_when_permission_denied(self) -> None:
        from selva_workers.graphs.coding import implement

        mock_result = PermissionResult(
            action_category=ActionCategory.FILE_WRITE,
            level=PermissionLevel.DENY,
            requires_approval=False,
            reason="Denied by policy",
        )

        with patch(
            "selva_workers.graphs.coding.check_permission",
            return_value=mock_result,
        ):
            result = implement(
                {
                    "messages": [],
                    "iteration": 0,
                }
            )

        assert result["status"] == "blocked"

    def test_implement_proceeds_when_permission_allowed(self) -> None:
        from selva_workers.graphs.coding import implement

        mock_result = PermissionResult(
            action_category=ActionCategory.FILE_WRITE,
            level=PermissionLevel.ALLOW,
            requires_approval=False,
            reason="Allowed",
        )

        with patch(
            "selva_workers.graphs.coding.check_permission",
            return_value=mock_result,
        ):
            result = implement(
                {
                    "messages": [
                        AIMessage(
                            content="Plan ready",
                            additional_kwargs={"plan": {"steps": ["step1"]}},
                        )
                    ],
                    "iteration": 0,
                }
            )

        assert result["status"] == "implementing"


class TestCRMPermissionCheck:
    """send() in CRM graph respects permission engine."""

    def test_send_blocked_when_permission_denied(self) -> None:
        from selva_workers.graphs.crm import send

        mock_result = PermissionResult(
            action_category=ActionCategory.EMAIL_SEND,
            level=PermissionLevel.DENY,
            requires_approval=False,
            reason="Denied by policy",
        )

        with patch(
            "selva_workers.graphs.base.check_permission",
            return_value=mock_result,
        ):
            result = send(
                {
                    "messages": [],
                    "status": "approved",
                    "recipient": "test@example.com",
                    "crm_action": "email",
                }
            )

        assert result["status"] == "blocked"

    def test_send_proceeds_when_permission_allowed(self) -> None:
        from selva_workers.graphs.crm import send

        mock_result = PermissionResult(
            action_category=ActionCategory.EMAIL_SEND,
            level=PermissionLevel.ALLOW,
            requires_approval=False,
            reason="Allowed",
        )

        with patch(
            "selva_workers.graphs.base.check_permission",
            return_value=mock_result,
        ):
            result = send(
                {
                    "messages": [],
                    "status": "approved",
                    "recipient": "test@example.com",
                    "crm_action": "email",
                    "task_id": "t1",
                }
            )

        assert result["status"] == "completed"
