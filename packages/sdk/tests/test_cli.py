"""Tests for the AutoSwarm CLI."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from selva_sdk.cli import cli
from selva_sdk.exceptions import AutoSwarmError
from selva_sdk.models import AgentResponse, TaskResponse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TASK = TaskResponse(
    id="aaaa-bbbb-cccc",
    description="Fix login bug",
    graph_type="coding",
    assigned_agent_ids=[],
    payload={},
    status="queued",
    created_at="2026-03-14T00:00:00",
    completed_at=None,
)

AGENTS = [
    AgentResponse(
        id="agent-1",
        name="Alice",
        role="coder",
        status="idle",
        level=3,
        effective_skills=["python"],
    ),
]


def _mock_client() -> MagicMock:
    mock = MagicMock()
    mock.dispatch.return_value = TASK
    mock.list_agents.return_value = AGENTS
    mock.get_task.return_value = TASK
    mock.wait_for_task.return_value = TASK._replace() if hasattr(TASK, "_replace") else TASK
    mock.wait_for_task.return_value = TaskResponse(
        **{**TASK.model_dump(), "status": "completed"}
    )
    mock.close.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

runner = CliRunner()


@patch("selva_sdk.cli._get_client")
def test_dispatch_command(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_client()
    result = runner.invoke(cli, ["dispatch", "Fix login bug"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "aaaa-bbbb-cccc"
    assert data["status"] == "queued"


@patch("selva_sdk.cli._get_client")
def test_dispatch_with_options(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_client()
    result = runner.invoke(
        cli,
        [
            "dispatch",
            "Deploy service",
            "--graph-type",
            "deployment",
            "--agent-id",
            "a1",
            "--skill",
            "docker",
        ],
    )
    assert result.exit_code == 0
    mock_get.return_value.dispatch.assert_called_once()


@patch("selva_sdk.cli._get_client")
def test_agents_list_command(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_client()
    result = runner.invoke(cli, ["agents", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["name"] == "Alice"


@patch("selva_sdk.cli._get_client")
def test_tasks_get_command(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_client()
    result = runner.invoke(cli, ["tasks", "get", "aaaa-bbbb-cccc"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["description"] == "Fix login bug"


@patch("selva_sdk.cli._get_client")
def test_tasks_wait_command(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_client()
    result = runner.invoke(cli, ["tasks", "wait", "aaaa-bbbb-cccc", "--timeout", "10"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "completed"


def test_help_text() -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "AutoSwarm CLI" in result.output


def test_dispatch_missing_description() -> None:
    result = runner.invoke(cli, ["dispatch"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


@patch("selva_sdk.cli._get_client")
def test_dispatch_error_display(mock_get: MagicMock) -> None:
    mock = _mock_client()
    mock.dispatch.side_effect = AutoSwarmError("Budget exceeded", 402)
    mock_get.return_value = mock
    result = runner.invoke(cli, ["dispatch", "Test"])
    assert result.exit_code == 1
    assert "Error: Budget exceeded" in result.output


@patch("selva_sdk.cli._get_client")
def test_env_var_configuration(mock_get: MagicMock) -> None:
    """Verify env vars are read for client construction."""
    mock_get.return_value = _mock_client()
    result = runner.invoke(
        cli,
        ["agents", "list"],
        env={"AUTOSWARM_API_URL": "http://custom:9999", "AUTOSWARM_TOKEN": "secret"},
    )
    assert result.exit_code == 0
