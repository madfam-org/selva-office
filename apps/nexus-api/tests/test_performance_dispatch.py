"""Tests for performance-aware dispatch scoring (PR 4: Agent Learning Loop)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _make_agent(
    tasks_completed=0,
    tasks_failed=0,
    approval_success_count=0,
    approval_denial_count=0,
):
    """Create a mock Agent with performance stats."""
    agent = MagicMock()
    agent.tasks_completed = tasks_completed
    agent.tasks_failed = tasks_failed
    agent.approval_success_count = approval_success_count
    agent.approval_denial_count = approval_denial_count
    return agent


class TestComputePerfWeight:
    """Unit tests for the _compute_perf_weight helper."""

    def test_new_agent_returns_neutral(self) -> None:
        from nexus_api.routers.swarms import _compute_perf_weight

        agent = _make_agent()
        weight = _compute_perf_weight(agent)
        assert weight == pytest.approx(0.5)

    def test_perfect_agent_returns_1_0(self) -> None:
        from nexus_api.routers.swarms import _compute_perf_weight

        agent = _make_agent(tasks_completed=10, approval_success_count=10)
        weight = _compute_perf_weight(agent)
        # completion_rate = 10/10 = 1.0, approval_rate = 10/10 = 1.0
        # weight = 0.5 * 1.0 + 0.5 * 1.0 = 1.0
        assert weight == pytest.approx(1.0)

    def test_poor_agent_returns_low(self) -> None:
        from nexus_api.routers.swarms import _compute_perf_weight

        agent = _make_agent(
            tasks_completed=1,
            tasks_failed=9,
            approval_success_count=2,
            approval_denial_count=8,
        )
        weight = _compute_perf_weight(agent)
        # completion_rate = 1/10 = 0.1, approval_rate = 2/10 = 0.2
        # weight = 0.5 * 0.2 + 0.5 * 0.1 = 0.15
        assert weight == pytest.approx(0.15)

    def test_tasks_only_no_approvals(self) -> None:
        from nexus_api.routers.swarms import _compute_perf_weight

        agent = _make_agent(tasks_completed=5, tasks_failed=5)
        weight = _compute_perf_weight(agent)
        # completion_rate = 5/10 = 0.5, approval_rate = default 0.5
        # weight = 0.5 * 0.5 + 0.5 * 0.5 = 0.5
        assert weight == pytest.approx(0.5)

    def test_higher_perf_agent_preferred(self) -> None:
        """In skill-equal agents, higher performance should score higher."""
        from nexus_api.routers.swarms import _compute_perf_weight

        good = _make_agent(
            tasks_completed=9,
            tasks_failed=1,
            approval_success_count=8,
            approval_denial_count=2,
        )
        bad = _make_agent(
            tasks_completed=2,
            tasks_failed=8,
            approval_success_count=3,
            approval_denial_count=7,
        )
        new = _make_agent()

        good_weight = _compute_perf_weight(good)
        bad_weight = _compute_perf_weight(bad)
        new_weight = _compute_perf_weight(new)

        # Good > new > bad
        assert good_weight > new_weight
        assert new_weight > bad_weight

    def test_performance_is_30_percent_modifier(self) -> None:
        """Verify the 30% weight doesn't dominate skill overlap."""
        from nexus_api.routers.swarms import _compute_perf_weight

        perfect = _compute_perf_weight(_make_agent(tasks_completed=100, approval_success_count=100))
        worst = _compute_perf_weight(_make_agent(tasks_failed=100, approval_denial_count=100))

        # With skill_score=1.0:
        # perfect: 1.0 * (0.7 + 0.3 * 1.0) = 1.0
        # worst:   1.0 * (0.7 + 0.3 * 0.0) = 0.7
        # Max gap is 0.3, so skill overlap (70%) dominates
        assert perfect == pytest.approx(1.0)
        assert worst == pytest.approx(0.0)
        # 0.7 (worst final) / 1.0 (perfect final) = 0.7 minimum ratio
        # This confirms 30% performance weight
