"""Loop counter node handler — enables controlled iteration in workflows."""

from __future__ import annotations

from typing import Any

from ..schema import NodeDefinition


class LoopCounterNodeHandler:
    """Handles execution of a 'loop_counter' node.

    Tracks iteration count in workflow_variables. Downstream conditional
    edges can check the counter to decide whether to loop or exit.
    """

    def __init__(self, node: NodeDefinition) -> None:
        self.node = node

    def build_node_fn(self) -> Any:
        node = self.node

        def loop_counter_node(state: dict) -> dict:
            workflow_vars = dict(state.get("workflow_variables", {}))
            counter_key = f"{node.id}_count"
            current = workflow_vars.get(counter_key, 0)
            current += 1
            workflow_vars[counter_key] = current
            workflow_vars[f"{node.id}_done"] = current >= node.max_iterations

            return {
                **state,
                "workflow_variables": workflow_vars,
                "current_node_id": node.id,
            }

        loop_counter_node.__name__ = f"loop_{node.id}"
        return loop_counter_node
