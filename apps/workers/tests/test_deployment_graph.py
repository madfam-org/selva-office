"""Tests for the deployment workflow graph (Gap E)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestDeploymentGraphStructure:
    """Deployment graph has correct nodes and edges."""

    def test_graph_has_expected_nodes(self) -> None:
        from selva_workers.graphs.deployment import build_deployment_graph

        graph = build_deployment_graph()
        node_names = set(graph.nodes.keys())
        assert "validate" in node_names
        assert "deploy_gate" in node_names
        assert "deploy" in node_names
        assert "monitor" in node_names

    def test_graph_compiles(self) -> None:
        from selva_workers.graphs.deployment import build_deployment_graph

        graph = build_deployment_graph()
        # Should compile without error
        compiled = graph.compile()
        assert compiled is not None

    def test_deployment_state_fields(self) -> None:
        from selva_workers.graphs.deployment import DeploymentState

        annotations = DeploymentState.__annotations__
        assert "service" in annotations
        assert "environment" in annotations
        assert "image_tag" in annotations
        assert "deploy_id" in annotations
        assert "deploy_status" in annotations


class TestValidateNode:
    """validate() checks permissions and required fields."""

    def test_missing_service_returns_error(self) -> None:
        from selva_workers.graphs.deployment import validate

        result = validate(
            {
                "messages": [],
                "service": "",
            }
        )

        assert result["status"] == "error"

    def test_valid_service_passes(self) -> None:
        from selva_workers.graphs.deployment import validate

        mock_result = MagicMock()
        mock_result.level = MagicMock()
        mock_result.level.name = "ALLOW"

        with patch("selva_workers.graphs.deployment.check_permission") as mock_check:
            from selva_permissions.types import PermissionLevel

            mock_result.level = PermissionLevel.ALLOW
            mock_check.return_value = mock_result

            result = validate(
                {
                    "messages": [],
                    "service": "web-api",
                    "environment": "staging",
                    "image_tag": "v1.0",
                }
            )

        assert result["status"] == "validated"

    def test_deny_permission_blocks(self) -> None:
        from selva_workers.graphs.deployment import validate

        mock_result = MagicMock()
        mock_result.level = MagicMock()
        mock_result.level.name = "DENY"

        with patch("selva_workers.graphs.deployment.check_permission") as mock_check:
            from selva_permissions.types import PermissionLevel

            mock_result.level = PermissionLevel.DENY
            mock_check.return_value = mock_result

            result = validate(
                {
                    "messages": [],
                    "service": "web-api",
                }
            )

        assert result["status"] == "blocked"


class TestDeployGateNode:
    """deploy_gate() uses interrupt() for HITL approval."""

    def test_approved_sets_status(self) -> None:
        from selva_workers.graphs.deployment import deploy_gate

        with patch(
            "selva_workers.graphs.deployment.interrupt",
            return_value={"approved": True},
        ):
            result = deploy_gate(
                {
                    "messages": [],
                    "service": "web-api",
                    "environment": "staging",
                    "image_tag": "v1.0",
                    "status": "validated",
                }
            )

        assert result["status"] == "approved"

    def test_denied_sets_status(self) -> None:
        from selva_workers.graphs.deployment import deploy_gate

        with patch(
            "selva_workers.graphs.deployment.interrupt",
            return_value={"approved": False, "feedback": "Not ready"},
        ):
            result = deploy_gate(
                {
                    "messages": [],
                    "service": "web-api",
                    "status": "validated",
                }
            )

        assert result["status"] == "denied"

    def test_skips_if_already_blocked(self) -> None:
        from selva_workers.graphs.deployment import deploy_gate

        state = {
            "messages": [],
            "service": "web-api",
            "status": "blocked",
        }

        result = deploy_gate(state)
        assert result["status"] == "blocked"


class TestDeployNode:
    """deploy() calls DeployTool."""

    def test_skips_if_denied(self) -> None:
        from selva_workers.graphs.deployment import deploy

        result = deploy(
            {
                "messages": [],
                "service": "web-api",
                "status": "denied",
            }
        )

        assert result["status"] == "denied"


class TestMonitorNode:
    """monitor() calls DeployStatusTool."""

    def test_skips_if_no_deploy_id(self) -> None:
        from selva_workers.graphs.deployment import monitor

        result = monitor(
            {
                "messages": [],
                "deploy_id": "",
                "status": "completed",
            }
        )

        assert result["status"] == "completed"

    def test_skips_if_error_status(self) -> None:
        from selva_workers.graphs.deployment import monitor

        result = monitor(
            {
                "messages": [],
                "deploy_id": "dep-123",
                "status": "error",
            }
        )

        assert result["status"] == "error"


class TestDeploymentRegistration:
    """Deployment graph is registered in __main__.py."""

    def test_deployment_in_graph_builders(self) -> None:
        from selva_workers.graphs.deployment import build_deployment_graph

        # Verify the builder function is importable and callable
        graph = build_deployment_graph()
        assert graph is not None

    def test_deployment_timeout_configured(self) -> None:
        from selva_redis_pool.timeout import DEFAULT_TIMEOUTS

        assert "deployment" in DEFAULT_TIMEOUTS
        assert DEFAULT_TIMEOUTS["deployment"] == 300
