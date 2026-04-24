"""Human node handler — pauses execution for HITL approval via LangGraph interrupt()."""

from __future__ import annotations

import logging
from typing import Any

from ..schema import NodeDefinition

logger = logging.getLogger(__name__)


class HumanNodeHandler:
    """Handles execution of a 'human' node.

    Uses LangGraph's interrupt() to pause graph execution until a human
    provides approval or feedback. The interrupt payload contains the
    node's configured message and current state context.
    """

    def __init__(self, node: NodeDefinition) -> None:
        self.node = node

    def build_node_fn(self) -> Any:
        """Return a LangGraph-compatible node function that calls interrupt()."""
        node = self.node

        def human_node(state: dict) -> dict:
            from langgraph.types import interrupt

            # Build interrupt payload
            payload = {
                "node_id": node.id,
                "message": node.interrupt_message,
                "action_category": "workflow_approval",
                "reasoning": f"Workflow paused at human review node '{node.id}'",
                "task_id": state.get("task_id", ""),
            }

            # This suspends graph execution until resumed
            resume_value = interrupt(payload)

            if isinstance(resume_value, dict):
                approved = resume_value.get("approved", False)
                feedback = resume_value.get("feedback", "")
            else:
                approved = bool(resume_value)
                feedback = ""

            logger.info(
                "Human node '%s' resumed: approved=%s feedback=%s",
                node.id,
                approved,
                feedback,
            )

            new_status = "running" if approved else "rejected"
            workflow_vars = dict(state.get("workflow_variables", {}))
            workflow_vars[f"{node.id}_approved"] = approved
            workflow_vars[f"{node.id}_feedback"] = feedback

            return {
                **state,
                "status": new_status,
                "requires_approval": False,
                "workflow_variables": workflow_vars,
                "current_node_id": node.id,
            }

        human_node.__name__ = f"human_{node.id}"
        return human_node
