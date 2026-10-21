"""YAML agent node: honours the node's model/temperature, passes the task org,
and fails visibly (no placeholder text that reads like output)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from selva_workflows.nodes.agent import AgentNodeHandler
from selva_workflows.schema import NodeDefinition


@pytest.fixture()
def fake_inference(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {"fail": None}

    async def call_llm(router: Any, **kwargs: Any) -> str:
        captured["kwargs"] = kwargs
        if captured["fail"] is not None:
            raise captured["fail"]
        return "real answer"

    module = types.ModuleType("selva_workers.inference")
    module.call_llm = call_llm  # type: ignore[attr-defined]
    module.get_model_router = lambda: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "selva_workers.inference", module)
    return captured


def _state() -> dict[str, Any]:
    return {
        "messages": [],
        "description": "Summarise the brief",
        "org_id": "madfam",
        "task_id": "t-1",
        "agent_id": "a-1",
    }


def test_node_model_temperature_and_org_are_passed(fake_inference: dict[str, Any]) -> None:
    node = NodeDefinition(
        id="writer", type="agent", model="claude-opus-5-5", temperature=0.2, system_prompt="S"
    )
    out = AgentNodeHandler(node).build_node_fn()(_state())
    kwargs = fake_inference["kwargs"]
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["temperature"] == 0.2
    assert kwargs["org_id"] == "madfam"
    assert kwargs["system_prompt"] == "S"
    assert out["status"] == "running"
    assert out["messages"][-1].content == "real answer"


def test_llm_failure_marks_node_error_without_placeholder(fake_inference: dict[str, Any]) -> None:
    fake_inference["fail"] = RuntimeError("All providers failed")
    node = NodeDefinition(id="writer", type="agent")
    out = AgentNodeHandler(node).build_node_fn()(_state())
    assert out["status"] == "error"
    assert "writer" in out["error"]
    last = out["messages"][-1]
    assert last.content.startswith("[ERROR]")
    assert "static fallback" not in last.content
    assert "LLM unavailable" not in last.content


def test_empty_response_is_a_failure(fake_inference: dict[str, Any]) -> None:
    async def empty(router: Any, **kwargs: Any) -> str:
        return ""

    sys.modules["selva_workers.inference"].call_llm = empty  # type: ignore[attr-defined]
    out = AgentNodeHandler(NodeDefinition(id="n", type="agent")).build_node_fn()(_state())
    assert out["status"] == "error"
