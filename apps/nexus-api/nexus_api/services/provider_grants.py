"""Provider credit grants — the nexus-api side (ledger seed + status read).

``madfam_inference.grants`` owns the grant config, the Redis meter and the
router guard. This module only gives it what nexus-api (and the inference
gateway, which imports this slice) can uniquely provide: the USD usage
ledger, so a cold Redis meter starts from the spend already recorded since
the grant's ``starts_at`` instead of from zero.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import func, select

from madfam_inference import grants as grant_lib

from ..database import admin_session
from ..models import ComputeTokenLedger

logger = logging.getLogger(__name__)


async def ledger_spent_usd(grant: grant_lib.ProviderGrant) -> float:
    """USD recorded in the ledger for ``grant.provider`` inside the grant window.

    Counts every org's spend on that provider — an over-count when the same
    provider is also used outside the grant, which errs on the safe side
    (the ceiling is reached early, never late).
    """
    async with admin_session() as db:
        result = await db.execute(
            select(func.coalesce(func.sum(ComputeTokenLedger.cost_usd), 0))
            .where(ComputeTokenLedger.provider == grant.provider)
            .where(ComputeTokenLedger.created_at >= grant.starts_at)
            .where(ComputeTokenLedger.created_at < grant.expires_at)
        )
        value = result.scalar_one()
    return float(value if isinstance(value, Decimal | int | float) else 0)


def register_ledger_seeder() -> None:
    """Let the grant meter seed a cold Redis counter from this process's ledger."""
    grant_lib.set_ledger_seeder(ledger_spent_usd)
    logger.debug("provider grants: ledger seeder registered")
