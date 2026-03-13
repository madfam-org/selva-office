"""Pydantic models for workflow definitions, serializable to/from YAML."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    """Supported workflow node types."""

    AGENT = "agent"
    HUMAN = "human"
    PASSTHROUGH = "passthrough"
    SUBGRAPH = "subgraph"
    PYTHON_RUNNER = "python_runner"
    LITERAL = "literal"
    LOOP_COUNTER = "loop_counter"


class ContextWindowPolicy(StrEnum):
    """Per-node message retention policy applied before each node executes."""

    KEEP_ALL = "keep_all"
    KEEP_LAST_N = "keep_last_n"
    CLEAR_ALL = "clear_all"
    SLIDING_WINDOW = "sliding_window"


class ThinkingStage(StrEnum):
    """Optional reflection stages around LLM calls (Phase 3.2)."""

    PRE_GEN = "pre_gen"
    POST_GEN = "post_gen"


class ContextPolicyConfig(BaseModel):
    """Configuration for a node's context window policy."""

    type: ContextWindowPolicy = ContextWindowPolicy.KEEP_ALL
    n: int = Field(default=10, ge=1, description="Number of messages to keep (for keep_last_n)")


class NodeDefinition(BaseModel):
    """A single node in a workflow DAG."""

    id: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    type: NodeType
    label: str = Field(default="", max_length=200)

    # Agent node config
    model: str | None = Field(default=None, description="Model override for this node")
    system_prompt: str | None = Field(default=None, description="System prompt for agent nodes")
    tools: list[str] = Field(default_factory=list, description="Tool names available to this node")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    # Human node config
    interrupt_message: str = Field(
        default="Awaiting human approval",
        description="Message displayed when execution pauses at a human node",
    )

    # Subgraph node config
    subgraph_id: str | None = Field(
        default=None, description="Reference to another workflow definition"
    )

    # Python runner config
    code: str | None = Field(default=None, description="Python code to execute")

    # Literal node config
    literal_value: Any = Field(default=None, description="Static value to inject into state")

    # Loop counter config
    max_iterations: int = Field(default=5, ge=1, le=100)

    # Context policy
    context_policy: ContextPolicyConfig = Field(default_factory=ContextPolicyConfig)

    # Thinking stages (Phase 3.2 extension point)
    thinking_stages: list[ThinkingStage] = Field(default_factory=list)

    # Position in visual editor (for UI persistence, not used by compiler)
    position_x: float = 0.0
    position_y: float = 0.0


class TriggerCondition(BaseModel):
    """Condition for conditional edge routing.

    Exactly one of regex, keyword, or expression should be set.
    """

    regex: str | None = Field(default=None, description="Regex pattern to match against output")
    keyword: str | None = Field(default=None, description="Keyword to search for in output")
    expression: str | None = Field(
        default=None,
        description="Python expression evaluated against state (e.g. 'state[\"score\"] > 0.8')",
    )


class EdgeDefinition(BaseModel):
    """A directed edge connecting two nodes in the workflow DAG."""

    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    label: str = Field(default="", max_length=200)

    # Conditional routing
    condition: TriggerCondition | None = Field(
        default=None,
        description="If set, this edge is only traversed when the condition matches",
    )

    # Data flow
    carry_data: bool = Field(default=True, description="Whether to pass state along this edge")
    transform: str | None = Field(
        default=None,
        description="Python expression to transform state before passing",
    )


class WorkflowDefinition(BaseModel):
    """Complete workflow definition — the top-level serializable unit."""

    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(default="")

    nodes: list[NodeDefinition] = Field(..., min_length=1)
    edges: list[EdgeDefinition] = Field(default_factory=list)

    # Global workflow variables accessible to all nodes
    variables: dict[str, Any] = Field(default_factory=dict)

    # Entry point — if not set, the first node is used
    entry_node: str | None = Field(default=None)
