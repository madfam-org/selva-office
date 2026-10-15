"""Stored-record fixtures only; native geometry is exercised in jewelry-studio's suite."""

import csv
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

path = Path(__file__).with_name("verify-bundle.py")
spec = importlib.util.spec_from_file_location("verify_bundle", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InsertionEvidence(unittest.TestCase):
    def report(self):
        return {
            "profile": "local-aglet-axis-probe-0.1",
            "bore_stop_depth_mm": 11,
            "external_length_mm": 12,
            "guide_reserved_per_end_mm": 12,
            "guide_overrun_per_end_mm": 1,
            "native_point_queries": 50,
            "status": "incompatible-insertion",
        }

    def test_stored_native_probe_keeps_the_incompatibility(self):
        module.verify_insertion_report(self.report(), 12, 1)

    def test_changed_readout_and_nonfinite_measurements_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            module.verify_insertion_report(self.report(), 12, 0)
        value = self.report()
        value["bore_stop_depth_mm"] = float("nan")
        with self.assertRaisesRegex(ValueError, "Nonfinite"):
            module.verify_insertion_report(value, 12, 1)

    def test_zero_probe_coverage_and_promoted_fit_are_rejected(self):
        for field, value in (
            ("native_point_queries", 0),
            ("status", "nominal-axis-fit"),
        ):
            report = self.report()
            report[field] = value
            with self.assertRaises(ValueError):
                module.verify_insertion_report(report, 12, 1)


class BundleIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2) + "\n"
            if isinstance(value, (dict, list))
            else value
        )

    def fixture(self):
        ref = "source-reference/solid-hyperobjects/fixture"
        self.write(ref + "/main.py", "# Stored-record test; never executed\n")
        self.write(ref + "/project.json", "{}\n")
        self.write(
            "source-reference/solid-hyperobjects/LICENSE",
            "Synthetic notice fixture only\n",
        )
        source = {
            "repository": "https://github.com/madfam-org/solid-hyperobjects",
            "commit": "a" * 40,
            "path": "jewelry-blank",
            "license": "CERN-OHL-W-2.0",
            "files": {
                n: hashlib.sha256((self.root / ref / n).read_bytes()).hexdigest()
                for n in ("main.py", "project.json")
            },
        }
        original_folder = self.root / ref
        original_folder.rename(original_folder.with_name("jewelry-blank"))
        source["source_digest"] = module.digest(source)
        parameters = {
            "ring_size": 7,
            "band_w": 6,
            "band_t": 2,
            "profile": "flat",
            "material": "silver-study",
        }
        source.update(
            {
                "parameters": {
                    k: parameters[k]
                    for k in ("ring_size", "band_w", "band_t", "profile")
                },
                "engine": {"repository": "yantra4d", "commit": "b" * 40},
            }
        )
        source["resolved_instance_digest"] = module.digest(source)
        request = {
            "family": "ring",
            "parameters": parameters,
            "pins": {"solid-hyperobjects": "a" * 40, "yantra4d": "b" * 40},
            "adapter_sha256": "c" * 64,
        }
        identity = module.digest(request)
        bom = [
            {
                "id": "band",
                "source": source["resolved_instance_digest"],
                "quantity": 1,
                "unit": "piece",
                "material": "silver-study",
            }
        ]
        self.write("request.json", request)
        self.write(
            "solid-report.json",
            {
                "brep_valid": True,
                "bore_verified": True,
                "mesh_watertight": True,
                "requested_bore_mm": 17.3196,
            },
        )
        self.write("model.stl", "Synthetic artifact bytes, not a native mesh\n")
        self.write(
            "accessory-handoff.json",
            {
                "instance_digest": identity,
                "parameters": parameters,
                "visibility": "private",
                "manufacturing_qualified": False,
            },
        )
        text = io.StringIO()
        writer = csv.DictWriter(text, fieldnames=list(bom[0]))
        writer.writeheader()
        writer.writerows(bom)
        self.write("bill-of-materials.csv", text.getvalue())
        artifacts = [
            {
                "path": str(p.relative_to(self.root)),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }
            for p in sorted(self.root.rglob("*"))
            if p.is_file()
        ]
        self.doc = {
            "format": "madfam.jewellery-instance",
            "version": "0.1.0-draft",
            "request": request,
            "instance_digest": identity,
            "units": "mm",
            "runtime_closure_verified": False,
            "manufacturing_qualified": False,
            "sources": [source],
            "bom": bom,
            "metrics": {"inner_diameter_mm": 17.3196},
            "checks": [
                {
                    "status": "passed",
                    "read_count": 1,
                    "scope": "Synthetic stored record",
                }
            ],
            "limits": ["No geometry was executed by this test fixture"],
            "artifacts": artifacts,
        }
        self.reseal(archive=True)

    def reseal(self, archive=False):
        self.doc.pop("document_digest", None)
        self.doc["document_digest"] = module.digest(self.doc)
        self.write("instance.json", self.doc)
        if archive:
            with zipfile.ZipFile(self.root / "design-bundle.zip", "w") as bundle:
                for item in self.doc["artifacts"]:
                    bundle.write(self.root / item["path"], item["path"])
                bundle.write(self.root / "instance.json", "instance.json")

    def test_positive_record_stays_scoped(self):
        report = module.verify(self.root)
        self.assertFalse(report["native_geometry_recomputed"])
        self.assertFalse(report["manufacturing_qualified"])
        self.assertEqual(report["source_instances_read"], 1)

    def test_artifact_tampering_is_rejected(self):
        self.write("model.stl", "changed\n")
        with self.assertRaisesRegex(ValueError, "Artifact changed"):
            module.verify(self.root)

    def test_document_tampering_is_rejected(self):
        self.doc["metrics"]["inner_diameter_mm"] = 20
        self.write("instance.json", self.doc)
        with self.assertRaisesRegex(ValueError, "document digest"):
            module.verify(self.root)

    def test_resealed_size_change_cannot_keep_old_native_bore(self):
        self.doc["request"]["parameters"]["ring_size"] = 8
        self.doc["instance_digest"] = module.digest(self.doc["request"])
        # Also update the exported request and its file lock, simulating a mistaken partial rebuild.
        self.write("request.json", self.doc["request"])
        item = next(a for a in self.doc["artifacts"] if a["path"] == "request.json")
        data = (self.root / "request.json").read_bytes()
        item.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        self.reseal()
        with self.assertRaisesRegex(ValueError, "input/source parameter"):
            module.verify(self.root, False)

    def test_no_zero_read_pass(self):
        self.doc["checks"][0]["read_count"] = 0
        self.reseal()
        with self.assertRaisesRegex(ValueError, "Zero reads"):
            module.verify(self.root, False)

    def test_cannot_promote_physical_qualification(self):
        self.doc["manufacturing_qualified"] = True
        self.reseal()
        with self.assertRaisesRegex(ValueError, "cannot promote"):
            module.verify(self.root, False)

    def test_floating_source_cannot_replace_pin(self):
        self.doc["sources"][0]["commit"] = "main"
        self.reseal()
        with self.assertRaisesRegex(ValueError, "immutable"):
            module.verify(self.root, False)

    def test_source_instance_parameter_mutation_fails(self):
        self.doc["sources"][0]["parameters"]["ring_size"] = 9
        self.reseal()
        with self.assertRaisesRegex(ValueError, "Resolved source"):
            module.verify(self.root, False)

    def test_physical_quantity_cannot_be_fractional_piece(self):
        self.doc["bom"][0]["quantity"] = 1.5
        self.reseal()
        with self.assertRaisesRegex(ValueError, "quantity unit"):
            module.verify(self.root, False)

    def test_no_path_escape(self):
        self.doc["artifacts"][0]["path"] = "../outside.txt"
        self.reseal()
        with self.assertRaisesRegex(ValueError, "escapes"):
            module.verify(self.root, False)

    def test_stale_archive_is_rejected(self):
        with zipfile.ZipFile(self.root / "design-bundle.zip", "a") as bundle:
            bundle.writestr("undeclared.txt", "not in the declared design")
        with self.assertRaisesRegex(ValueError, "exactly the declared"):
            module.verify(self.root)

    def test_unknown_profile_is_not_guessed(self):
        self.doc["version"] = "future"
        self.reseal()
        with self.assertRaisesRegex(ValueError, "Unsupported instance"):
            module.verify(self.root, False)


if __name__ == "__main__":
    unittest.main()
