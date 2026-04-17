"""CLI: ``madfam-validate-factory-manifest <path>...``.

Exits 0 if every path validates, 1 on any failure. Paths can be direct
files or directories (in which case every ``.factory-manifest.json``
beneath them is checked).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .validator import FactoryManifestError, validate_file


def _iter_manifests(paths: list[Path]):
    for p in paths:
        if p.is_dir():
            yield from sorted(p.rglob(".factory-manifest.json"))
        elif p.is_file():
            yield p
        else:
            print(f"warn: {p} does not exist — skipped", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="madfam-validate-factory-manifest")
    p.add_argument("paths", nargs="+", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    failures = 0
    count = 0
    for manifest in _iter_manifests(args.paths):
        count += 1
        try:
            validate_file(manifest)
            print(f"OK    {manifest}")
        except FactoryManifestError as exc:
            failures += 1
            print(f"FAIL  {manifest}", file=sys.stderr)
            for line in exc.errors:
                print(f"        {line}", file=sys.stderr)
    if count == 0:
        print("warn: no .factory-manifest.json files found", file=sys.stderr)
        return 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
