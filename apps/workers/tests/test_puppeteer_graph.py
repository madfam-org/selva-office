"""Tests for the puppeteer workflow graph (Phase 4.3)."""

from __future__ import annotations

from langchain_core.messages import AIMessage


class TestPuppeteerGraphStructure:
    """Puppeteer graph has correct nodes and edges."""

    def test_build_puppeteer_graph(self) -> None:
        from selva_workers.graphs.puppeteer import build_puppeteer_graph

        graph = build_puppeteer_graph()
        node_names = set(graph.nodes.keys())
        assert "decompose" in node_names
        assert "assign" in node_names
        assert "execute_parallel" in node_names
        assert "aggregate" in node_names
        assert "feedback" in node_names

    def test_graph_compiles(self) -> None:
        from selva_workers.graphs.puppeteer import build_puppeteer_graph

        graph = build_puppeteer_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_puppeteer_state_fields(self) -> None:
        from selva_workers.graphs.puppeteer import PuppeteerState

        annotations = PuppeteerState.__annotations__
        assert "subtasks" in annotations
        assert "subtask_results" in annotations
        assert "aggregated_result" in annotations
        assert "max_parallel" in annotations
        assert "selected_agents" in annotations


class TestDecomposeNode:
    """decompose() splits task into subtasks."""

    def test_decompose_node_fallback(self) -> None:
        from selva_workers.graphs.puppeteer import decompose

        result = decompose({
            "messages": [],
            "description": "Build a landing page",
        })

        assert result["status"] == "decomposed"
        assert len(result["subtasks"]) == 1
        assert result["subtasks"][0]["description"] == "Build a landing page"
        assert result["subtasks"][0]["type"] == "general"

    def test_decompose_adds_message(self) -> None:
        from selva_workers.graphs.puppeteer import decompose

        result = decompose({
            "messages": [],
            "description": "Test task",
        })

        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)


class TestAssignNode:
    """assign() selects agents via Thompson Sampling."""

    def test_assign_node_fallback(self) -> None:
        from selva_workers.graphs.puppeteer import assign

        result = assign({
            "messages": [],
            "subtasks": [{"description": "task1", "type": "general"}],
            "agent_id": "agent-123",
        })

        assert result["status"] == "assigned"
        assert "agent-123" in result["selected_agents"]

    def test_assign_no_subtasks_returns_error(self) -> None:
        from selva_workers.graphs.puppeteer import assign

        result = assign({
            "messages": [],
            "subtasks": [],
        })

        assert result["status"] == "error"


class TestExecuteParallelNode:
    """execute_parallel() runs subtasks concurrently."""

    def test_execute_parallel_node(self) -> None:
        from selva_workers.graphs.puppeteer import execute_parallel

        result = execute_parallel({
            "messages": [],
            "subtasks": [
                {"description": "subtask 1", "type": "general"},
                {"description": "subtask 2", "type": "general"},
            ],
            "max_parallel": 3,
        })

        assert result["status"] == "executed"
        assert len(result["subtask_results"]) == 2
        assert all(r["success"] for r in result["subtask_results"])

    def test_execute_no_subtasks_returns_error(self) -> None:
        from selva_workers.graphs.puppeteer import execute_parallel

        result = execute_parallel({
            "messages": [],
            "subtasks": [],
            "max_parallel": 3,
        })

        assert result["status"] == "error"


class TestAggregateNode:
    """aggregate() combines subtask results."""

    def test_aggregate_node(self) -> None:
        from selva_workers.graphs.puppeteer import aggregate

        result = aggregate({
            "messages": [],
            "subtask_results": [
                {"index": 0, "result": "Result A", "success": True},
                {"index": 1, "result": "Result B", "success": True},
            ],
        })

        assert result["status"] == "aggregated"
        assert result["aggregated_result"] is not None
        assert result["aggregated_result"]["subtask_count"] == 2
        assert result["aggregated_result"]["success_count"] == 2

    def test_aggregate_no_results_returns_error(self) -> None:
        from selva_workers.graphs.puppeteer import aggregate

        result = aggregate({
            "messages": [],
            "subtask_results": [],
        })

        assert result["status"] == "error"


class TestFeedbackNode:
    """feedback() records outcomes for learning."""

    def test_feedback_node(self) -> None:
        from selva_workers.graphs.puppeteer import feedback

        result = feedback({
            "messages": [],
            "subtask_results": [
                {"index": 0, "success": True},
                {"index": 1, "success": False},
            ],
            "selected_agents": ["agent-1"],
        })

        assert result["status"] == "completed"
        assert len(result["messages"]) == 1

    def test_feedback_no_results(self) -> None:
        from selva_workers.graphs.puppeteer import feedback

        result = feedback({
            "messages": [],
            "subtask_results": [],
            "selected_agents": [],
        })

        assert result["status"] == "completed"


class TestPuppeteerRegistration:
    """Puppeteer graph is registered and configured."""

    def test_puppeteer_timeout_configured(self) -> None:
        from selva_redis_pool.timeout import DEFAULT_TIMEOUTS

        assert "puppeteer" in DEFAULT_TIMEOUTS
        assert DEFAULT_TIMEOUTS["puppeteer"] == 600
