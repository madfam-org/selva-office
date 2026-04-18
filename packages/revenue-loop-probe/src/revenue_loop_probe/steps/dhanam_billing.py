"""Stage 5 — verify Dhanam recorded the billing event we just fired.

Dhanam's billing pipeline is async — the Stripe webhook returns 200 long
before the ledger row is written. We poll for up to ``DHANAM_BILLING_POLL_TIMEOUT_S``
(default 30s) with 1s backoff.
"""

from __future__ import annotations

import asyncio
import time

from ..probe import ProbeContext, ProbeStep, StageResult, StageStatus


class DhanamBillingStep(ProbeStep):
    name = "dhanam.billing_event"

    async def run(self, ctx: ProbeContext) -> StageResult:
        t0 = time.perf_counter()

        base_url = ctx.env.get("DHANAM_API_URL")
        api_token = ctx.env.get("DHANAM_PROBE_TOKEN")
        if not base_url or not api_token:
            return StageResult(
                name=self.name,
                status=StageStatus.SKIPPED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail="DHANAM_API_URL or DHANAM_PROBE_TOKEN not set",
            )

        stripe_event_id = ctx.state.get("stripe_event_id")
        if not stripe_event_id:
            return StageResult(
                name=self.name,
                status=StageStatus.SKIPPED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail="no stripe_event_id in ctx.state",
            )

        timeout_s = float(ctx.env.get("DHANAM_BILLING_POLL_TIMEOUT_S", "30"))
        deadline = time.perf_counter() + timeout_s
        url = f"{base_url.rstrip('/')}/v1/probe/billing-events/{stripe_event_id}"

        assert ctx.http is not None
        last_status: int | None = None
        last_body: str = ""
        while time.perf_counter() < deadline:
            try:
                resp = await ctx.http.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_token}",
                        "X-Probe-Correlation-Id": ctx.correlation_id,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                last_status = -1
                last_body = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(1.0)
                continue

            last_status = resp.status_code
            last_body = resp.text[:200]
            if resp.status_code == 200:
                body = resp.json() if resp.content else {}
                if body.get("status") in ("recorded", "succeeded", "complete"):
                    ctx.state["dhanam_billing_id"] = body.get("id")
                    return StageResult(
                        name=self.name,
                        status=StageStatus.PASSED,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                        facts={
                            "billing_id": body.get("id"),
                            "amount_mxn_cents": body.get("amount_mxn_cents"),
                            "tenant_id": body.get("tenant_id"),
                        },
                    )
            # 404 => Dhanam hasn't processed it yet; keep polling.
            await asyncio.sleep(1.0)

        return StageResult(
            name=self.name,
            status=StageStatus.FAILED,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            detail=(
                f"Dhanam did not record event {stripe_event_id} within "
                f"{timeout_s:.0f}s (last: {last_status} {last_body})"
            ),
        )
