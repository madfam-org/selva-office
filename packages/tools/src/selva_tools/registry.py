"""Tool registry — singleton for discovering, registering, and retrieving tools."""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all available tools.

    Supports manual registration, auto-discovery from built-in modules,
    and generating OpenAI function-calling specs for a subset of tools.
    """

    _instance: ToolRegistry | None = None

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._initialized = False

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Overwrites if name already exists."""
        if tool.name in self._tools:
            logger.debug("Overwriting tool '%s' in registry", tool.name)
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return sorted(self._tools.keys())

    def get_specs(self, tool_names: list[str] | None = None) -> list[dict[str, Any]]:
        """Generate OpenAI function-calling specs for the given tools.

        If tool_names is None, returns specs for all registered tools.
        """
        if tool_names is None:
            tools = self._tools.values()
        else:
            tools = [self._tools[n] for n in tool_names if n in self._tools]
        return [t.to_openai_spec() for t in tools]

    def discover_builtins(self) -> None:
        """Auto-discover and register all built-in tools."""
        if self._initialized:
            return
        self._initialized = True

        from .builtins import get_builtin_tools

        for tool in get_builtin_tools():
            self.register(tool)

        logger.info("Registered %d built-in tools", len(self._tools))


def get_tool_registry() -> ToolRegistry:
    """Get the singleton tool registry, auto-discovering builtins on first call."""
    registry = ToolRegistry.get_instance()
    registry.discover_builtins()
    return registry
