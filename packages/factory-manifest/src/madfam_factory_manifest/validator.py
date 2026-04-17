"""Validator for Factory Manifest v1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PACKAGE_ROOT / "schema" / "factory-manifest.v1.schema.json"


@dataclass
class FactoryManifestError(Exception):
    """Aggregated validation error for a single manifest."""

    path: Path | None
    errors: list[str]

    def __str__(self) -> str:  # pragma: no cover — trivial
        prefix = f"{self.path}: " if self.path else ""
        return prefix + "; ".join(self.errors)


def load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Load the canonical v1 schema. Used by tests + CLI."""
    target = schema_path or SCHEMA_PATH
    return json.loads(target.read_text())


def validate_document(
    doc: dict[str, Any],
    *,
    schema_path: Path | None = None,
    source: Path | None = None,
) -> None:
    """Validate one manifest dict. Raise ``FactoryManifestError`` on failure."""
    schema = load_schema(schema_path)
    Draft202012Validator.check_schema(schema)
    # Enable format-checker so ``format: email`` / ``format: uri`` / etc.
    # actually assert instead of being hints.
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        raise FactoryManifestError(
            path=source,
            errors=[f"{list(e.path) or '<root>'}: {e.message}" for e in errors],
        )


def validate_file(path: Path, *, schema_path: Path | None = None) -> None:
    """Load + validate a ``.factory-manifest.json`` on disk."""
    doc = json.loads(path.read_text())
    validate_document(doc, schema_path=schema_path, source=path)
