"""Tests for the weekly pricing-intel runner.

Covers: report formatting, dirty-flag detection, JSON mode, CLI
argument parsing. The runner calls the underlying pricing_intel tools
against an inline YAML catalog so we never rely on a live Dhanam API
here.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from selva_tools.cli.pricing_intel_weekly import (
    _build_parser,
    _format_report,
    _run_audit,
    main,
)

_SAMPLE_CATALOG = """
products:
  acme:
    name: Acme
    tiers:
      entry:
        dhanam_tier: essentials
        prices: { MXN: { monthly: 10000 } }
        features:
          - "f1"
      pro:
        dhanam_tier: pro
        prices: { MXN: { monthly: 30000 } }
        features:
          - "f1"
          - "f2"
coupons: {}
"""

_CLEAN_CATALOG = """
products:
  acme:
    name: Acme
    tiers:
      entry:
        dhanam_tier: essentials
        prices: { MXN: { monthly: 10000 } }
        features:
          - "f1"
          - "f2"
          - "f3"
      pro:
        dhanam_tier: pro
        prices: { MXN: { monthly: 25000 } }
        features:
          - "f1"
          - "f2"
          - "f3"
          - "f4"
          - "f5"
          - "f6"
coupons: {}
"""


def _fresh_audit(catalog_path: str) -> tuple[dict, dict]:
    return asyncio.run(_run_audit(catalog_path))


# ============================================================================
# _format_report
# ============================================================================


class TestFormatReport:
    def test_clean_catalog_reports_no_findings_and_is_not_dirty(self, tmp_path: Path) -> None:
        p = tmp_path / "catalog.yaml"
        p.write_text(_CLEAN_CATALOG)
        tier_gaps, promo_stacks = _fresh_audit(str(p))
        report, is_dirty = _format_report(tier_gaps, promo_stacks, str(p))
        assert is_dirty is False
        assert "Catalog is clean" in report
        assert "Pricing-Intel Weekly Brief" in report

    def test_dirty_catalog_is_flagged(self, tmp_path: Path) -> None:
        p = tmp_path / "catalog.yaml"
        p.write_text(_SAMPLE_CATALOG)
        tier_gaps, promo_stacks = _fresh_audit(str(p))
        report, is_dirty = _format_report(tier_gaps, promo_stacks, str(p))
        assert is_dirty is True
        assert "Cannibalization risks" in report

    def test_report_header_lists_source_url(self, tmp_path: Path) -> None:
        p = tmp_path / "catalog.yaml"
        p.write_text(_SAMPLE_CATALOG)
        tier_gaps, promo_stacks = _fresh_audit(str(p))
        report, _ = _format_report(tier_gaps, promo_stacks, str(p))
        assert str(p) in report

    def test_margin_risk_section_renders_when_present(self, tmp_path: Path) -> None:
        # Simulate a margin_risk by hand-crafting the promo_stacks dict.
        tier_gaps = {"findings": []}
        promo_stacks = {
            "findings": [
                {
                    "product_slug": "widget",
                    "tier_slug": "entry",
                    "coupon": "deep",
                    "currency": "MXN",
                    "list_monthly": 100,
                    "effective_monthly": 30,
                    "total_discount_pct": 70.0,
                    "severity": "margin_risk",
                    "note": "review margin floor",
                }
            ]
        }
        report, is_dirty = _format_report(tier_gaps, promo_stacks, "http://example/catalog")
        assert is_dirty is True
        assert "Margin risk" in report
        assert "widget" in report


# ============================================================================
# _build_parser — CLI surface
# ============================================================================


class TestParser:
    def test_defaults(self) -> None:
        args = _build_parser().parse_args([])
        # Default catalog URL is either env-overridden or the Dhanam URL.
        assert args.catalog_url
        assert args.json_only is False
        assert args.fail_on_risk is False

    def test_custom_catalog_url(self) -> None:
        args = _build_parser().parse_args(
            [
                "--catalog-url",
                "file:///tmp/catalog.yaml",
            ]
        )
        assert args.catalog_url == "file:///tmp/catalog.yaml"

    def test_fail_on_risk_flag(self) -> None:
        args = _build_parser().parse_args(["--fail-on-risk"])
        assert args.fail_on_risk is True

    def test_json_only_flag(self) -> None:
        args = _build_parser().parse_args(["--json-only"])
        assert args.json_only is True


# ============================================================================
# main() — end-to-end
# ============================================================================


class TestMainExitCodes:
    def test_clean_catalog_exits_zero(self, tmp_path: Path) -> None:
        p = tmp_path / "catalog.yaml"
        p.write_text(_CLEAN_CATALOG)
        rc = main(["--catalog-url", str(p), "--fail-on-risk"])
        assert rc == 0

    def test_dirty_catalog_with_fail_flag_exits_one(self, tmp_path: Path) -> None:
        p = tmp_path / "catalog.yaml"
        p.write_text(_SAMPLE_CATALOG)
        rc = main(["--catalog-url", str(p), "--fail-on-risk"])
        assert rc == 1

    def test_dirty_catalog_without_fail_flag_still_exits_zero(self, tmp_path: Path) -> None:
        # Without --fail-on-risk, dirty findings don't change exit code.
        # The K8s Job stays green; operators see findings via logs only.
        p = tmp_path / "catalog.yaml"
        p.write_text(_SAMPLE_CATALOG)
        rc = main(["--catalog-url", str(p)])
        assert rc == 0


class TestMainOutput:
    def test_json_mode_emits_parseable_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        p = tmp_path / "catalog.yaml"
        p.write_text(_SAMPLE_CATALOG)
        rc = main(["--catalog-url", str(p), "--json-only"])
        assert rc == 0
        stdout = capsys.readouterr().out
        data = json.loads(stdout)
        assert "as_of" in data
        assert "tier_gaps" in data
        assert "promo_stacks" in data
        assert "findings" in data["tier_gaps"]

    def test_markdown_mode_emits_human_report(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        p = tmp_path / "catalog.yaml"
        p.write_text(_CLEAN_CATALOG)
        main(["--catalog-url", str(p)])
        stdout = capsys.readouterr().out
        assert "# Pricing-Intel Weekly Brief" in stdout
