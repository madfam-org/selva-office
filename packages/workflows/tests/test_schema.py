"""Tests for workflow definition schema and Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from selva_workflows.schema import (
    ContextPolicyConfig,
    ContextWindowPolicy,
    EdgeDefinition,
    NodeDefinition,
    NodeType,
    TriggerCondition,
    WorkflowDefinition,
)


class TestNodeDefinition:
    def test_minimal_agent_node(self) -> None:
        node = NodeDefinition(id="my-node", type=NodeType.AGENT)
        assert node.id == "my-node"
        assert node.type == NodeType.AGENT
        assert node.tools == []
        assert node.context_policy.type == ContextWindowPolicy.KEEP_ALL

    def test_agent_node_with_config(self) -> None:
        node = NodeDefinition(
            id="coder",
            type=NodeType.AGENT,
            model="gpt-4",
            system_prompt="You are a coder",
            tools=["bash", "git_commit"],
            temperature=0.5,
        )
        assert node.model == "gpt-4"
        assert node.temperature == 0.5
        assert len(node.tools) == 2

    def test_invalid_node_id(self) -> None:
        with pytest.raises(ValidationError):
            NodeDefinition(id="bad id!", type=NodeType.AGENT)

    def test_subgraph_node(self) -> None:
        node = NodeDefinition(
            id="sub", type=NodeType.SUBGRAPH, subgraph_id="other-workflow"
        )
        assert node.subgraph_id == "other-workflow"

    def test_python_runner_node(self) -> None:
        node = NodeDefinition(
            id="runner",
            type=NodeType.PYTHON_RUNNER,
            code="result = 42",
        )
        assert node.code == "result = 42"

    def test_context_policy(self) -> None:
        node = NodeDefinition(
            id="trimmed",
            type=NodeType.AGENT,
            context_policy=ContextPolicyConfig(
                type=ContextWindowPolicy.KEEP_LAST_N, n=5
            ),
        )
        assert node.context_policy.type == ContextWindowPolicy.KEEP_LAST_N
        assert node.context_policy.n == 5


class TestEdgeDefinition:
    def test_simple_edge(self) -> None:
        edge = EdgeDefinition(source="a", target="b")
        assert edge.carry_data is True
        assert edge.condition is None

    def test_conditional_edge_regex(self) -> None:
        edge = EdgeDefinition(
            source="a",
            target="b",
            condition=TriggerCondition(regex=r"\bapproved\b"),
        )
        assert edge.condition is not None
        assert edge.condition.regex == r"\bapproved\b"

    def test_conditional_edge_keyword(self) -> None:
        edge = EdgeDefinition(
            source="a",
            target="b",
            condition=TriggerCondition(keyword="success"),
        )
        assert edge.condition is not None
        assert edge.condition.keyword == "success"

    def test_conditional_edge_expression(self) -> None:
        edge = EdgeDefinition(
            source="a",
            target="b",
            condition=TriggerCondition(expression='variables.get("score", 0) > 0.8'),
        )
        assert edge.condition is not None


class TestWorkflowDefinition:
    def test_minimal_workflow(self) -> None:
        wf = WorkflowDefinition(
            name="test",
            nodes=[NodeDefinition(id="start", type=NodeType.AGENT)],
        )
        assert wf.name == "test"
        assert wf.version == "1.0.0"
        assert len(wf.nodes) == 1

    def test_workflow_with_variables(self) -> None:
        wf = WorkflowDefinition(
            name="test",
            nodes=[NodeDefinition(id="start", type=NodeType.AGENT)],
            variables={"target_lang": "python", "max_retries": 3},
        )
        assert wf.variables["target_lang"] == "python"

    def test_requires_at_least_one_node(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowDefinition(name="empty", nodes=[])
