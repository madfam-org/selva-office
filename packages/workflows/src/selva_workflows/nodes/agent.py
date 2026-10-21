"""Agent node handler — invokes an LLM via the inference layer."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..schema import NodeDefinition

logger = logging.getLogger(__name__)


class AgentNodeHandler:
    """Handles execution of an 'agent' node in a compiled workflow.

    Calls the LLM through the inference layer with the node's system prompt,
    tools, and model configuration. Tool calling loops are handled at the
    graph level (Phase 2.2).
    """

    def __init__(self, node: NodeDefinition) -> None:
        self.node = node

    def build_node_fn(self) -> Any:
        """Return a LangGraph-compatible node function."""
        node = self.node

        def agent_node(state: dict) -> dict:
            """Execute an LLM call for this agent node."""
            messages: list = list(state.get("messages", []))
            task_description = state.get("description", "")

            # Build system message from node config
            system_parts: list[str] = []
            if node.system_prompt:
                system_parts.append(node.system_prompt)

            agent_prompt = state.get("agent_system_prompt", "")
            if agent_prompt:
                system_parts.append(agent_prompt)

            if system_parts:
                messages.insert(0, SystemMessage(content="\n\n".join(system_parts)))

            # If no user message exists yet, inject the task description
            has_human = any(isinstance(m, HumanMessage) for m in messages)
            if not has_human and task_description:
                messages.append(HumanMessage(content=task_description))

            # Try LLM call via inference layer.
            #
            # call_llm is async and returns a plain str (the assistant's
            # message content). The previous implementation called it
            # synchronously with the wrong arg shape and accessed a
            # nonexistent ``.content`` attribute — broken since written
            # but masked by the broad except below, which silently fell
            # through to the static fallback on every workflow run.
            try:
                import asyncio

                from selva_workers.inference import call_llm, get_model_router

                router = get_model_router()
                if router is None:
                    raise RuntimeError("No model router available")  # noqa: TRY301

                # Pull out the system message we just inserted at index 0
                # so it can travel via call_llm's ``system_prompt`` kwarg
                # rather than as a regular message (some providers reject
                # in-list system messages on the second turn).
                system_prompt = ""
                user_messages = list(messages)
                if user_messages and isinstance(user_messages[0], SystemMessage):
                    sys_msg = user_messages.pop(0)
                    system_prompt = (
                        sys_msg.content
                        if isinstance(sys_msg.content, str)
                        else str(sys_msg.content)
                    )

                ai_content = asyncio.run(
                    call_llm(
                        router,
                        messages=[
                            {"role": _msg_role(m), "content": m.content}
                            for m in user_messages
                        ],
                        system_prompt=system_prompt,
                        # The node's own model / temperature (schema fields
                        # that used to be ignored) and the task's tenant.
                        model=node.model,
                        temperature=node.temperature,
                        org_id=state.get("org_id") or None,
                        task_id=state.get("task_id") or None,
                        agent_id=state.get("agent_id") or None,
                    )
                )
                if not ai_content:
                    raise RuntimeError("LLM returned an empty response")  # noqa: TRY301

                result_messages = list(state.get("messages", []))
                result_messages.append(AIMessage(content=ai_content))

                return {
                    **state,
                    "messages": result_messages,
                    "status": "running",
                    "current_node_id": node.id,
                }
            except Exception as exc:
                # Fail visible: no placeholder text that reads like output.
                # The node does not raise (so the rest of the workflow and
                # every other graph keep running), but it marks the state as
                # an error and says so explicitly; call_llm has also recorded
                # the failure on the task, which the worker reports as failed.
                logger.error("Agent node '%s' failed: LLM call failed: %s", node.id, exc)
                error = f"Agent node '{node.id}' failed: LLM call failed ({type(exc).__name__})"
                result_messages = list(state.get("messages", []))
                result_messages.append(
                    AIMessage(
                        content=f"[ERROR] {error}",
                        additional_kwargs={"error": True, "node_id": node.id},
                    )
                )
                return {
                    **state,
                    "messages": result_messages,
                    "status": "error",
                    "error": error,
                    "current_node_id": node.id,
                }

        agent_node.__name__ = f"agent_{node.id}"
        return agent_node


def _msg_role(msg: Any) -> str:
    if isinstance(msg, SystemMessage):
        return "system"
    if isinstance(msg, HumanMessage):
        return "user"
    if isinstance(msg, AIMessage):
        return "assistant"
    return "user"
