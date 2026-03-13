"""Workflow definition validation: cycle detection, orphan checks, type compatibility."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .schema import EdgeDefinition, NodeDefinition, NodeType, WorkflowDefinition


@dataclass
class ValidationError:
    """A single validation issue found in a workflow definition."""

    code: str
    message: str
    node_id: str | None = None
    edge_index: int | None = None


@dataclass
class ValidationResult:
    """Aggregate result of workflow validation."""

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


class WorkflowValidator:
    """Validates a WorkflowDefinition for structural correctness."""

    def validate(self, workflow: WorkflowDefinition) -> ValidationResult:
        result = ValidationResult()

        node_map = {n.id: n for n in workflow.nodes}

        self._check_unique_ids(workflow.nodes, result)
        self._check_entry_node(workflow, node_map, result)
        self._check_edge_references(workflow.edges, node_map, result)
        self._check_orphan_nodes(workflow, node_map, result)
        self._check_cycles(workflow, result)
        self._check_node_type_config(workflow.nodes, result)
        self._check_conditional_edges(workflow.edges, node_map, result)

        return result

    def _check_unique_ids(
        self, nodes: list[NodeDefinition], result: ValidationResult
    ) -> None:
        seen: set[str] = set()
        for node in nodes:
            if node.id in seen:
                result.errors.append(
                    ValidationError(
                        code="DUPLICATE_NODE_ID",
                        message=f"Duplicate node ID: '{node.id}'",
                        node_id=node.id,
                    )
                )
            seen.add(node.id)

    def _check_entry_node(
        self,
        workflow: WorkflowDefinition,
        node_map: dict[str, NodeDefinition],
        result: ValidationResult,
    ) -> None:
        if workflow.entry_node and workflow.entry_node not in node_map:
            result.errors.append(
                ValidationError(
                    code="INVALID_ENTRY_NODE",
                    message=f"Entry node '{workflow.entry_node}' not found in nodes",
                )
            )

    def _check_edge_references(
        self,
        edges: list[EdgeDefinition],
        node_map: dict[str, NodeDefinition],
        result: ValidationResult,
    ) -> None:
        for i, edge in enumerate(edges):
            if edge.source not in node_map:
                result.errors.append(
                    ValidationError(
                        code="INVALID_EDGE_SOURCE",
                        message=f"Edge source '{edge.source}' not found in nodes",
                        edge_index=i,
                    )
                )
            if edge.target not in node_map:
                result.errors.append(
                    ValidationError(
                        code="INVALID_EDGE_TARGET",
                        message=f"Edge target '{edge.target}' not found in nodes",
                        edge_index=i,
                    )
                )

    def _check_orphan_nodes(
        self,
        workflow: WorkflowDefinition,
        node_map: dict[str, NodeDefinition],
        result: ValidationResult,
    ) -> None:
        if len(workflow.nodes) <= 1:
            return

        # Build sets of nodes that are referenced by edges
        referenced: set[str] = set()
        for edge in workflow.edges:
            referenced.add(edge.source)
            referenced.add(edge.target)

        entry = workflow.entry_node or workflow.nodes[0].id

        for node in workflow.nodes:
            if node.id != entry and node.id not in referenced:
                result.warnings.append(
                    ValidationError(
                        code="ORPHAN_NODE",
                        message=f"Node '{node.id}' is not connected to any edges",
                        node_id=node.id,
                    )
                )

    def _check_cycles(
        self, workflow: WorkflowDefinition, result: ValidationResult
    ) -> None:
        """Detect cycles using DFS. Loop counter nodes are allowed to form cycles."""
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in workflow.edges:
            adjacency[edge.source].append(edge.target)

        # Build set of loop counter node IDs (cycles involving these are allowed)
        loop_nodes = {n.id for n in workflow.nodes if n.type == NodeType.LOOP_COUNTER}

        white, gray, black = 0, 1, 2
        color: dict[str, int] = {n.id: white for n in workflow.nodes}

        def dfs(node_id: str, path: list[str]) -> None:
            color[node_id] = gray
            path.append(node_id)
            for neighbor in adjacency.get(node_id, []):
                if neighbor not in color:
                    continue  # Invalid edge target; caught by _check_edge_references
                if color[neighbor] == gray:
                    # Found a cycle — check if it involves a loop counter
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:]
                    if not any(n in loop_nodes for n in cycle):
                        result.errors.append(
                            ValidationError(
                                code="CYCLE_DETECTED",
                                message=f"Cycle detected: {' -> '.join(cycle)} -> {neighbor}",
                            )
                        )
                elif color[neighbor] == white:
                    dfs(neighbor, path)
            path.pop()
            color[node_id] = black

        for node in workflow.nodes:
            if color[node.id] == white:
                dfs(node.id, [])

    def _check_node_type_config(
        self, nodes: list[NodeDefinition], result: ValidationResult
    ) -> None:
        for node in nodes:
            if node.type == NodeType.SUBGRAPH and not node.subgraph_id:
                result.errors.append(
                    ValidationError(
                        code="MISSING_SUBGRAPH_ID",
                        message=f"Subgraph node '{node.id}' must specify subgraph_id",
                        node_id=node.id,
                    )
                )
            if node.type == NodeType.PYTHON_RUNNER and not node.code:
                result.errors.append(
                    ValidationError(
                        code="MISSING_PYTHON_CODE",
                        message=f"Python runner node '{node.id}' must specify code",
                        node_id=node.id,
                    )
                )

    def _check_conditional_edges(
        self,
        edges: list[EdgeDefinition],
        node_map: dict[str, NodeDefinition],
        result: ValidationResult,
    ) -> None:
        """Warn if a node has multiple conditional outgoing edges but no default."""
        source_edges: dict[str, list[EdgeDefinition]] = defaultdict(list)
        for edge in edges:
            source_edges[edge.source].append(edge)

        for source, out_edges in source_edges.items():
            if source not in node_map:
                continue
            conditional = [e for e in out_edges if e.condition is not None]
            unconditional = [e for e in out_edges if e.condition is None]
            if conditional and not unconditional:
                result.warnings.append(
                    ValidationError(
                        code="NO_DEFAULT_EDGE",
                        message=(
                            f"Node '{source}' has {len(conditional)} conditional edge(s) "
                            f"but no default (unconditional) edge"
                        ),
                        node_id=source,
                    )
                )
