"""inference_budget_status: platform-only, returns the C2 grant status fields."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import fakeredis.aioredis
import pytest

from madfam_inference import grants as g
from selva_tools.audience import Audience, AudienceMismatch, with_audience
from selva_tools.builtins.inference_budget import InferenceBudgetStatusTool

C2_FIELDS = {
    "id",
    "provider",
    "ceiling_usd",
    "spent_usd",
    "reserved_usd",
    "remaining_usd",
    "starts_at",
    "expires_at",
    "seconds_to_expiry",
    "burn_usd_per_hour_60m",
    "required_usd_per_hour",
    "pace_status",
    "autopilot",
}


@pytest.fixture
def guard() -> Iterator[g.GrantGuard]:
    book = g.parse_grants(
        json.dumps(
            {
                "grants": [
                    {
                        "id": "example-grant",
                        "provider": "anthropic",
                        "amount_usd": 100.0,
                        "safety_margin_usd": 5.0,
                        "starts_at": "2030-01-01T00:00:00Z",
                        "expires_at": "2030-01-02T00:00:00Z",
                        "allowed_orgs": ["madfam"],
                    }
                ]
            }
        )
    )
    state = g.GrantConfigState(grants=tuple(book.grants), source="test")
    guard = g.GrantGuard(
        config_loader=lambda: state,
        required=("anthropic",),
        meter=g.GrantMeter(fakeredis.aioredis.FakeRedis(decode_responses=True)),
        now_fn=lambda: datetime(2030, 1, 1, 12, tzinfo=UTC),
    )
    g.set_default_guard(guard)
    yield guard
    g.set_default_guard(None)


def test_tool_is_platform_audience() -> None:
    assert InferenceBudgetStatusTool.audience is Audience.PLATFORM


async def test_tenant_swarm_is_refused(
    monkeypatch: pytest.MonkeyPatch, guard: g.GrantGuard
) -> None:
    monkeypatch.setenv("AUDIENCE_FILTER_ENABLED", "true")
    with with_audience(Audience.TENANT), pytest.raises(AudienceMismatch):
        await InferenceBudgetStatusTool().execute()


async def test_platform_swarm_gets_c2_fields(guard: g.GrantGuard) -> None:
    with with_audience(Audience.PLATFORM):
        result = await InferenceBudgetStatusTool().execute()
    assert result.success
    [grant] = result.data["grants"]
    assert set(grant) >= C2_FIELDS
    assert grant["remaining_usd"] == pytest.approx(95.0)
    assert grant["seconds_to_expiry"] == 12 * 3600
    assert grant["pace_status"] == "behind"


async def test_unknown_grant_id(guard: g.GrantGuard) -> None:
    with with_audience(Audience.PLATFORM):
        result = await InferenceBudgetStatusTool().execute(grant_id="nope")
    assert result.success and result.data["grants"] == []
