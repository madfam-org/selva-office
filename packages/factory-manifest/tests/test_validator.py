"""Tests for the Factory Manifest v1 validator.

Covers the shipped schema + the three example manifests + a handful of
hand-crafted invalid manifests to make sure the schema catches what it
promises to catch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from madfam_factory_manifest import (
    FactoryManifestError,
    SCHEMA_PATH,
    load_schema,
    validate_document,
    validate_file,
)

PKG = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = PKG / "examples"


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text())


def test_schema_itself_is_valid():
    # `load_schema` calls Draft202012Validator.check_schema internally; if
    # the schema itself is malformed this throws.
    load_schema()
    assert SCHEMA_PATH.exists()


def test_all_shipped_examples_validate():
    # Every example under examples/ must validate. Drift here = a new
    # invariant was added to the schema without updating the examples.
    manifests = sorted(EXAMPLES_DIR.glob("*.manifest.json"))
    assert manifests, "no example manifests found — check examples/ path"
    for m in manifests:
        validate_file(m)


def test_karafiel_example_has_expected_shape():
    doc = _load_example("karafiel.cfdi-stamp.manifest.json")
    assert doc["factory_id"] == "karafiel.cfdi-stamp"
    assert doc["price"]["currency"] == "MXN"
    assert doc["price"]["model"] == "per_call"


def test_routecraft_manifest_validates():
    # The routecraft .factory-manifest.json was added in the 2026-04-17
    # compliance pass. Keep it valid.
    routecraft_manifest = PKG.parents[3] / "routecraft" / ".factory-manifest.json"
    if routecraft_manifest.exists():
        validate_file(routecraft_manifest)


@pytest.fixture
def valid_min_doc():
    """Minimum valid manifest — used as a starting point for negative tests."""
    return {
        "manifest_version": "1.0",
        "factory_id": "demo.noop",
        "owner": {
            "product": "demo",
            "team": "demo",
            "contact": "ops@madfam.io",
        },
        "version": "0.1.0",
        "inputs": {"type": "object"},
        "outputs": {"type": "object"},
        "price": {
            "currency": "MXN",
            "model": "free_internal",
            "free_internal": {"metering_only": True},
        },
        "sla": {
            "p95_latency_ms": 1000,
            "availability_target": 0.99,
            "error_budget_window_days": 30,
        },
        "idempotency": {
            "key_field": "idempotency_key",
            "ttl_seconds": 3600,
        },
    }


def test_min_doc_validates(valid_min_doc):
    validate_document(valid_min_doc)


def test_rejects_wrong_manifest_version(valid_min_doc):
    valid_min_doc["manifest_version"] = "2.0"
    with pytest.raises(FactoryManifestError):
        validate_document(valid_min_doc)


def test_rejects_missing_factory_id(valid_min_doc):
    valid_min_doc.pop("factory_id")
    with pytest.raises(FactoryManifestError):
        validate_document(valid_min_doc)


def test_rejects_non_mxn_currency(valid_min_doc):
    valid_min_doc["price"]["currency"] = "USD"
    with pytest.raises(FactoryManifestError):
        validate_document(valid_min_doc)


def test_rejects_bad_factory_id_format(valid_min_doc):
    # Factory IDs must be lowercase dotted — "Karafiel.cfdi" fails.
    valid_min_doc["factory_id"] = "Karafiel.cfdi-stamp"
    with pytest.raises(FactoryManifestError):
        validate_document(valid_min_doc)


def test_rejects_bad_semver(valid_min_doc):
    valid_min_doc["version"] = "alpha"
    with pytest.raises(FactoryManifestError):
        validate_document(valid_min_doc)


def test_rejects_owner_without_contact(valid_min_doc):
    valid_min_doc["owner"].pop("contact")
    with pytest.raises(FactoryManifestError):
        validate_document(valid_min_doc)


def test_rejects_invalid_contact_email(valid_min_doc):
    valid_min_doc["owner"]["contact"] = "not-an-email"
    with pytest.raises(FactoryManifestError):
        validate_document(valid_min_doc)


def test_error_surfaces_json_path(valid_min_doc):
    valid_min_doc["price"]["currency"] = "EUR"
    with pytest.raises(FactoryManifestError) as excinfo:
        validate_document(valid_min_doc)
    # Path must include 'price' and 'currency' so CI logs point at the field.
    joined = "\n".join(excinfo.value.errors)
    assert "price" in joined
    assert "currency" in joined
