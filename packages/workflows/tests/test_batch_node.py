"""Tests for the batch processing node handler."""

from __future__ import annotations

import asyncio

import pytest

from selva_workflows.nodes.batch import BatchNodeHandler, _aggregate
from selva_workflows.schema import (
    BatchAggregateStrategy,
    EdgeDefinition,
    NodeDefinition,
    NodeType,
    WorkflowDefinition,
)
from selva_workflows.validator import WorkflowValidator


def _make_batch_node(**overrides) -> NodeDefinition:  # type: ignore[no-untyped-def]
    defaults = {
        "id": "batch_1",
        "type": NodeType.BATCH,
        "batch_split_key": "items",
        "delegate_node_id": "worker",
        "max_parallel": 3,
        "batch_aggregate_strategy": BatchAggregateStrategy.COLLECT,
    }
    defaults.update(overrides)
    return NodeDefinition(**defaults)


def _echo_delegate(state: dict) -> dict:
    """Simple delegate that returns the batch item doubled."""
    item = state.get("batch_item", "")
    return {**state, "result": f"processed-{item}"}


# ---------------------------------------------------------------------------
# Unit tests: BatchNodeHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_batch_splits_and_collects() -> None:
    node = _make_batch_node()
    handler = BatchNodeHandler(node, delegate_fn=_echo_delegate)
    fn = handler.build_node_fn()

    state = {"items": ["a", "b", "c"]}
    result = await fn(state)

    assert result["batch_total"] == 3
    assert result["batch_succeeded"] == 3
    assert result["batch_failed"] == 0
    assert len(result["batch_results"]) == 3
    assert result["current_node_id"] == "batch_1"


@pytest.mark.asyncio()
async def test_batch_missing_split_key() -> None:
    node = _make_batch_node()
    handler = BatchNodeHandler(node, delegate_fn=_echo_delegate)
    fn = handler.build_node_fn()

    state = {"other_key": [1, 2]}
    result = await fn(state)
    assert "batch_results" not in result


@pytest.mark.asyncio()
async def test_batch_non_list_split_key() -> None:
    node = _make_batch_node()
    handler = BatchNodeHandler(node, delegate_fn=_echo_delegate)
    fn = handler.build_node_fn()

    state = {"items": "not-a-list"}
    result = await fn(state)
    assert "batch_results" not in result


@pytest.mark.asyncio()
async def test_batch_no_delegate() -> None:
    node = _make_batch_node()
    handler = BatchNodeHandler(node, delegate_fn=None)
    fn = handler.build_node_fn()

    state = {"items": [1, 2, 3]}
    result = await fn(state)
    assert result["batch_results"] == [1, 2, 3]


@pytest.mark.asyncio()
async def test_batch_handles_delegate_errors() -> None:
    def failing_delegate(state: dict) -> dict:
        if state.get("batch_item") == "bad":
            raise ValueError("bad item")
        return {**state, "result": "ok"}

    node = _make_batch_node()
    handler = BatchNodeHandler(node, delegate_fn=failing_delegate)
    fn = handler.build_node_fn()

    state = {"items": ["good", "bad", "good"]}
    result = await fn(state)

    assert result["batch_succeeded"] == 2
    assert result["batch_failed"] == 1
    assert len(result["batch_errors"]) == 1


@pytest.mark.asyncio()
async def test_batch_respects_max_parallel() -> None:
    max_concurrent = 0
    current = 0
    lock = asyncio.Lock()

    async def slow_delegate(state: dict) -> dict:
        nonlocal max_concurrent, current
        async with lock:
            current += 1
            max_concurrent = max(max_concurrent, current)
        await asyncio.sleep(0.01)
        async with lock:
            current -= 1
        return {**state, "result": "done"}

    node = _make_batch_node(max_parallel=2)
    handler = BatchNodeHandler(node, delegate_fn=slow_delegate)
    fn = handler.build_node_fn()

    state = {"items": list(range(6))}
    await fn(state)

    assert max_concurrent <= 2


# ---------------------------------------------------------------------------
# Unit tests: aggregation strategies
# ---------------------------------------------------------------------------


def test_collect_strategy() -> None:
    results = [{"a": 1}, {"b": 2}]
    assert _aggregate(results, BatchAggregateStrategy.COLLECT) == results


def test_merge_strategy() -> None:
    results = [{"a": 1}, {"b": 2}, {"a": 3}]
    merged = _aggregate(results, BatchAggregateStrategy.MERGE)
    assert merged == {"a": 3, "b": 2}


def test_vote_strategy() -> None:
    results = [
        {"result": "approve"},
        {"result": "approve"},
        {"result": "deny"},
    ]
    voted = _aggregate(results, BatchAggregateStrategy.VOTE)
    assert voted["result"] == "approve"
    assert voted["votes"]["approve"] == 2


def test_vote_empty_results() -> None:
    result = _aggregate([], BatchAggregateStrategy.VOTE)
    assert result == []


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


def test_validator_requires_batch_split_key() -> None:
    wf = WorkflowDefinition(
        name="test",
        nodes=[
            NodeDefinition(id="b", type=NodeType.BATCH, delegate_node_id="p"),
            NodeDefinition(id="p", type=NodeType.PASSTHROUGH),
        ],
        edges=[EdgeDefinition(source="b", target="p")],
    )
    result = WorkflowValidator().validate(wf)
    codes = [e.code for e in result.errors]
    assert "MISSING_BATCH_SPLIT_KEY" in codes


def test_validator_requires_batch_delegate() -> None:
    wf = WorkflowDefinition(
        name="test",
        nodes=[
            NodeDefinition(id="b", type=NodeType.BATCH, batch_split_key="items"),
            NodeDefinition(id="p", type=NodeType.PASSTHROUGH),
        ],
        edges=[EdgeDefinition(source="b", target="p")],
    )
    result = WorkflowValidator().validate(wf)
    codes = [e.code for e in result.errors]
    assert "MISSING_BATCH_DELEGATE" in codes


def test_validator_checks_delegate_exists() -> None:
    wf = WorkflowDefinition(
        name="test",
        nodes=[
            NodeDefinition(
                id="b",
                type=NodeType.BATCH,
                batch_split_key="items",
                delegate_node_id="nonexistent",
            ),
        ],
    )
    result = WorkflowValidator().validate(wf)
    codes = [e.code for e in result.errors]
    assert "INVALID_BATCH_DELEGATE" in codes


def test_validator_valid_batch_passes() -> None:
    wf = WorkflowDefinition(
        name="test",
        nodes=[
            NodeDefinition(
                id="b",
                type=NodeType.BATCH,
                batch_split_key="items",
                delegate_node_id="worker",
            ),
            NodeDefinition(id="worker", type=NodeType.PASSTHROUGH),
        ],
        edges=[EdgeDefinition(source="b", target="worker")],
    )
    result = WorkflowValidator().validate(wf)
    assert result.is_valid
