"""Orchestrator: run a list of checks and produce a ``DoctorReport``."""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from .checks import Check, CheckStatus, DoctorReport, default_checks


class Doctor:
    """Runs a set of preflight checks in parallel and aggregates the result."""

    def __init__(
        self,
        checks: list[Callable[[], Awaitable[Check]]] | None = None,
    ) -> None:
        self._checks = checks or default_checks()

    async def run(self) -> DoctorReport:
        started = time.time()
        results = await asyncio.gather(
            *(self._invoke(c) for c in self._checks),
            return_exceptions=True,
        )
        checks: list[Check] = []
        for idx, r in enumerate(results):
            if isinstance(r, BaseException):
                # A check raised despite the "never raise" contract; surface
                # as a FAIL so we don't silently drop it.
                fn = self._checks[idx]
                checks.append(
                    Check(
                        name=getattr(fn, "__name__", "anon"),
                        status=CheckStatus.FAIL,
                        detail=f"check raised {type(r).__name__}: {r}",
                    )
                )
            else:
                checks.append(r)
        return DoctorReport(
            checks=checks,
            started_at=started,
            finished_at=time.time(),
        )

    @staticmethod
    async def _invoke(fn: Callable[[], Awaitable[Check]]) -> Check:
        # Thin wrapper so we can swap in per-check timeouts later without
        # touching every check's call site.
        return await fn()
