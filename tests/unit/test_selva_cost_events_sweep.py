"""Selva inference → Dhanam: outbox, idempotency, the sweep, the Dhanam client, the command.

In-memory SQLite for the ledger and the outbox, ``httpx.MockTransport`` for
Janua and Dhanam. Nothing leaves the process.
"""

from __future__ import annotations

import dataclasses
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest

os.environ.setdefault("ENVIRONMENT", "development")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from nexus_api.cost_events import __main__ as command  # noqa: E402
from nexus_api.cost_events import outbox as ob  # noqa: E402
from nexus_api.cost_events.config import BUILTIN_PLATFORM_ORGS, CostEventsConfig  # noqa: E402
from nexus_api.cost_events.dhanam_client import (  # noqa: E402
    DhanamCostEventsClient,
    error_code,
)
from nexus_api.cost_events.rollup import FundingRules  # noqa: E402
from nexus_api.cost_events.runner import SweepRefusedError, run, window  # noqa: E402
from nexus_api.database import Base  # noqa: E402
from nexus_api.models import ComputeTokenLedger  # noqa: E402

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=UTC)  # civil day 2026-11-10 in Mexico City
DAY = date(2026, 11, 9)
TOKEN_URL = "https://auth.example.test/api/v1/oauth/token"
EVENTS_URL = "https://api.example.test/v1/cost-events"
CFG = CostEventsConfig(
    enabled=True,
    client_id="cid",
    client_secret="secret-value",
    token_url=TOKEN_URL,
    events_url=EVENTS_URL,
    lookback_days=3,
    platform_orgs=BUILTIN_PLATFORM_ORGS,
)
RULES = FundingRules()


@pytest.fixture()
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[
                    Base.metadata.tables[name]
                    for name in ("compute_token_ledger", "cost_event_outbox")
                ],
            )
        )
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def factory_for(maker: async_sessionmaker[AsyncSession]) -> Callable[[], Any]:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session
            await session.commit()

    return factory


async def add_rows(maker: async_sessionmaker[AsyncSession], *rows: dict[str, Any]) -> None:
    async with maker() as session:
        for row in rows:
            session.add(
                ComputeTokenLedger(
                    id=uuid.uuid4(),
                    action="inference_proxy",
                    amount=row.get("tokens", 1000),
                    provider=row.get("provider", "deepinfra"),
                    model="m",
                    org_id=row.get("org", "madfam"),
                    caller=row.get("caller", "svc"),
                    cost_usd=Decimal(row.get("cost", "1.250000")),
                    created_at=row.get("at", datetime(2026, 11, 9, 18, tzinfo=UTC)),
                )
            )
        await session.commit()


async def outbox_rows(maker: async_sessionmaker[AsyncSession]) -> list[ob.CostEventOutbox]:
    async with maker() as session:
        return list((await session.execute(select(ob.CostEventOutbox))).scalars())


class FakeDhanam:
    """Janua + Dhanam on one MockTransport. ``answers`` pops one status per events POST."""

    def __init__(self, *answers: int | tuple[int, dict[str, Any]]) -> None:
        self.answers = list(answers)
        self.tokens_issued = 0
        self.batches: list[list[dict[str, Any]]] = []
        self.auth_headers: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            assert b"grant_type=client_credentials" in request.content
            assert b"scope=dhanam-cost-events%3Awrite" in request.content
            self.tokens_issued += 1
            return httpx.Response(
                200, json={"access_token": f"tok-{self.tokens_issued}", "expires_in": 3600}
            )
        assert str(request.url) == EVENTS_URL
        self.auth_headers.append(request.headers["authorization"])
        self.batches.append(json.loads(request.content)["events"])
        answer = self.answers.pop(0) if self.answers else 200
        status, body = answer if isinstance(answer, tuple) else (answer, {"received": 1})
        return httpx.Response(status, json=body)

    def client(self) -> DhanamCostEventsClient:
        return DhanamCostEventsClient(CFG, transport=httpx.MockTransport(self.handler))


async def sweep(
    maker: async_sessionmaker[AsyncSession], dhanam: FakeDhanam | None = None, **kwargs: Any
) -> Any:
    return await run(
        kwargs.pop("cfg", CFG),
        dry_run=kwargs.pop("dry_run", False),
        rules=RULES,
        session_factory=factory_for(maker),
        client=(dhanam or FakeDhanam()).client(),
        now=NOW,
        **kwargs,
    )


# ── window ────────────────────────────────────────────────────────────────────


def test_window_is_closed_days_only() -> None:
    today = date(2026, 11, 10)
    assert window(CFG, today) == [date(2026, 11, 7), date(2026, 11, 8), date(2026, 11, 9)]
    assert window(CFG, today, until=today) == window(CFG, today)  # today never builds
    assert window(CFG, today, since=date(2026, 11, 9), until=date(2026, 11, 9)) == [DAY]
    floored = CostEventsConfig(lookback_days=3, start_date=date(2026, 11, 9))
    assert window(floored, today) == [DAY]
    assert window(CFG, today, since=today) == []


# ── the sweep ─────────────────────────────────────────────────────────────────


async def test_dry_run_writes_and_sends_nothing(sessions: async_sessionmaker[AsyncSession]) -> None:
    await add_rows(sessions, {}, {"org": "t1"})
    dhanam = FakeDhanam()
    off = CostEventsConfig(lookback_days=3)  # flag off, no client pair: still fine
    report = await sweep(sessions, dhanam, cfg=off, dry_run=True)
    summary = report.summary()
    assert summary["events_built"] == 2
    assert summary["outbox_changes"] == {"created": 2}
    assert await outbox_rows(sessions) == []
    assert dhanam.batches == [] and dhanam.tokens_issued == 0
    assert "t1" not in json.dumps(summary)  # counts and codes only


async def test_real_sweep_refuses_without_flag_or_config(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(SweepRefusedError, match="SELVA_COST_EVENTS_EMIT_ENABLED"):
        await sweep(sessions, cfg=CostEventsConfig())
    with pytest.raises(SweepRefusedError, match="SELVA_DHANAM_COST_EVENTS_CLIENT_ID"):
        await sweep(sessions, cfg=CostEventsConfig(enabled=True))


async def test_sweep_sends_once_and_replays_are_idempotent(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await add_rows(sessions, {}, {"org": "t1"}, {"at": NOW})  # NOW is today: not built
    dhanam = FakeDhanam()
    report = await sweep(sessions, dhanam)
    assert report.sent == {"ok": 2} and report.pending_after == 0
    assert len(dhanam.batches) == 1 and len(dhanam.batches[0]) == 2
    assert dhanam.auth_headers == ["Bearer tok-1"]
    assert {r.status for r in await outbox_rows(sessions)} == {"sent"}

    second = await sweep(sessions, dhanam)
    assert second.changes == {"unchanged": 2}
    assert len(dhanam.batches) == 1  # nothing new to send

    replay = await sweep(sessions, dhanam, replay=True)
    assert replay.changes == {"updated": 2}
    assert dhanam.batches[1] == dhanam.batches[0]  # same ids, same bodies


async def test_late_rows_update_the_same_event(sessions: async_sessionmaker[AsyncSession]) -> None:
    await add_rows(sessions, {})
    dhanam = FakeDhanam()
    await sweep(sessions, dhanam)
    await add_rows(sessions, {"cost": "0.750000"})
    report = await sweep(sessions, dhanam)
    assert report.changes == {"updated": 1}
    first, second = dhanam.batches
    assert first[0]["id"] == second[0]["id"]
    assert (first[0]["amount_minor"], second[0]["amount_minor"]) == (125, 200)


async def test_vanished_group_is_cancelled_or_deleted(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await add_rows(sessions, {"caller": "svc-a"})
    dhanam = FakeDhanam()
    await sweep(sessions, dhanam)
    mapped = dataclasses.replace(CFG, product_by_caller={"svc-a": "tezca"})
    report = await sweep(sessions, dhanam, cfg=mapped)
    assert report.changes == {"created": 1, "cancelled": 1}
    statuses = sorted(e.get("status", "active") for e in dhanam.batches[1])
    assert statuses == ["active", "cancelled"]

    # Never accepted by Dhanam → simply deleted.
    async with sessions() as session:
        await ob.sync_outbox(
            session, {"x:1": {"id": "x:1", "amount_minor": 1}}, {"x:1": date(2026, 11, 1)},
            [date(2026, 11, 1)],
        )  # fmt: skip
        await session.commit()
    async with sessions() as session:
        changes = await ob.sync_outbox(session, {}, {}, [date(2026, 11, 1)])
        await session.commit()
    assert changes == {"deleted": 1}


async def test_400_marks_only_the_refused_events(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await add_rows(sessions, {}, {"org": "t1"})
    refusal = {"errors": [{"index": 1, "errors": ["amount_minor must be a non-zero integer"]}]}
    dhanam = FakeDhanam((400, refusal), 200)
    report = await sweep(sessions, dhanam)
    assert report.sent == {"rejected": 1, "ok": 1}
    rows = {r.status: r for r in await outbox_rows(sessions)}
    assert rows["rejected"].last_error == "amount_minor"
    assert len(dhanam.batches[1]) == 1  # the valid one went out on its own


async def test_transient_failure_backs_off_and_retries(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await add_rows(sessions, {})
    dhanam = FakeDhanam(503)
    report = await sweep(sessions, dhanam)
    assert report.stopped_on == "transient" and not report.alert
    (row,) = await outbox_rows(sessions)
    assert (row.status, row.attempts, row.last_error) == ("pending", 1, "http_503")
    assert row.next_attempt_at is not None
    # Backed off: the next sweep inside the window sends nothing.
    await sweep(sessions, dhanam)
    assert len(dhanam.batches) == 1
    assert ob.backoff(1) == timedelta(minutes=1)
    assert ob.backoff(30) == ob.MAX_BACKOFF


@pytest.mark.parametrize(("status", "outcome"), [(403, "forbidden"), (409, "conflict")])
async def test_operator_problems_stop_the_run_and_alert(
    sessions: async_sessionmaker[AsyncSession], status: int, outcome: str
) -> None:
    await add_rows(sessions, {})
    report = await sweep(sessions, FakeDhanam(status))
    assert report.stopped_on == outcome and report.alert
    (row,) = await outbox_rows(sessions)
    assert row.status == "pending"


async def test_401_refreshes_the_token_once(sessions: async_sessionmaker[AsyncSession]) -> None:
    await add_rows(sessions, {})
    dhanam = FakeDhanam(401, 200)
    report = await sweep(sessions, dhanam)
    assert report.sent == {"ok": 1}
    assert dhanam.auth_headers == ["Bearer tok-1", "Bearer tok-2"]

    await add_rows(sessions, {"org": "t9"})
    twice = await sweep(sessions, FakeDhanam(401, 401))
    assert twice.stopped_on == "unauthorized" and twice.alert


async def test_janua_down_is_transient(sessions: async_sessionmaker[AsyncSession]) -> None:
    await add_rows(sessions, {})

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(503)
        raise AssertionError("no events POST without a token")

    client = DhanamCostEventsClient(CFG, transport=httpx.MockTransport(handler))
    report = await run(
        CFG, dry_run=False, rules=RULES, session_factory=factory_for(sessions),
        client=client, now=NOW,
    )  # fmt: skip
    assert report.stopped_on == "transient"
    (row,) = await outbox_rows(sessions)
    assert row.last_error == "token_unavailable"


async def test_post_batch_bounds() -> None:
    client = FakeDhanam().client()
    with pytest.raises(ValueError):
        await client.post_batch([])
    with pytest.raises(ValueError):
        await client.post_batch([{}] * 501)
    assert "secret-value" not in repr(client)


def test_error_codes_keep_the_field_never_the_value() -> None:
    assert error_code("amount_minor must be a non-zero integer") == "amount_minor"
    assert error_code("unknown field funding") == "unknown_field"
    assert error_code("duplicate (source, id) in the same batch") == "duplicate_id"
    assert error_code("") == "unspecified"


# ── the command ───────────────────────────────────────────────────────────────


def test_command_exit_codes(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setenv("SELVA_COST_EVENTS_EMIT_ENABLED", "false")
    assert command.main([]) == 2  # flag off: refused, nothing read
    assert "SELVA_COST_EVENTS_EMIT_ENABLED" in capsys.readouterr().err

    monkeypatch.setenv("SELVA_COST_EVENTS_LOOKBACK_DAYS", "999")
    assert command.main(["--dry-run"]) == 2
    monkeypatch.delenv("SELVA_COST_EVENTS_LOOKBACK_DAYS")

    assert command.main(["--since", "2026-11-09", "--until", "2026-11-01"]) == 2

    class Report:
        alert = True
        stopped_on = "forbidden"

        def summary(self) -> dict[str, Any]:
            return {"stopped_on": "forbidden"}

    async def fake_run(*_args: Any, **_kwargs: Any) -> Report:
        return Report()

    monkeypatch.setattr(command, "run", fake_run)
    assert command.main(["--dry-run"]) == 1
    assert json.loads(capsys.readouterr().out.strip()) == {"stopped_on": "forbidden"}


# ── the grant guard's config, as the sweep reads it ──────────────────────────


def test_funding_rules_come_from_the_grant_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_api.cost_events.config import CostEventsConfigError
    from nexus_api.cost_events.runner import funding_rules_from_env

    monkeypatch.delenv("PROVIDER_GRANTS_PATH", raising=False)
    monkeypatch.setenv("PROVIDER_GRANTS_REQUIRED_FOR", "anthropic")
    monkeypatch.setenv("PLATFORM_ORG_ID", "madfam")
    monkeypatch.setenv(
        "PROVIDER_GRANTS_JSON",
        json.dumps(
            {
                "grants": [
                    {
                        "id": "g1",
                        "provider": "anthropic",
                        "amount_usd": 10,
                        "starts_at": "2026-11-01T00:00:00Z",
                        "expires_at": "2026-12-01T00:00:00Z",
                        "allowed_orgs": ["madfam"],
                    }
                ]
            }
        ),
    )
    rules = funding_rules_from_env()
    assert [g.provider for g in rules.grants] == ["anthropic"]
    assert rules.required_providers == frozenset({"anthropic"})
    assert rules.is_extra_credential("anthropic-ops")

    monkeypatch.setenv("PROVIDER_GRANTS_JSON", '{"grants": [{"id": "BAD"}]}')
    with pytest.raises(CostEventsConfigError, match="grants config is invalid"):
        funding_rules_from_env()


async def test_network_errors_are_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        raise httpx.ConnectError("down", request=request)

    client = DhanamCostEventsClient(CFG, transport=httpx.MockTransport(handler))
    result = await client.post_batch([{"id": "a"}])
    assert (result.outcome, result.error_code) == ("transient", "network")

    def no_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>")

    bad_janua = DhanamCostEventsClient(CFG, transport=httpx.MockTransport(no_json))
    result = await bad_janua.post_batch([{"id": "a"}])
    assert (result.outcome, result.error_code) == ("transient", "token_unavailable")
