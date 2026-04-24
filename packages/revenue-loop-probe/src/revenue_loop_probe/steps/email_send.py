"""Stage 3 — fire the drafted email through the send pipeline.

In dry-run mode (the default), this never reaches Resend or the real
recipient. Instead it calls the probe-scoped endpoint which validates
the send contract (signing, HTML sanitisation, unsubscribe header) and
returns success without hitting the mail provider.
"""

from __future__ import annotations

import contextlib
import time

from ..probe import ProbeContext, ProbeStep, StageResult, StageStatus


class EmailSendStep(ProbeStep):
    name = "email.send"

    async def run(self, ctx: ProbeContext) -> StageResult:
        t0 = time.perf_counter()

        base_url = ctx.env.get("NEXUS_API_URL")
        api_token = ctx.env.get("NEXUS_PROBE_TOKEN")
        if not base_url or not api_token:
            return StageResult(
                name=self.name,
                status=StageStatus.SKIPPED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail="NEXUS_API_URL or NEXUS_PROBE_TOKEN not set",
            )

        draft = ctx.state.get("draft_body")
        lead_id = ctx.state.get("lead_id")
        if not draft or not lead_id:
            return StageResult(
                name=self.name,
                status=StageStatus.SKIPPED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail="draft_body or lead_id missing from prior stages",
            )

        assert ctx.http is not None
        url = f"{base_url.rstrip('/')}/api/v1/probe/email/send"
        try:
            resp = await ctx.http.post(
                url,
                json={
                    "correlation_id": ctx.correlation_id,
                    "lead_id": lead_id,
                    "body": draft,
                    "dry_run": ctx.dry_run,
                },
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "X-Probe-Correlation-Id": ctx.correlation_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return StageResult(
                name=self.name,
                status=StageStatus.FAILED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail=f"send endpoint unreachable: {type(exc).__name__}: {exc}",
            )

        if resp.status_code >= 400:
            return StageResult(
                name=self.name,
                status=StageStatus.FAILED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail=f"send endpoint returned {resp.status_code}: {resp.text[:200]}",
            )

        body = {}
        with contextlib.suppress(Exception):
            body = resp.json()

        # Contract checks — even in dry-run we want to see these:
        missing_contract = []
        if not body.get("list_unsubscribe_header_present"):
            missing_contract.append("list-unsubscribe")
        if body.get("sanitized_html") is None:
            missing_contract.append("sanitized_html")
        if not body.get("from_address"):
            missing_contract.append("from_address")
        if missing_contract:
            return StageResult(
                name=self.name,
                status=StageStatus.FAILED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail=f"send contract missing: {', '.join(missing_contract)}",
                facts={"raw_body": str(body)[:200]},
            )

        ctx.state["message_id"] = body.get("message_id")
        status = StageStatus.DRY_RUN if ctx.dry_run else StageStatus.PASSED
        return StageResult(
            name=self.name,
            status=status,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            facts={
                "message_id": body.get("message_id"),
                "from_address": body.get("from_address"),
                "provider": body.get("provider"),
            },
        )
