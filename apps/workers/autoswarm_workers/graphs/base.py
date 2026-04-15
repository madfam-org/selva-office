"""Common LangGraph state, nodes, and utilities shared across all workflow graphs."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from collections.abc import Coroutine
from datetime import UTC
from typing import Any, TypedDict, TypeVar

from langchain_core.messages import BaseMessage

from autoswarm_permissions import (
    DEFAULT_CONTEXT_RULES,
    DEFAULT_PERMISSION_MATRIX,
    ROLE_PERMISSION_MATRICES,
    ActionClassifier,
    PermissionContext,
    PermissionEngine,
    RoleMatrixRule,
)
from autoswarm_permissions.types import ActionCategory, PermissionLevel, PermissionResult

from ..tools.bash_tool import BashTool
from ..tools.git_tool import GitTool

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def run_async(coro: Coroutine[Any, Any, _T]) -> _T:  # noqa: UP047
    """Run an async coroutine from a sync graph node context.

    If no event loop is running, uses ``asyncio.run()``.  Otherwise, offloads
    to a single-threaded ``ThreadPoolExecutor`` so that LangGraph sync nodes
    can await async helpers without blocking the loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# -- Real permission engine and classifier ------------------------------------

_classifier = ActionClassifier()
_role_matrix_rule = RoleMatrixRule(ROLE_PERMISSION_MATRICES)
_default_context_rules = [*DEFAULT_CONTEXT_RULES, _role_matrix_rule]
_engine = PermissionEngine(
    matrix=DEFAULT_PERMISSION_MATRIX,
    context_rules=_default_context_rules,
)


# -- Shared graph state -------------------------------------------------------


class BaseGraphState(TypedDict, total=False):
    """Base state carried through every LangGraph workflow.

    All workflow-specific graphs extend this with additional fields.
    ``total=False`` allows nodes to write only the keys they care about.
    """

    messages: list[BaseMessage]
    task_id: str
    agent_id: str
    status: str
    result: dict[str, Any] | None
    requires_approval: bool
    approval_request_id: str | None
    agent_system_prompt: str
    agent_skill_ids: list[str]
    # Custom workflow fields
    workflow_variables: dict[str, Any]
    current_node_id: str
    description: str
    locale: str


# -- Shared node functions ----------------------------------------------------


def _build_engine_for_state(state: BaseGraphState) -> PermissionEngine:
    """Build a PermissionEngine with skill-based overrides if available."""
    skill_ids = state.get("agent_skill_ids", [])
    if not skill_ids:
        return _engine

    try:
        from autoswarm_skills import get_skill_registry

        registry = get_skill_registry()
        allowed_tool_names = registry.get_allowed_tools(skill_ids)
        overrides: dict[ActionCategory, PermissionLevel] = {}
        for tool_name in allowed_tool_names:
            try:
                cat = ActionCategory(tool_name)
                overrides[cat] = PermissionLevel.ALLOW
            except ValueError:
                pass
        if overrides:
            return PermissionEngine(matrix=DEFAULT_PERMISSION_MATRIX, overrides=overrides)
    except Exception:
        logger.warning("Failed to build skill-based permission overrides", exc_info=True)

    return _engine


def check_permission(
    state: BaseGraphState,
    action_category_str: str,
) -> PermissionResult:
    """Check if an action is permitted for the current agent.

    Returns a ``PermissionResult`` with ``level`` of ALLOW, ASK, or DENY.
    For ASK-level actions, the calling node should use ``interrupt()``
    separately to request human approval.
    """
    from datetime import datetime

    engine = _build_engine_for_state(state)
    try:
        category = ActionCategory(action_category_str)
    except ValueError:
        category = ActionCategory.API_CALL

    perm_context = PermissionContext(
        time_utc=datetime.now(UTC),
        agent_level=state.get("agent_level"),  # type: ignore[arg-type]
        risk_score=state.get("risk_score"),  # type: ignore[arg-type]
        agent_role=state.get("agent_role"),  # type: ignore[arg-type]
    )

    # Resolve playbook guard for bounded autonomous execution (Axiom IV)
    playbook_guard = None
    playbook_data = state.get("playbook")
    if playbook_data and isinstance(playbook_data, dict):
        try:
            from autoswarm_permissions.playbook import (
                PlaybookDefinition,
                PlaybookExecutionState,
                PlaybookGuard,
            )

            playbook_def = PlaybookDefinition(
                id=playbook_data.get("id", ""),
                name=playbook_data.get("name", ""),
                trigger_event=playbook_data.get("trigger_event", ""),
                allowed_actions=set(playbook_data.get("allowed_actions", [])),
                token_budget=playbook_data.get("token_budget", 50),
                financial_cap_cents=playbook_data.get("financial_cap_cents", 0),
                require_approval=playbook_data.get("require_approval", False),
            )
            exec_state = PlaybookExecutionState(playbook=playbook_def)
            playbook_guard = PlaybookGuard(exec_state)
        except Exception:
            pass

    return engine.evaluate(category, context=perm_context, playbook_guard=playbook_guard)


def permission_check(state: BaseGraphState) -> BaseGraphState:
    """Evaluate the pending action against the real PermissionEngine.

    Inspects the last message for tool_calls and classifies each tool
    name via ``ActionClassifier``.  Falls back to extracting the
    ``action_category`` string from ``additional_kwargs`` metadata.

    If any tool call maps to ``ASK`` the node sets
    ``requires_approval=True`` so downstream nodes (or the interrupt
    handler) can pause execution and request human approval.

    If any tool call maps to ``DENY`` the status is set to ``"blocked"``.
    Otherwise (``ALLOW``), execution continues unimpeded.
    """
    messages = state.get("messages", [])
    if not messages:
        return {**state, "requires_approval": False}

    last_message = messages[-1]
    engine = _build_engine_for_state(state)

    # Build permission context from agent metadata.
    from datetime import datetime

    perm_context = PermissionContext(
        time_utc=datetime.now(UTC),
        agent_level=state.get("agent_level"),  # type: ignore[arg-type]
        risk_score=state.get("risk_score"),  # type: ignore[arg-type]
        agent_role=state.get("agent_role"),  # type: ignore[arg-type]
    )

    # -- Classify from tool_calls if present ----------------------------------
    tool_calls = getattr(last_message, "tool_calls", None)
    if tool_calls:
        for call in tool_calls:
            tool_name = call.get("name", "unknown")
            category = _classifier.classify(tool_name)
            result = engine.evaluate(category, context=perm_context)

            if result.level == PermissionLevel.DENY:
                logger.warning(
                    "Action '%s' (tool '%s') denied by permission engine for agent %s",
                    category.value,
                    tool_name,
                    state.get("agent_id", "unknown"),
                )
                return {**state, "status": "blocked", "requires_approval": False}

            if result.requires_approval:
                logger.info(
                    "Action '%s' (tool '%s') requires approval for agent %s: %s",
                    category.value,
                    tool_name,
                    state.get("agent_id", "unknown"),
                    result.reason,
                )
                return {**state, "requires_approval": True}

        # All tool calls are allowed.
        return {**state, "requires_approval": False}

    # -- Fallback: classify from action_category metadata ---------------------
    action_category_str: str = getattr(last_message, "additional_kwargs", {}).get(
        "action_category", "api_call"
    )

    try:
        category = ActionCategory(action_category_str)
    except ValueError:
        logger.warning(
            "Unknown action category '%s'; defaulting to API_CALL",
            action_category_str,
        )
        category = ActionCategory.API_CALL

    result = engine.evaluate(category, context=perm_context)

    if result.level == PermissionLevel.DENY:
        logger.warning(
            "Action '%s' denied by permission engine for agent %s",
            category.value,
            state.get("agent_id", "unknown"),
        )
        return {**state, "status": "blocked", "requires_approval": False}

    if result.requires_approval:
        logger.info(
            "Action '%s' requires approval for agent %s: %s",
            category.value,
            state.get("agent_id", "unknown"),
            result.reason,
        )
        return {**state, "requires_approval": True}

    return {**state, "requires_approval": False}


# -- Tool registry for dispatching real tool calls ----------------------------

_bash_tool = BashTool()
_git_tool = GitTool()

_TOOL_REGISTRY: dict[str, Any] = {
    "bash": _bash_tool,
    "shell": _bash_tool,
    "terminal": _bash_tool,
    "git_push": _git_tool,
    "git_commit": _git_tool,
    "create_worktree": _git_tool,
    "cleanup_worktree": _git_tool,
}


def tool_executor(state: BaseGraphState) -> BaseGraphState:
    """Execute the tool call described in the most recent message.

    Before execution the node runs a permission check.  If approval is
    required and has not been granted, the node short-circuits and
    returns the state with ``status="waiting_approval"``.

    Dispatches to real tool implementations (BashTool, GitTool) via
    the tool registry.  Unrecognised tool names log a warning and
    return a placeholder result.
    """
    # Guard: if approval is still pending, do not execute.
    if state.get("requires_approval") and state.get("status") != "approved":
        logger.info("Tool execution paused pending approval for task %s", state.get("task_id"))
        return {**state, "status": "waiting_approval"}

    messages = state.get("messages", [])
    if not messages:
        return {**state, "status": "error", "result": {"error": "No messages in state"}}

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", None)
    if not tool_calls:
        return {**state, "status": "completed", "result": {"output": last_message.content}}

    # Execute each tool call sequentially.
    results: list[dict[str, Any]] = []

    _run_async = run_async  # alias for local use

    for call in tool_calls:
        tool_name = call.get("name", "unknown")
        tool_args = call.get("args", {})
        logger.info("Executing tool '%s' with args %s", tool_name, tool_args)

        try:
            if tool_name in ("bash", "shell", "terminal"):
                command = tool_args.get("command", "")
                bash_result = _run_async(_bash_tool.execute(command))
                results.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "output": bash_result.stdout,
                        "stderr": bash_result.stderr,
                        "return_code": bash_result.return_code,
                        "success": bash_result.success,
                    }
                )
            elif tool_name == "git_push":
                repo_path = tool_args.get("repo_path", ".")
                branch = tool_args.get("branch", "main")
                push_result = _run_async(_git_tool.push(repo_path, branch))
                results.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "output": push_result.stdout,
                        "stderr": push_result.stderr,
                        "return_code": push_result.return_code,
                        "success": push_result.success,
                    }
                )
            elif tool_name == "git_commit":
                repo_path = tool_args.get("repo_path", ".")
                message = tool_args.get("message", "auto-commit")
                commit_result = _run_async(_git_tool.commit(repo_path, message))
                results.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "output": commit_result.stdout,
                        "stderr": commit_result.stderr,
                        "return_code": commit_result.return_code,
                        "success": commit_result.success,
                    }
                )
            else:
                logger.warning(
                    "No handler registered for tool '%s'; returning placeholder result.",
                    tool_name,
                )
                results.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "output": "",
                        "error": f"No handler registered for tool '{tool_name}'",
                        "success": False,
                    }
                )
        except Exception as exc:
            logger.error("Tool '%s' execution failed: %s", tool_name, exc)
            results.append(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "output": "",
                    "error": str(exc),
                    "success": False,
                }
            )

    return {**state, "status": "completed", "result": {"tool_results": results}}
