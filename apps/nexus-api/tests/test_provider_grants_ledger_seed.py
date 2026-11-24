"""The grant meter's cold-start seed: ``services.provider_grants.ledger_spent_usd``.

The seed must read every org's spend under the strict, FORCEd RLS of
migration 0028. Production has no ``DATABASE_ADMIN_URL``, so
``admin_session()`` falls back to the regular pool with no org set and the
policies hide every row: the seed read $0 and a Redis loss restarted the meter
from zero. The read now runs in ``tenant_session("platform")``.

The SQLite tests cover the query and the error path. ``TestForcedRlsOnPostgres``
proves the RLS context on a real Postgres; it runs when
``SELVA_RLS_TEST_DATABASE_URL`` names a throwaway database reachable as a role
that can create roles (CI's test-py job sets it). It creates its own schema and
login role and drops both.
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import fakeredis.aioredis
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from madfam_inference import grants as g
from nexus_api import database
from nexus_api.models import ComputeTokenLedger
from nexus_api.services import provider_grants

GRANT = g.ProviderGrant.model_validate(
    {
        "id": "seed-test-grant",
        "provider": "anthropic",
        "amount_usd": 10.0,
        "safety_margin_usd": 0.0,
        "starts_at": "2030-01-01T00:00:00Z",
        "expires_at": "2030-02-01T00:00:00Z",
        "allowed_orgs": ["madfam"],
    }
)
IN_WINDOW = datetime(2030, 1, 10, tzinfo=UTC)
BEFORE = datetime(2029, 12, 31, 23, 59, tzinfo=UTC)
AFTER = datetime(2030, 2, 1, tzinfo=UTC)
NOW = datetime(2030, 1, 15, tzinfo=UTC)

# (org_id, provider, cost_usd, created_at) — only the first two rows count.
LEDGER_ROWS: list[tuple[str, str, Decimal | None, datetime]] = [
    ("org-a", "anthropic", Decimal("1.250000"), IN_WINDOW),
    ("org-b", "anthropic", Decimal("2.500000"), IN_WINDOW),
    ("org-a", "anthropic", None, IN_WINDOW),  # token-only legacy debit
    ("org-b", "deepinfra", Decimal("9.000000"), IN_WINDOW),  # other provider
    ("org-a", "anthropic", Decimal("100.000000"), BEFORE),  # before the window
    ("org-a", "anthropic", Decimal("100.000000"), AFTER),  # at expiry: excluded
]
EXPECTED_SPEND = 3.75


def _ledger_total_query() -> Any:
    return (
        select(func.coalesce(func.sum(ComputeTokenLedger.cost_usd), 0))
        .where(ComputeTokenLedger.provider == GRANT.provider)
        .where(ComputeTokenLedger.created_at >= GRANT.starts_at)
        .where(ComputeTokenLedger.created_at < GRANT.expires_at)
    )


class TestLedgerSpentUsd:
    async def test_sums_every_org_in_the_window(self, db_session: AsyncSession) -> None:
        for org, provider, cost, at in LEDGER_ROWS:
            db_session.add(
                ComputeTokenLedger(
                    action="inference",
                    amount=1,
                    provider=provider,
                    org_id=org,
                    cost_usd=cost,
                    created_at=at,
                )
            )
        await db_session.commit()
        assert await provider_grants.ledger_spent_usd(GRANT) == pytest.approx(EXPECTED_SPEND)

    async def test_no_rows_is_a_real_zero(self) -> None:
        assert await provider_grants.ledger_spent_usd(GRANT) == 0.0

    async def test_reads_through_the_platform_rls_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        orgs: list[str] = []
        real = provider_grants.tenant_session

        @asynccontextmanager
        async def spy(org_id: str) -> Any:
            orgs.append(org_id)
            async with real(org_id) as db:
                yield db

        monkeypatch.setattr(provider_grants, "tenant_session", spy)
        assert not hasattr(provider_grants, "admin_session")
        await provider_grants.ledger_spent_usd(GRANT)
        assert orgs == ["platform"]

    async def test_database_error_raises_and_the_meter_stays_unseeded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        @asynccontextmanager
        async def down(_org_id: str) -> Any:
            raise OperationalError("SELECT 1", {}, ConnectionError("db down"))
            yield  # pragma: no cover

        monkeypatch.setattr(provider_grants, "tenant_session", down)
        with pytest.raises(OperationalError):
            await provider_grants.ledger_spent_usd(GRANT)

        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        meter = g.GrantMeter(redis, seeder=provider_grants.ledger_spent_usd)
        with pytest.raises(g.GrantMeterUnseededError):
            await meter.try_reserve(GRANT, 1.0, NOW)
        assert await redis.exists(g._keys(GRANT.id)[0]) == 0
        await redis.aclose()

    async def test_non_numeric_total_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Result:
            def scalar_one(self) -> object:
                return "garbage"

        class _Db:
            async def execute(self, _stmt: Any) -> _Result:
                return _Result()

        @asynccontextmanager
        async def fake(_org_id: str) -> Any:
            yield _Db()

        monkeypatch.setattr(provider_grants, "tenant_session", fake)
        with pytest.raises(TypeError):
            await provider_grants.ledger_spent_usd(GRANT)

    async def test_redis_lost_cold_start_reseeds_from_the_ledger(
        self, db_session: AsyncSession
    ) -> None:
        db_session.add(
            ComputeTokenLedger(
                action="inference",
                amount=1,
                provider="anthropic",
                org_id="org-a",
                cost_usd=Decimal("8.000000"),
                created_at=IN_WINDOW,
            )
        )
        await db_session.commit()
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        meter = g.GrantMeter(redis, seeder=provider_grants.ledger_spent_usd)
        assert not (await meter.try_reserve(GRANT, 3.0, NOW))[0]  # 8 + 3 > 10
        assert (await meter.snapshot(GRANT, NOW)).spent_usd == pytest.approx(8.0)
        await redis.aclose()


_PG_URL = os.environ.get("SELVA_RLS_TEST_DATABASE_URL", "")


@pytest.mark.skipif(not _PG_URL, reason="SELVA_RLS_TEST_DATABASE_URL not set")
class TestForcedRlsOnPostgres:
    async def test_platform_marker_sees_every_org_where_the_admin_fallback_sees_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base = make_url(_PG_URL).set(drivername="postgresql+asyncpg")
        suffix = uuid.uuid4().hex[:12]
        schema = role = f"grantseed_{suffix}"
        password = uuid.uuid4().hex
        owner = create_async_engine(base, poolclass=NullPool)
        try:
            async with owner.begin() as conn:
                await conn.execute(text(f"CREATE SCHEMA {schema}"))
                # Same shape as the app role: no superuser, no BYPASSRLS, and it
                # owns the table (FORCE is what stops the owner bypass).
                await conn.execute(
                    text(f"CREATE ROLE {role} LOGIN PASSWORD '{password}' NOSUPERUSER NOBYPASSRLS")
                )
                await conn.execute(
                    text(
                        f"CREATE TABLE {schema}.compute_token_ledger ("
                        "id uuid PRIMARY KEY, org_id varchar(255) NOT NULL, "
                        "provider varchar(50), cost_usd numeric(12, 6), "
                        "created_at timestamptz NOT NULL)"
                    )
                )
                for org, provider, cost, at in LEDGER_ROWS:
                    await conn.execute(
                        text(
                            f"INSERT INTO {schema}.compute_token_ledger "
                            "VALUES (:id, :org, :provider, :cost, :at)"
                        ),
                        {
                            "id": uuid.uuid4(),
                            "org": org,
                            "provider": provider,
                            "cost": cost,
                            "at": at,
                        },
                    )
                # Migration 0028's policy, verbatim, then FORCE.
                await conn.execute(
                    text(f"ALTER TABLE {schema}.compute_token_ledger ENABLE ROW LEVEL SECURITY")
                )
                await conn.execute(
                    text(
                        f"CREATE POLICY tenant_isolation_compute_token_ledger "
                        f"ON {schema}.compute_token_ledger FOR ALL "
                        "USING (current_setting('app.current_org_id', true) = 'platform' "
                        "OR org_id = current_setting('app.current_org_id', true)) "
                        "WITH CHECK (current_setting('app.current_org_id', true) = 'platform' "
                        "OR org_id = current_setting('app.current_org_id', true))"
                    )
                )
                await conn.execute(
                    text(f"ALTER TABLE {schema}.compute_token_ledger FORCE ROW LEVEL SECURITY")
                )
                await conn.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO {role}"))
                await conn.execute(
                    text(f"ALTER TABLE {schema}.compute_token_ledger OWNER TO {role}")
                )

            app = create_async_engine(
                base.set(username=role, password=password),
                poolclass=NullPool,
                connect_args={"server_settings": {"search_path": schema}},
            )
            factory = async_sessionmaker(app, class_=AsyncSession, expire_on_commit=False)
            monkeypatch.setattr(database, "get_session_factory", lambda: factory)
            # What admin_session() is in production: no DATABASE_ADMIN_URL, so
            # the admin factory is the regular pool.
            monkeypatch.setattr(database, "get_admin_session_factory", lambda: factory)
            try:
                async with database.admin_session() as db:
                    old_seed = (await db.execute(_ledger_total_query())).scalar_one()
                assert float(old_seed) == 0.0  # the bug: every row hidden

                spent = await provider_grants.ledger_spent_usd(GRANT)
                assert spent == pytest.approx(EXPECTED_SPEND)

                async with database.tenant_session("org-a") as db:
                    org_a = (await db.execute(_ledger_total_query())).scalar_one()
                assert float(org_a) == pytest.approx(1.25)  # tenants stay isolated
            finally:
                await app.dispose()
        finally:
            async with owner.begin() as conn:
                await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
                await conn.execute(text(f"DROP ROLE IF EXISTS {role}"))
            await owner.dispose()
