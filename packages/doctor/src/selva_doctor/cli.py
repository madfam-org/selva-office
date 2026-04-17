"""CLI entrypoint — ``selva-doctor``.

Exits 0 if the report has no FAIL checks, 1 otherwise. Emits plain text by
default; pass ``--json`` for machine-readable output.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .doctor import Doctor


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="selva-doctor",
        description="Preflight check for the Selva/Selva runtime.",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    doctor = Doctor()
    report = asyncio.run(doctor.run())
    out = report.to_json() if args.json else report.to_text()
    print(out)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
