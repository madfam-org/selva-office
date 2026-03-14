"""Tests for PuppeteerOrchestrator bandit-based agent selection."""

from __future__ import annotations

import uuid

import pytest

from autoswarm_orchestrator.bandit import ThompsonBandit
from autoswarm_orchestrator.orchestrator import SwarmOrchestrator
from autoswarm_orchestrator.puppeteer import PuppeteerOrchestrator
from autoswarm_orchestrator.types import AgentConfig, AgentRole, AgentStatus


def _agent(
    name: str,
    role: AgentRole = AgentRole.CODER,
    status: AgentStatus = AgentStatus.IDLE,
) -> AgentConfig:
    return AgentConfig(
        id=str(uuid.uuid4()),
        name=name,
        role=role,
        status=status,
    )


class TestPuppeteerOrchestrator:
    """PuppeteerOrchestrator extends SwarmOrchestrator with bandit selection."""

    def test_puppeteer_inherits_orchestrator(self) -> None:
        orch = PuppeteerOrchestrator()
        assert isinstance(orch, SwarmOrchestrator)
        assert isinstance(orch.bandit, ThompsonBandit)

    def test_select_agent_from_idle(self) -> None:
        a1 = _agent("Ada")
        a2 = _agent("Bob", status=AgentStatus.WORKING)
        orch = PuppeteerOrchestrator()
        orch.agents[a1.id] = a1
        orch.agents[a2.id] = a2

        # Only Ada is idle, so she must be selected
        selected = orch.select_agent()
        assert selected == a1.id

    def test_select_agent_no_idle_raises(self) -> None:
        a1 = _agent("Ada", status=AgentStatus.WORKING)
        orch = PuppeteerOrchestrator()
        orch.agents[a1.id] = a1

        with pytest.raises(ValueError, match="No candidates"):
            orch.select_agent()

    def test_select_with_explicit_candidates(self) -> None:
        orch = PuppeteerOrchestrator()
        candidates = ["agent-x", "agent-y"]
        selected = orch.select_agent(candidates=candidates)
        assert selected in candidates

    def test_select_agents_multiple(self) -> None:
        agents = [_agent(f"Agent-{i}") for i in range(5)]
        orch = PuppeteerOrchestrator()
        for a in agents:
            orch.agents[a.id] = a

        selected = orch.select_agents(3)
        assert len(selected) == 3
        # All selected should be valid agent IDs
        agent_ids = {a.id for a in agents}
        for s in selected:
            assert s in agent_ids

    def test_select_agents_no_replacement(self) -> None:
        agents = [_agent(f"Agent-{i}") for i in range(5)]
        orch = PuppeteerOrchestrator()
        for a in agents:
            orch.agents[a.id] = a

        selected = orch.select_agents(3)
        # No duplicates
        assert len(set(selected)) == len(selected)

    def test_select_agents_caps_at_available(self) -> None:
        agents = [_agent(f"Agent-{i}") for i in range(2)]
        orch = PuppeteerOrchestrator()
        for a in agents:
            orch.agents[a.id] = a

        # Request more than available
        selected = orch.select_agents(5)
        assert len(selected) == 2

    def test_record_outcome(self) -> None:
        orch = PuppeteerOrchestrator()
        orch.record_outcome("agent-1", 1.0)
        stats = orch.bandit.get_stats()
        assert stats["agent-1"]["alpha"] == 2.0

    def test_record_outcome_updates_bandit(self) -> None:
        orch = PuppeteerOrchestrator()
        orch.record_outcome("agent-1", 0.0)
        orch.record_outcome("agent-1", 1.0)
        stats = orch.bandit.get_stats()
        assert stats["agent-1"]["alpha"] == 2.0
        assert stats["agent-1"]["beta"] == 2.0
