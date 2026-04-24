"""Tests for YAML serialization/deserialization."""

from __future__ import annotations

import pytest
import yaml

from selva_workflows.schema import (
    EdgeDefinition,
    NodeDefinition,
    NodeType,
    TriggerCondition,
    WorkflowDefinition,
)
from selva_workflows.serializer import WorkflowSerializer


class TestWorkflowSerializer:
    def test_roundtrip_simple(self) -> None:
        wf = WorkflowDefinition(
            name="test-workflow",
            description="A test workflow",
            nodes=[
                NodeDefinition(id="start", type=NodeType.AGENT, system_prompt="Hello"),
                NodeDefinition(id="end", type=NodeType.PASSTHROUGH),
            ],
            edges=[EdgeDefinition(source="start", target="end")],
        )
        yaml_str = WorkflowSerializer.to_yaml(wf)
        restored = WorkflowSerializer.from_yaml(yaml_str)
        assert restored.name == wf.name
        assert len(restored.nodes) == 2
        assert len(restored.edges) == 1
        assert restored.nodes[0].system_prompt == "Hello"

    def test_roundtrip_with_conditions(self) -> None:
        wf = WorkflowDefinition(
            name="conditional",
            nodes=[
                NodeDefinition(id="check", type=NodeType.AGENT),
                NodeDefinition(id="yes", type=NodeType.AGENT),
                NodeDefinition(id="no", type=NodeType.AGENT),
            ],
            edges=[
                EdgeDefinition(
                    source="check",
                    target="yes",
                    condition=TriggerCondition(keyword="approved"),
                ),
                EdgeDefinition(source="check", target="no"),
            ],
        )
        yaml_str = WorkflowSerializer.to_yaml(wf)
        restored = WorkflowSerializer.from_yaml(yaml_str)
        assert len(restored.edges) == 2
        assert restored.edges[0].condition is not None
        assert restored.edges[0].condition.keyword == "approved"

    def test_roundtrip_with_variables(self) -> None:
        wf = WorkflowDefinition(
            name="vars",
            nodes=[NodeDefinition(id="n", type=NodeType.LITERAL, literal_value=42)],
            variables={"lang": "python", "max_retries": 3},
        )
        yaml_str = WorkflowSerializer.to_yaml(wf)
        restored = WorkflowSerializer.from_yaml(yaml_str)
        assert restored.variables["lang"] == "python"
        assert restored.variables["max_retries"] == 3
        assert restored.nodes[0].literal_value == 42

    def test_from_yaml_invalid(self) -> None:
        with pytest.raises((ValueError, yaml.YAMLError)):
            WorkflowSerializer.from_yaml("not: valid: yaml: [}")

    def test_from_yaml_wrong_type(self) -> None:
        with pytest.raises(ValueError, match="Expected a YAML mapping"):
            WorkflowSerializer.from_yaml("- just a list")

    def test_dict_roundtrip(self) -> None:
        wf = WorkflowDefinition(
            name="dict-test",
            nodes=[NodeDefinition(id="a", type=NodeType.AGENT)],
        )
        d = WorkflowSerializer.to_dict(wf)
        assert isinstance(d, dict)
        restored = WorkflowSerializer.from_dict(d)
        assert restored.name == "dict-test"
