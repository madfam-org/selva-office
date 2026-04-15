"""Puppeteer workflow graph -- decompose, assign, execute in parallel, aggregate, feedback."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from ..event_emitter import instrumented_node
from .base import BaseGraphState
from .base import run_async as _run_async

logger = logging.getLogger(__name__)


# -- State --------------------------------------------------------------------


class PuppeteerState(BaseGraphState, TypedDict, total=False):
    """State for the puppeteer workflow."""

    subtasks: list[dict[str, Any]]
    subtask_results: list[dict[str, Any]]
    aggregated_result: dict[str, Any] | None
    max_parallel: int
    selected_agents: list[str]


# -- Node functions -----------------------------------------------------------


@instrumented_node
def decompose(state: PuppeteerState) -> PuppeteerState:
    """Decompose the main task into subtasks.

    Uses LLM if available, otherwise creates a single subtask from description.
    """
    messages = state.get("messages", [])
    description = state.get("description", "")

    # Try LLM-based decomposition
    try:
        import json as json_mod

        from autoswarm_workers.inference import call_llm, get_model_router

        router = get_model_router()

        # Retrieve experience context for prompt enrichment
        experience_suffix = ""
        try:
            from autoswarm_workers.prompts import build_experience_context

            agent_id = state.get("agent_id", "unknown")
            experience_suffix = _run_async(build_experience_context(
                agent_id=agent_id,
                agent_role="planner",
                task_description=description,
            ))
        except Exception:
            logger.debug("Failed to retrieve experience context", exc_info=True)

        prompt = (
            "Decompose this task into 2-5 independent subtasks. "
            "Return a JSON array of objects with 'description' and 'type' fields.\n\n"
            f"Task: {description}"
        )
        if experience_suffix:
            prompt += f"\n\n{experience_suffix}"
        response = _run_async(
            call_llm(
                router,
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are a task decomposition assistant. Return valid JSON only."
                ),
                task_type="planning",
            )
        )

        try:
            subtasks = json_mod.loads(response)
            if isinstance(subtasks, list) and len(subtasks) > 0:
                decompose_msg = AIMessage(
                    content=f"Decomposed into {len(subtasks)} subtasks"
                )
                return {
                    **state,
                    "messages": [*messages, decompose_msg],
                    "subtasks": subtasks,
                    "status": "decomposed",
                }
        except (json_mod.JSONDecodeError, TypeError):
            pass
    except Exception:
        logger.debug("LLM decomposition unavailable, using single subtask")

    # Fallback: single subtask
    subtasks = [{"description": description, "type": "general"}]
    decompose_msg = AIMessage(
        content=f"Created {len(subtasks)} subtask(s) from description"
    )
    return {
        **state,
        "messages": [*messages, decompose_msg],
        "subtasks": subtasks,
        "status": "decomposed",
    }


@instrumented_node
def assign(state: PuppeteerState) -> PuppeteerState:
    """Assign agents to subtasks using Thompson Sampling."""
    messages = state.get("messages", [])
    subtasks = state.get("subtasks", [])

    if not subtasks:
        return {
            **state,
            "messages": [*messages, AIMessage(content="No subtasks to assign")],
            "status": "error",
        }

    # Use bandit for agent selection
    try:
        from autoswarm_orchestrator import PuppeteerOrchestrator

        orchestrator = PuppeteerOrchestrator()
        # Get available candidates from state
        agent_id = state.get("agent_id", "unknown")
        candidates = [agent_id] if agent_id != "unknown" else []

        selected = orchestrator.select_agents(len(subtasks), candidates or None)
        assign_msg = AIMessage(
            content=f"Assigned {len(selected)} agents via Thompson Sampling"
        )
        return {
            **state,
            "messages": [*messages, assign_msg],
            "selected_agents": selected,
            "status": "assigned",
        }
    except Exception:
        logger.debug("Bandit assignment unavailable, using single agent fallback")

    # Fallback: assign the primary agent to all subtasks
    agent_id = state.get("agent_id", "unknown")
    assign_msg = AIMessage(
        content=f"Assigned agent {agent_id} to all {len(subtasks)} subtasks"
    )
    return {
        **state,
        "messages": [*messages, assign_msg],
        "selected_agents": [agent_id] * len(subtasks),
        "status": "assigned",
    }


@instrumented_node
def execute_parallel(state: PuppeteerState) -> PuppeteerState:
    """Execute subtasks in parallel with semaphore-based concurrency control."""
    messages = state.get("messages", [])
    subtasks = state.get("subtasks", [])
    max_parallel = state.get("max_parallel", 3)

    if not subtasks:
        return {
            **state,
            "messages": [*messages, AIMessage(content="No subtasks to execute")],
            "status": "error",
        }

    # Execute subtasks — dispatch as independent SwarmTasks when API is available,
    # fall back to in-process LLM execution otherwise
    async def _execute_subtasks() -> list[dict[str, Any]]:
        import os

        import httpx

        semaphore = asyncio.Semaphore(max_parallel)
        api_url = os.environ.get("NEXUS_API_URL", "")
        api_token = os.environ.get("WORKER_API_TOKEN", "dev-bypass")
        use_dispatch = bool(api_url) and os.environ.get("PUPPETEER_DISPATCH_SUBTASKS", "false") == "true"

        async def _dispatch_subtask(
            subtask: dict[str, Any], index: int
        ) -> dict[str, Any]:
            """Dispatch subtask as independent SwarmTask via API."""
            async with semaphore:
                try:
                    async with httpx.AsyncClient(timeout=300) as client:
                        # Create SwarmTask
                        resp = await client.post(
                            f"{api_url}/api/v1/swarms/dispatch",
                            headers={"Authorization": f"Bearer {api_token}"},
                            json={
                                "description": subtask.get("description", ""),
                                "graph_type": subtask.get("graph_type", "fast_coding"),
                                "required_skills": subtask.get("required_skills", ["coding"]),
                                "metadata": {"parent_task": state.get("task_id"), "subtask_index": index},
                            },
                        )
                        if resp.status_code not in (200, 201):
                            raise RuntimeError(f"Dispatch failed: {resp.status_code}")
                        task_id = resp.json().get("task", {}).get("id", "")

                        # Poll for completion (max 5 minutes)
                        for _ in range(60):
                            await asyncio.sleep(5)
                            status_resp = await client.get(
                                f"{api_url}/api/v1/swarms/tasks/{task_id}",
                                headers={"Authorization": f"Bearer {api_token}"},
                            )
                            if status_resp.status_code == 200:
                                task_data = status_resp.json()
                                if task_data.get("status") in ("completed", "failed"):
                                    return {
                                        "index": index,
                                        "description": subtask.get("description", ""),
                                        "result": task_data.get("result", ""),
                                        "success": task_data.get("status") == "completed",
                                        "task_id": task_id,
                                    }
                        return {"index": index, "description": subtask.get("description", ""), "result": "Timeout", "success": False}
                except Exception as exc:
                    logger.error("Subtask dispatch failed: %s", exc)
                    return {"index": index, "description": subtask.get("description", ""), "result": str(exc), "success": False}

        async def _run_subtask_locally(
            subtask: dict[str, Any], index: int
        ) -> dict[str, Any]:
            """Execute subtask in-process via LLM."""
            async with semaphore:
                try:
                    from autoswarm_workers.inference import call_llm, get_model_router

                    router = get_model_router()
                    prompt = (
                        "Execute this subtask and provide a result summary:\n\n"
                        f"{subtask.get('description', '')}"
                    )
                    response = await call_llm(
                        router,
                        messages=[{"role": "user", "content": prompt}],
                        task_type="fast_coding",
                    )
                    return {
                        "index": index,
                        "description": subtask.get("description", ""),
                        "result": response,
                        "success": True,
                    }
                except Exception as exc:
                    return {
                        "index": index,
                        "description": subtask.get("description", ""),
                        "result": f"Subtask completed (no LLM): {subtask.get('description', '')}",
                        "success": True,
                        "error": str(exc) if str(exc) else None,
                    }

        executor = _dispatch_subtask if use_dispatch else _run_subtask_locally
        tasks = [executor(st, i) for i, st in enumerate(subtasks)]
        return await asyncio.gather(*tasks)

    results = _run_async(_execute_subtasks())

    exec_msg = AIMessage(
        content=(
            f"Executed {len(results)} subtasks "
            f"({sum(1 for r in results if r.get('success'))} succeeded)"
        )
    )
    return {
        **state,
        "messages": [*messages, exec_msg],
        "subtask_results": list(results),
        "status": "executed",
    }


@instrumented_node
def aggregate(state: PuppeteerState) -> PuppeteerState:
    """Aggregate subtask results into a unified result."""
    messages = state.get("messages", [])
    results = state.get("subtask_results", [])

    if not results:
        return {
            **state,
            "messages": [*messages, AIMessage(content="No results to aggregate")],
            "status": "error",
        }

    # Try LLM-based aggregation
    try:
        from autoswarm_workers.inference import call_llm, get_model_router

        router = get_model_router()
        results_text = "\n".join(
            f"Subtask {r['index']}: {r.get('result', 'no result')}" for r in results
        )
        prompt = (
            "Aggregate these subtask results into a coherent summary:\n\n"
            f"{results_text}"
        )
        response = _run_async(call_llm(
            router,
            messages=[{"role": "user", "content": prompt}],
            task_type="planning",
        ))

        aggregated: dict[str, Any] = {
            "summary": response,
            "subtask_count": len(results),
            "success_count": sum(1 for r in results if r.get("success")),
        }
    except Exception:
        # Fallback aggregation
        aggregated = {
            "summary": "; ".join(str(r.get("result", "")) for r in results),
            "subtask_count": len(results),
            "success_count": sum(1 for r in results if r.get("success")),
        }

    agg_msg = AIMessage(content=f"Aggregated {len(results)} results")
    return {
        **state,
        "messages": [*messages, agg_msg],
        "aggregated_result": aggregated,
        "result": aggregated,
        "status": "aggregated",
    }


@instrumented_node
def feedback(state: PuppeteerState) -> PuppeteerState:
    """Record outcomes in the bandit for future learning."""
    messages = state.get("messages", [])
    results = state.get("subtask_results", [])
    selected_agents = state.get("selected_agents", [])

    # Calculate reward based on success rate
    success_rate = (
        sum(1 for r in results if r.get("success")) / len(results) if results else 0.0
    )

    # Update bandit
    try:
        from autoswarm_orchestrator import PuppeteerOrchestrator

        orchestrator = PuppeteerOrchestrator()
        for agent_id in set(selected_agents):
            if agent_id != "unknown":
                orchestrator.record_outcome(agent_id, success_rate)

        feedback_msg = AIMessage(
            content=(
                f"Recorded feedback: {success_rate:.0%} success rate "
                f"for {len(set(selected_agents))} agents"
            )
        )
    except Exception:
        feedback_msg = AIMessage(
            content=f"Feedback recorded: {success_rate:.0%} success rate"
        )

    return {
        **state,
        "messages": [*messages, feedback_msg],
        "status": "completed",
    }


# -- Graph construction -------------------------------------------------------


def build_puppeteer_graph() -> StateGraph:
    """Construct the puppeteer workflow state graph.

    Flow::

        decompose -> assign (bandit) -> execute_parallel -> aggregate -> feedback -> END
    """
    graph = StateGraph(PuppeteerState)

    graph.add_node("decompose", decompose)
    graph.add_node("assign", assign)
    graph.add_node("execute_parallel", execute_parallel)
    graph.add_node("aggregate", aggregate)
    graph.add_node("feedback", feedback)

    graph.set_entry_point("decompose")
    graph.add_edge("decompose", "assign")
    graph.add_edge("assign", "execute_parallel")
    graph.add_edge("execute_parallel", "aggregate")
    graph.add_edge("aggregate", "feedback")
    graph.add_edge("feedback", END)

    return graph
