"""Stage 4 — fire a synthetic Stripe ``payment_intent.succeeded`` webhook
into Dhanam.

We mint an MXN-denominated payment event for the probe lead and sign it
exactly the way Stripe does, so Dhanam's HMAC verification treats it as a
real (test-mode) event. Dhanam is expected to run the full billing
pipeline: record the payment, credit the tenant, emit a billing event onto
the bus.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from ..probe import ProbeContext, ProbeStep, StageResult, StageStatus


def _sign_stripe(payload: bytes, secret: str, ts: int) -> str:
    """Build the `Stripe-Signature` header value for a given payload."""
    signed = f"{ts}.{payload.decode('utf-8')}".encode()
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


class StripeWebhookStep(ProbeStep):
    name = "stripe.webhook"

    async def run(self, ctx: ProbeContext) -> StageResult:
        t0 = time.perf_counter()

        webhook_url = ctx.env.get("DHANAM_STRIPE_WEBHOOK_URL")
        secret = ctx.env.get("DHANAM_STRIPE_WEBHOOK_SECRET")
        if not webhook_url or not secret:
            return StageResult(
                name=self.name,
                status=StageStatus.SKIPPED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail="DHANAM_STRIPE_WEBHOOK_URL or DHANAM_STRIPE_WEBHOOK_SECRET not set",
            )

        lead_id = ctx.state.get("lead_id")
        amount_mxn_cents = int(ctx.env.get("PROBE_PAYMENT_AMOUNT_MXN_CENTS", "4900"))

        event = {
            "id": f"evt_probe_{ctx.correlation_id}",
            "object": "event",
            "type": "payment_intent.succeeded",
            "livemode": not ctx.dry_run,
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": f"pi_probe_{ctx.correlation_id}",
                    "object": "payment_intent",
                    "amount": amount_mxn_cents,
                    "currency": "mxn",
                    "status": "succeeded",
                    "metadata": {
                        "madfam_probe": "true",
                        "madfam_correlation_id": ctx.correlation_id,
                        "madfam_lead_id": lead_id or "unknown",
                    },
                }
            },
        }
        payload = json.dumps(event, separators=(",", ":")).encode()
        ts = int(time.time())
        signature = _sign_stripe(payload, secret, ts)

        assert ctx.http is not None
        try:
            resp = await ctx.http.post(
                webhook_url,
                content=payload,
                headers={
                    "Stripe-Signature": signature,
                    "Content-Type": "application/json",
                    "X-Probe-Correlation-Id": ctx.correlation_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return StageResult(
                name=self.name,
                status=StageStatus.FAILED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail=f"Dhanam webhook unreachable: {type(exc).__name__}: {exc}",
            )

        if resp.status_code >= 400:
            return StageResult(
                name=self.name,
                status=StageStatus.FAILED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail=f"Dhanam webhook rejected signed probe event: {resp.status_code}",
                facts={"body_head": resp.text[:200]},
            )

        ctx.state["stripe_event_id"] = event["id"]
        return StageResult(
            name=self.name,
            status=StageStatus.PASSED,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            facts={
                "event_id": event["id"],
                "amount_mxn_cents": amount_mxn_cents,
                "dhanam_status": resp.status_code,
            },
        )
