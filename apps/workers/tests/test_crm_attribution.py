"""Tests for T3.2 attribution — lead_id threaded through CRM graph send()."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class _FakeToolResult(SimpleNamespace):
    def __init__(self, success: bool = True, data: dict | None = None, error: str = "") -> None:
        super().__init__(success=success, data=data or {"email_id": "em-xyz"}, error=error)


def _allow_perm():
    from autoswarm_permissions.types import PermissionLevel

    result = MagicMock()
    result.level = PermissionLevel.ALLOW
    return result


class TestCRMSendAttributionThreading:
    """Verify send() threads lead_id into the marketing email tool and PostHog."""

    def test_send_passes_lead_id_to_tool_and_emits_playbook_sent(self) -> None:
        from autoswarm_workers.graphs import crm as crm_graph

        captured_kwargs: dict = {}
        posthog_calls: list[tuple] = []

        class _FakeTool:
            async def execute(self, **kwargs):  # type: ignore[no-untyped-def]
                captured_kwargs.update(kwargs)
                return _FakeToolResult(success=True, data={"email_id": "em-abc-123"})

        with (
            patch(
                "autoswarm_workers.graphs.base.check_permission",
                return_value=_allow_perm(),
            ),
            patch(
                "autoswarm_tools.builtins.marketing_tools.SendMarketingEmailTool",
                return_value=_FakeTool(),
            ),
            patch(
                "autoswarm_workers.attribution.emit_playbook_sent",
                side_effect=lambda lead_id, **kw: posthog_calls.append((lead_id, kw)),
            ),
        ):
            result = crm_graph.send({
                "messages": [],
                "task_id": "task-attr-1",
                "recipient": "lupita@acme.mx",
                "contact_email": "lupita@acme.mx",
                "contact_name": "Lupita",
                "crm_action": "email",
                "draft_content": "<p>Hola Lupita!</p>",
                "lead_id": "lead-attr-abc",
                "utm_campaign": "hot_lead_auto",
                "playbook": {"name": "Lead Response", "require_approval": False},
            })

        assert result["status"] == "completed"
        assert result["result"]["email_sent"] is True
        assert result["result"]["lead_id"] == "lead-attr-abc"
        assert result["result"]["email_id"] == "em-abc-123"

        # Tool received lead_id in kwargs
        assert captured_kwargs.get("lead_id") == "lead-attr-abc"
        # utm_campaign suffixed with lead_id for cookie-based checkout reattribution
        assert captured_kwargs.get("utm_campaign") == "hot_lead_auto__lead-attr-abc"

        # PostHog playbook.sent fired with lead_id as distinct_id
        assert len(posthog_calls) == 1
        lead_id, kw = posthog_calls[0]
        assert lead_id == "lead-attr-abc"
        assert kw["playbook_name"] == "Lead Response"
        assert kw["task_id"] == "task-attr-1"
        assert kw["channel"] == "email"
        assert kw["recipient_domain"] == "acme.mx"

    def test_send_without_lead_id_does_not_emit_playbook_sent(self) -> None:
        """No lead_id → no PostHog emit (prevents orphan events)."""
        from autoswarm_workers.graphs import crm as crm_graph

        class _FakeTool:
            async def execute(self, **kwargs):  # type: ignore[no-untyped-def]
                return _FakeToolResult(success=True)

        posthog_calls: list[tuple] = []

        with (
            patch(
                "autoswarm_workers.graphs.base.check_permission",
                return_value=_allow_perm(),
            ),
            patch(
                "autoswarm_tools.builtins.marketing_tools.SendMarketingEmailTool",
                return_value=_FakeTool(),
            ),
            patch(
                "autoswarm_workers.attribution.emit_playbook_sent",
                side_effect=lambda lead_id, **kw: posthog_calls.append((lead_id, kw)),
            ),
        ):
            result = crm_graph.send({
                "messages": [],
                "task_id": "task-no-attr",
                "recipient": "u@x.com",
                "contact_email": "u@x.com",
                "contact_name": "U",
                "crm_action": "email",
                "draft_content": "<p>hi</p>",
                "playbook": {"name": "Lead Response", "require_approval": False},
                # No lead_id
            })

        assert result["status"] == "completed"
        assert posthog_calls == []


class TestAttributionModuleContract:
    """Worker attribution module emits structured log when PostHog unset."""

    def test_emit_playbook_sent_logs_when_no_posthog(self, caplog) -> None:
        import logging

        from autoswarm_workers import attribution as attr

        # Force unconfigured state
        attr._client = None
        attr._init_attempted = True

        with caplog.at_level(logging.INFO, logger=attr.__name__):
            attr.emit_playbook_sent(
                "lead-xyz",
                playbook_name="Lead Response",
                task_id="task-1",
                channel="email",
                recipient_domain="example.com",
            )

        assert any(
            "[attribution]" in record.message
            and "lead-xyz" in record.message
            and "playbook.sent" in record.message
            for record in caplog.records
        )

    def test_emit_playbook_sent_skips_empty_lead_id(self) -> None:
        from autoswarm_workers import attribution as attr

        attr.emit_playbook_sent(
            "",
            playbook_name="x",
            task_id="y",
            channel="email",
        )

    def test_domain_of_worker(self) -> None:
        from autoswarm_workers.attribution import domain_of

        assert domain_of("a@Example.com") == "example.com"
        assert domain_of("no-at-sign") is None
        assert domain_of("") is None
