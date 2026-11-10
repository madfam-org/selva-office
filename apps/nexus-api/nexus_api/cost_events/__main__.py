"""Operator command: send Selva's inference usage to Dhanam's cost ledger.

::

    python -m nexus_api.cost_events --dry-run                     # counts only
    python -m nexus_api.cost_events --dry-run --since 2026-10-01  # a backfill preview
    python -m nexus_api.cost_events                               # one real sweep
    python -m nexus_api.cost_events --since 2026-10-01 --until 2026-10-31 --replay

``--dry-run`` builds the events and the outbox changes a sweep would make, then
rolls everything back: nothing is written, nothing is sent, and it works with
``SELVA_COST_EVENTS_EMIT_ENABLED`` off and no client pair. A real sweep needs
the flag and the full configuration (it names what is missing). ``--replay``
re-queues the window's sent and refused events as they are (Dhanam answers
``unchanged`` for an identical body).

Output: one JSON line of COUNTS and CODES (no org, no amount, no payload).
Exit codes: 0 done; 1 Dhanam or Janua refused the client (403, 409, 401 twice,
an unexpected status): an operator problem; 2 refused to run (flag off,
configuration missing or malformed).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date

from .config import CostEventsConfigError, load_config
from .runner import SweepRefusedError, run

logger = logging.getLogger("nexus_api.cost_events")


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nexus_api.cost_events",
        description="Send Selva inference usage to Dhanam as cost.event.v1 (counts only).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build and count; write nothing.")
    parser.add_argument("--since", type=_day, help="First civil day (YYYY-MM-DD, Mexico City).")
    parser.add_argument("--until", type=_day, help="Last civil day, inclusive (≤ yesterday).")
    parser.add_argument(
        "--replay", action="store_true", help="Re-queue sent and refused events of the window."
    )
    return parser


async def _main(args: argparse.Namespace) -> int:
    try:
        cfg = load_config()
        report = await run(
            cfg,
            dry_run=args.dry_run,
            since=args.since,
            until=args.until,
            replay=args.replay,
        )
    except (CostEventsConfigError, SweepRefusedError) as exc:
        print(json.dumps({"refused": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report.summary(), sort_keys=True))
    if report.alert:
        logger.error("ALERT cost events: sweep stopped on %s", report.stopped_on)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    if args.since and args.until and args.since > args.until:
        print(json.dumps({"refused": "--since is after --until"}), file=sys.stderr)
        return 2
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
