"""Literal node handler — injects a static value into workflow state."""

from __future__ import annotations

from typing import Any

from ..schema import NodeDefinition


class LiteralNodeHandler:
    """Handles execution of a 'literal' node.

    Injects the node's configured static value into workflow_variables.
    """

    def __init__(self, node: NodeDefinition) -> None:
        self.node = node

    def build_node_fn(self) -> Any:
        node = self.node

        def literal_node(state: dict) -> dict:
            workflow_vars = dict(state.get("workflow_variables", {}))
            workflow_vars[node.id] = node.literal_value
            return {
                **state,
                "workflow_variables": workflow_vars,
                "current_node_id": node.id,
            }

        literal_node.__name__ = f"literal_{node.id}"
        return literal_node
