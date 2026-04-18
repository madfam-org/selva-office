"""Passthrough node handler — forwards state unchanged."""

from __future__ import annotations

from typing import Any

from ..schema import NodeDefinition


class PassthroughNodeHandler:
    """Handles execution of a 'passthrough' node. Forwards state unchanged."""

    def __init__(self, node: NodeDefinition) -> None:
        self.node = node

    def build_node_fn(self) -> Any:
        node = self.node

        def passthrough_node(state: dict) -> dict:
            return {**state, "current_node_id": node.id}

        passthrough_node.__name__ = f"passthrough_{node.id}"
        return passthrough_node
