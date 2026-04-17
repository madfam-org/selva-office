"""MADFAM Factory Manifest v1 validator.

Intended to be wired into CI in every repo that publishes a
``.factory-manifest.json`` at its root. Failing the validator fails the
build — no silent drift.
"""

from .validator import (
    SCHEMA_PATH,
    FactoryManifestError,
    load_schema,
    validate_file,
    validate_document,
)

__all__ = [
    "SCHEMA_PATH",
    "FactoryManifestError",
    "load_schema",
    "validate_file",
    "validate_document",
]

__version__ = "0.1.0"
