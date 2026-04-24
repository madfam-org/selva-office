"""Puppeteer orchestrator -- uses Thompson Sampling for intelligent agent selection."""

from __future__ import annotations

from .bandit import ThompsonBandit
from .orchestrator import SwarmOrchestrator
from .types import AgentStatus


class PuppeteerOrchestrator(SwarmOrchestrator):
    """Extended orchestrator that uses bandit-based agent selection.

    Instead of manual agent assignment, the puppeteer selects agents
    using Thompson Sampling based on historical performance.
    """

    def __init__(
        self,
        bandit: ThompsonBandit | None = None,
        persist_path: str | None = None,
        **kwargs,  # noqa: ANN003
    ) -> None:
        super().__init__(**kwargs)
        self.bandit = bandit or ThompsonBandit(persist_path=persist_path)

    def select_agent(self, candidates: list[str] | None = None) -> str:
        """Select the best agent using Thompson Sampling.

        If candidates is None, uses all idle agents.
        """
        if candidates is None:
            candidates = [
                aid for aid, agent in self.agents.items() if agent.status == AgentStatus.IDLE
            ]
        return self.bandit.select(candidates)

    def select_agents(self, count: int, candidates: list[str] | None = None) -> list[str]:
        """Select multiple agents without replacement."""
        if candidates is None:
            candidates = [
                aid for aid, agent in self.agents.items() if agent.status == AgentStatus.IDLE
            ]

        selected: list[str] = []
        remaining = list(candidates)
        for _ in range(min(count, len(remaining))):
            if not remaining:
                break
            choice = self.bandit.select(remaining)
            selected.append(choice)
            remaining.remove(choice)
        return selected

    def record_outcome(self, agent_id: str, reward: float) -> None:
        """Record a task outcome for learning."""
        self.bandit.update(agent_id, reward)
