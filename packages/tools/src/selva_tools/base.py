"""Base tool interface and result types."""

from __future__ import annotations

import abc
from typing import Any

from pydantic import BaseModel, Field

from .audience import Audience


class ToolResult(BaseModel):
    """Structured result from a tool execution."""

    success: bool = True
    output: str = ""
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class BaseTool(abc.ABC):
    """Abstract base class for all tools in the AutoSwarm tool registry.

    Each tool must define:
    - ``name``: unique identifier used in function-calling specs
    - ``description``: human-readable description for LLM context
    - ``parameters_schema()``: JSON Schema for the tool's parameters
    - ``execute(**kwargs)``: async execution method

    Optional class attribute:
    - ``audience``: ``Audience.PLATFORM`` for MADFAM-only ops (Cloudflare,
      K8s, tenant_identities, Janua admin, etc.) or ``Audience.TENANT``
      for tools a tenant swarm may use (the default). Tools that touch
      cross-tenant or platform-owned infra must be explicitly tagged
      PLATFORM — the registry's spec filter hides them from tenant
      swarms, and ``enforce_audience()`` guards at execute time.
    """

    name: str
    description: str
    audience: Audience = Audience.TENANT

    @abc.abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """Return JSON Schema describing this tool's parameters.

        The schema follows the OpenAI function-calling format:
        ``{"type": "object", "properties": {...}, "required": [...]}``
        """

    @abc.abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given arguments.

        Returns:
            A ToolResult with the output or error.
        """

    def to_openai_spec(self) -> dict[str, Any]:
        """Generate an OpenAI function-calling tool spec."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema(),
            },
        }
