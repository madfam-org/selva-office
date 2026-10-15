"""Fail-closed boundary checks for the catalogue integrity reader."""

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "catalogue_audit", Path(__file__).with_name("verify-catalogue.py")
)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class CatalogueIntegrityTests(unittest.TestCase):
    def test_zero_coverage_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "catalogue.json").write_text(json.dumps({"hyperobjects": []}))
            with self.assertRaisesRegex(ValueError, "100 unique"):
                v.verify(p)

    def test_material_or_preset_aliases_do_not_inflate_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            rows = [
                dict(id=str(i), repository="solid-hyperobjects", slug="one-family")
                for i in range(100)
            ]
            (p / "catalogue.json").write_text(json.dumps({"hyperobjects": rows}))
            with self.assertRaisesRegex(ValueError, "Duplicate source"):
                v.verify(p)

    def test_stale_evidence_cannot_verify_a_changed_catalogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "evidence").mkdir()
            rows = [
                dict(id=str(i), repository="solid-hyperobjects", slug=str(i)) for i in range(100)
            ]
            (p / "catalogue.json").write_text(json.dumps({"hyperobjects": rows}))
            (p / "evidence/catalogue-100.json").write_text(json.dumps({"catalogue_sha256": "old"}))
            with self.assertRaisesRegex(ValueError, "stale"):
                v.verify(p)

    def test_artifact_path_must_stay_inside_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for name in ["../other-file", "/absolute-file", "sub/../../other"]:
                with self.assertRaises(ValueError):
                    v.member(p, name)
            self.assertEqual(v.member(p, "source/main.py"), p.resolve() / "source/main.py")

    def test_nonfinite_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            v.canonical({"size": float("nan")})


class CatalogueBOMTests(unittest.TestCase):
    """Synthetic serialization cases, not native geometry or Linux CI evidence."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fields = ["id", "quantity", "unit", "material"]
        self.doc = {
            "artifacts": [{"path": "bill-of-materials.csv"}, {"path": "native-bom.json"}],
            "bom": [
                {"id": "outer", "quantity": 2, "unit": "cut", "material": "textile-unassigned"}
            ],
        }
        self.pattern = {"bom": [{"item": "outer", "qty": 2, "unit": "count"}]}
        self.write_csv(self.doc["bom"])
        (self.root / "native-bom.json").write_text(json.dumps(self.pattern["bom"]))

    def write_csv(self, rows, fields=None):
        with (self.root / "bill-of-materials.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields or self.fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_csv_round_trip_for_each_catalogue_kind_and_quoted_labels(self):
        for unit, material in [
            ("body", "material-unassigned"),
            ("cut", "paper"),
            ("cut", "textile-unassigned"),
        ]:
            with self.subTest(unit=unit, material=material):
                self.doc["bom"] = [
                    {
                        "id": "part, with\na quoted label",
                        "quantity": 2,
                        "unit": unit,
                        "material": material,
                    }
                ]
                self.write_csv(self.doc["bom"])
                v.verify_bom_exports(self.root, self.doc)

    def test_soft_and_reference_guide_material_roles(self):
        v.verify_bom_exports(self.root, self.doc, self.pattern)
        self.pattern["metadata"] = {"output_role": "reference-guide"}
        self.doc["bom"][0].update(unit="reference-guide", material="reference-print-unassigned")
        self.write_csv(self.doc["bom"])
        v.verify_bom_exports(self.root, self.doc, self.pattern)

    def test_csv_quantity_cannot_disagree_with_document(self):
        self.write_csv([self.doc["bom"][0] | {"quantity": 999}])
        with self.assertRaisesRegex(ValueError, "CSV/document parity"):
            v.verify_bom_exports(self.root, self.doc)

    def test_headers_and_row_count_are_exact(self):
        self.write_csv(self.doc["bom"], list(reversed(self.fields)))
        with self.assertRaisesRegex(ValueError, "header"):
            v.verify_bom_exports(self.root, self.doc)
        for rows in [[], self.doc["bom"] * 2]:
            self.write_csv(rows)
            with self.assertRaisesRegex(ValueError, "CSV/document parity"):
                v.verify_bom_exports(self.root, self.doc)

    def test_material_must_match_native_role_even_when_csv_agrees(self):
        self.doc["bom"][0]["material"] = "reference-print-unassigned"
        self.write_csv(self.doc["bom"])
        with self.assertRaisesRegex(ValueError, "material/output role"):
            v.verify_bom_exports(self.root, self.doc, self.pattern)

    def test_native_bom_export_matches_pattern_bom(self):
        (self.root / "native-bom.json").write_text(json.dumps([{"item": "outer", "qty": 999}]))
        with self.assertRaisesRegex(ValueError, "Native BOM/pattern parity"):
            v.verify_bom_exports(self.root, self.doc, self.pattern)

    def test_bom_exports_must_be_declared_artifacts(self):
        self.doc["artifacts"] = [{"path": "native-bom.json"}]
        with self.assertRaisesRegex(ValueError, "CSV is not a declared"):
            v.verify_bom_exports(self.root, self.doc)
        self.doc["artifacts"] = [{"path": "bill-of-materials.csv"}]
        with self.assertRaisesRegex(ValueError, "Native BOM is not a declared"):
            v.verify_bom_exports(self.root, self.doc, self.pattern)


if __name__ == "__main__":
    unittest.main()
