"""
Gap 3: AutoSwarm Plugin Base Class

Defines the AutoSwarmPlugin ABC and HookType enum.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class HookType(str, Enum):
    PRE_PHASE = "pre_phase"
    POST_PHASE = "post_phase"
    ON_SKILL_LOAD = "on_skill_load"
    ON_MEMORY_INSERT = "on_memory_insert"
    ON_GATEWAY_MESSAGE = "on_gateway_message"


class AutoSwarmPlugin(ABC):
    """
    Base class for all AutoSwarm plugins.

    Subclass this and implement:
      - register_tools() → list of tool dicts
      - get_context_addenda(phase) → list of strings to inject into system prompt

    Optionally register hooks by adding entries to self.hooks in setup().
    """

    def __init__(self, manifest: dict[str, Any]) -> None:
        self._manifest = manifest
        self.hooks: dict[HookType, Any] = {}

    @property
    def name(self) -> str:
        return self._manifest.get("name", self.__class__.__name__)

    @property
    def version(self) -> str:
        return self._manifest.get("version", "0.0.1")

    def setup(self) -> None:
        """Called once on plugin load. Register hooks here."""

    def teardown(self) -> None:
        """Called on plugin unload or application shutdown."""

    @abstractmethod
    def register_tools(self) -> list[dict[str, Any]]:
        """Return list of tool definition dicts to add to the tool registry."""
        ...

    def get_context_addenda(self, phase: str) -> list[str]:
        """Return list of context strings to inject into the system prompt for *phase*."""
        return []
