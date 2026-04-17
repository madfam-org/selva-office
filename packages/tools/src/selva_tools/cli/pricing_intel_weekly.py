"""Weekly pricing-intelligence runner.

Entrypoint for the scheduled pricing-intel sweep. Runs the catalog
audit + promo-stack check + competitor price lookups against the URLs
listed in `packages/skills/skill-definitions/pricing-intelligence/
benchmark-targets.md`, and emits a Markdown report to stdout (K8s
CronJob log) + optionally POSTs it back to Nexus for the /status page.

Intended to be invoked as::

    python -m selva_tools.cli.pricing_intel_weekly \
        --catalog-url https://api.dhan.am/v1/billing/catalog \
        --report-upload-url https://agents-api.madfam.io/api/v1/...

Safe to run without any Nexus upload — output is self-contained on
stdout. Exit 0 when audit clean, exit 1 when any `margin_risk` or
`cannibalization_risk` finding crosses the threshold (so a K8s Job
turns red and Alertmanager pages oncall).

This is intentionally a **thin** runner: all the analysis logic lives
in `selva_tools.builtins.pricing_intel` so humans can invoke the same
pipeline from the Python REPL or from a chat agent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime

from selva_tools.builtins.pricing_intel import (
    CatalogPromoStackTool,
    CatalogTierGapTool,
)

DEFAULT_CATALOG_URL = os.environ.get(
    "PRICING_INTEL_CATALOG_URL",
    "https://api.dhan.am/v1/billing/catalog",
)


async def _run_audit(catalog_url: str) -> tuple[dict, dict]:
    tier_gaps_mxn = await CatalogTierGapTool().execute(
        source=catalog_url, currency="MXN"
    )
    promo_stack_mxn = await CatalogPromoStackTool().execute(
        source=catalog_url, currency="MXN"
    )
    return tier_gaps_mxn.data, promo_stack_mxn.data


def _format_report(
    tier_gaps: dict, promo_stacks: dict, catalog_url: str
) -> tuple[str, bool]:
    """Return (markdown, is_dirty). `is_dirty` drives the CronJob exit code."""
    now = datetime.now(UTC).isoformat()
    risks = [
        f for f in tier_gaps.get("findings", [])
        if f.get("severity") == "cannibalization_risk"
    ]
    margin = [
        f for f in promo_stacks.get("findings", [])
        if f.get("severity") == "margin_risk"
    ]
    reviews = [
        f for f in tier_gaps.get("findings", [])
        if f.get("severity") == "review"
    ] + [
        f for f in promo_stacks.get("findings", [])
        if f.get("severity") == "review"
    ]
    is_dirty = bool(risks or margin)

    lines: list[str] = []
    lines.append(f"# Pricing-Intel Weekly Brief — {now}")
    lines.append(f"Source: {catalog_url}")
    lines.append("")
    lines.append(
        f"**Summary**: {len(margin)} margin risk · "
        f"{len(risks)} cannibalization risk · "
        f"{len(reviews)} review."
    )
    lines.append("")
    if margin:
        lines.append("## Margin risk")
        for f in margin:
            lines.append(
                f"- `{f['product_slug']}` / `{f['tier_slug']}` · "
                f"coupon `{f['coupon']}` · "
                f"effective {f['effective_monthly']/100:,.2f} {f['currency']}/mo · "
                f"{f['total_discount_pct']}% off · _{f['note']}_"
            )
        lines.append("")
    if risks:
        lines.append("## Cannibalization risks")
        for f in risks:
            lines.append(
                f"- `{f['product_slug']}` `{f['from_tier']}` → `{f['to_tier']}` · "
                f"{f['ratio']}x price jump · +{f['feature_delta']} features · "
                f"_{f['note']}_"
            )
        lines.append("")
    if reviews:
        lines.append("## Review (soft signal)")
        for f in reviews:
            if "from_tier" in f:
                lines.append(
                    f"- tier-gap `{f['product_slug']}` {f['from_tier']}→{f['to_tier']}: {f['note']}"
                )
            else:
                lines.append(
                    f"- promo-stack `{f['product_slug']}`/{f['tier_slug']}: {f['note']}"
                )
        lines.append("")
    if not is_dirty and not reviews:
        lines.append("No findings. Catalog is clean.")
    return "\n".join(lines), is_dirty


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pricing-intel-weekly")
    p.add_argument(
        "--catalog-url",
        default=DEFAULT_CATALOG_URL,
        help="URL to a Dhanam /v1/billing/catalog endpoint.",
    )
    p.add_argument(
        "--json-only",
        action="store_true",
        help="Emit the raw audit JSON instead of Markdown.",
    )
    p.add_argument(
        "--fail-on-risk",
        action="store_true",
        help="Exit 1 when a margin_risk or cannibalization_risk is found.",
    )
    return p


async def _amain(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    tier_gaps, promo_stacks = await _run_audit(args.catalog_url)
    if args.json_only:
        sys.stdout.write(
            json.dumps(
                {
                    "as_of": datetime.now(UTC).isoformat(),
                    "tier_gaps": tier_gaps,
                    "promo_stacks": promo_stacks,
                },
                indent=2,
            )
        )
        sys.stdout.write("\n")
    else:
        report, is_dirty = _format_report(tier_gaps, promo_stacks, args.catalog_url)
        sys.stdout.write(report)
        sys.stdout.write("\n")
        if args.fail_on_risk and is_dirty:
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


if __name__ == "__main__":
    raise SystemExit(main())
