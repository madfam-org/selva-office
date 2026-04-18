"""Tests for workflow validation."""

from __future__ import annotations

from selva_workflows.schema import (
    EdgeDefinition,
    NodeDefinition,
    NodeType,
    TriggerCondition,
    WorkflowDefinition,
)
from selva_workflows.validator import WorkflowValidator


def _make_workflow(**kwargs) -> WorkflowDefinition:  # type: ignore[no-untyped-def]
    defaults = {
        "name": "test",
        "nodes": [NodeDefinition(id="start", type=NodeType.AGENT)],
    }
    defaults.update(kwargs)
    return WorkflowDefinition(**defaults)


class TestWorkflowValidator:
    def setup_method(self) -> None:
        self.validator = WorkflowValidator()

    def test_valid_single_node(self) -> None:
        wf = _make_workflow()
        result = self.validator.validate(wf)
        assert result.is_valid

    def test_valid_linear_chain(self) -> None:
        wf = _make_workflow(
            nodes=[
                NodeDefinition(id="a", type=NodeType.AGENT),
                NodeDefinition(id="b", type=NodeType.AGENT),
                NodeDefinition(id="c", type=NodeType.AGENT),
            ],
            edges=[
                EdgeDefinition(source="a", target="b"),
                EdgeDefinition(source="b", target="c"),
            ],
        )
        result = self.validator.validate(wf)
        assert result.is_valid

    def test_duplicate_node_ids(self) -> None:
        wf = _make_workflow(
            nodes=[
                NodeDefinition(id="dup", type=NodeType.AGENT),
                NodeDefinition(id="dup", type=NodeType.PASSTHROUGH),
            ],
        )
        result = self.validator.validate(wf)
        assert not result.is_valid
        assert any(e.code == "DUPLICATE_NODE_ID" for e in result.errors)

    def test_invalid_entry_node(self) -> None:
        wf = _make_workflow(entry_node="nonexistent")
        result = self.validator.validate(wf)
        assert not result.is_valid
        assert any(e.code == "INVALID_ENTRY_NODE" for e in result.errors)

    def test_invalid_edge_source(self) -> None:
        wf = _make_workflow(
            nodes=[NodeDefinition(id="a", type=NodeType.AGENT)],
            edges=[EdgeDefinition(source="nonexistent", target="a")],
        )
        result = self.validator.validate(wf)
        assert not result.is_valid
        assert any(e.code == "INVALID_EDGE_SOURCE" for e in result.errors)

    def test_invalid_edge_target(self) -> None:
        wf = _make_workflow(
            nodes=[NodeDefinition(id="a", type=NodeType.AGENT)],
            edges=[EdgeDefinition(source="a", target="nonexistent")],
        )
        result = self.validator.validate(wf)
        assert not result.is_valid
        assert any(e.code == "INVALID_EDGE_TARGET" for e in result.errors)

    def test_orphan_node_warning(self) -> None:
        wf = _make_workflow(
            nodes=[
                NodeDefinition(id="a", type=NodeType.AGENT),
                NodeDefinition(id="orphan", type=NodeType.AGENT),
            ],
            edges=[],
        )
        result = self.validator.validate(wf)
        assert result.is_valid  # orphan is a warning, not error
        assert any(w.code == "ORPHAN_NODE" for w in result.warnings)

    def test_cycle_detection(self) -> None:
        wf = _make_workflow(
            nodes=[
                NodeDefinition(id="a", type=NodeType.AGENT),
                NodeDefinition(id="b", type=NodeType.AGENT),
            ],
            edges=[
                EdgeDefinition(source="a", target="b"),
                EdgeDefinition(source="b", target="a"),
            ],
        )
        result = self.validator.validate(wf)
        assert not result.is_valid
        assert any(e.code == "CYCLE_DETECTED" for e in result.errors)

    def test_cycle_with_loop_counter_allowed(self) -> None:
        wf = _make_workflow(
            nodes=[
                NodeDefinition(id="a", type=NodeType.AGENT),
                NodeDefinition(id="counter", type=NodeType.LOOP_COUNTER, max_iterations=3),
            ],
            edges=[
                EdgeDefinition(source="a", target="counter"),
                EdgeDefinition(source="counter", target="a"),
            ],
        )
        result = self.validator.validate(wf)
        assert result.is_valid  # cycles with loop counters are allowed

    def test_missing_subgraph_id(self) -> None:
        wf = _make_workflow(
            nodes=[NodeDefinition(id="sub", type=NodeType.SUBGRAPH)],
        )
        result = self.validator.validate(wf)
        assert not result.is_valid
        assert any(e.code == "MISSING_SUBGRAPH_ID" for e in result.errors)

    def test_missing_python_code(self) -> None:
        wf = _make_workflow(
            nodes=[NodeDefinition(id="py", type=NodeType.PYTHON_RUNNER)],
        )
        result = self.validator.validate(wf)
        assert not result.is_valid
        assert any(e.code == "MISSING_PYTHON_CODE" for e in result.errors)

    def test_no_default_edge_warning(self) -> None:
        wf = _make_workflow(
            nodes=[
                NodeDefinition(id="a", type=NodeType.AGENT),
                NodeDefinition(id="b", type=NodeType.AGENT),
                NodeDefinition(id="c", type=NodeType.AGENT),
            ],
            edges=[
                EdgeDefinition(
                    source="a", target="b",
                    condition=TriggerCondition(keyword="yes"),
                ),
                EdgeDefinition(
                    source="a", target="c",
                    condition=TriggerCondition(keyword="no"),
                ),
            ],
        )
        result = self.validator.validate(wf)
        assert any(w.code == "NO_DEFAULT_EDGE" for w in result.warnings)
