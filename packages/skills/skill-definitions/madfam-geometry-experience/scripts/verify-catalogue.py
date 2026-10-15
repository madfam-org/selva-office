"""Read-only integrity audit of a trusted local Jewelry Studio catalogue and its native evidence.

Does not execute generators, authenticate authorship, rerun kernels or certify manufacture.
"""

import argparse
import csv
import hashlib
import json
import re
import zipfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def member(base, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute(), "Unsafe artifact path")
    path = (base / name).resolve()
    require(path.is_relative_to(base.resolve()), "Artifact escapes its bundle")
    return path


def verify_bom_exports(folder, doc, pattern=None):
    """Check serialized quantities against the document and owning pattern data."""
    fields = ["id", "quantity", "unit", "material"]
    declared = {item["path"] for item in doc["artifacts"]}
    require("bill-of-materials.csv" in declared, "BOM CSV is not a declared artifact")
    require(isinstance(doc["bom"], list) and doc["bom"], "Empty document BOM")
    require(all(set(item) == set(fields) for item in doc["bom"]), "Unexpected BOM fields")
    with member(folder, "bill-of-materials.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == fields, "BOM CSV header mismatch")
        rows = list(reader)
    expected = [{key: str(item[key]) for key in fields} for item in doc["bom"]]
    require(rows == expected, "BOM CSV/document parity mismatch")
    if pattern is not None:
        guide = pattern.get("metadata", {}).get("output_role") == "reference-guide"
        material = "reference-print-unassigned" if guide else "textile-unassigned"
        require(
            all(item["material"] == material for item in doc["bom"]),
            "Pattern BOM material/output role drift",
        )
        require("native-bom.json" in declared, "Native BOM is not a declared artifact")
        native_bom = json.loads(member(folder, "native-bom.json").read_text())
        require(native_bom == pattern.get("bom", []), "Native BOM/pattern parity mismatch")


def verify(studio):
    root = Path(studio).resolve()
    catalogue = json.loads((root / "catalogue.json").read_text())
    rows = catalogue["hyperobjects"]
    require(
        len(rows) == 100 and len({r["id"] for r in rows}) == 100,
        "Require exactly 100 unique families",
    )
    require(
        len({(r["repository"], r["slug"]) for r in rows}) == 100,
        "Duplicate source family counted twice",
    )
    evidence = json.loads((root / "evidence/catalogue-100.json").read_text())
    require(
        evidence["catalogue_sha256"] == digest((root / "catalogue.json").read_bytes()),
        "Catalogue evidence is stale",
    )
    adapter_paths = [
        "catalogue.py",
        "catalogue.json",
        "factory.py",
        "native/inspect_catalogue_solid.py",
        "native/inspect_sheet.py",
    ]
    adapter = digest(canonical({p: digest((root / p).read_bytes()) for p in adapter_paths}))
    require(evidence["adapter_sha256"] == adapter, "Adapter evidence is stale")
    proofs = evidence["families"]
    require(
        len(proofs) == 100 and {p["id"] for p in proofs} == {r["id"] for r in rows},
        "Evidence coverage must be exact and nonempty",
    )
    proofs = {p["id"]: p for p in proofs}
    artifacts = 0
    instances = 0
    for row in rows:
        proof = proofs[row["id"]]
        require(
            proof["passed"] and proof["changed_geometry"],
            row["id"] + ": native samples not passed or changed",
        )
        require(
            proof["default"]["instance_digest"] != proof["changed"]["instance_digest"],
            "Identical default and changed instance",
        )
        observed_signatures = []
        defaults = {p["id"]: p["default"] for p in row["controls"]}
        for tag, params in [("default", defaults), ("changed", defaults | row["probe"])]:
            key = proof[tag]["instance_digest"]
            require(re.fullmatch("[a-f0-9]{64}", key), "Invalid instance identity")
            folder = root / "cache" / key
            doc = json.loads((folder / "instance.json").read_text())
            require(doc["format"] == "madfam.jewelry-catalogue-instance", "Wrong instance profile")
            require(
                doc["hyperobject"] == row["id"] and doc["instance_digest"] == key,
                "Wrong hyperobject instance",
            )
            require(doc["request"]["parameters"] == params, "Parameter / evidence drift")
            require(
                doc["request"]["adapter_sha256"] == adapter,
                "Instance adapter differs from the coverage proof",
            )
            require(digest(canonical(doc["request"])) == key, "Request identity mismatch")
            require(
                digest(canonical({k: v for k, v in doc.items() if k != "document_digest"}))
                == doc["document_digest"],
                "Document integrity mismatch",
            )
            require(
                doc["manufacturing_qualified"] is False
                and doc["runtime_closure_verified"] is False,
                "Unsupported qualification claim",
            )
            require(doc["visibility"] == "private", "Unexpected catalogue publication")
            require(len(doc["sources"]) == 1, "This profile requires one canonical family")
            source = doc["sources"][0]
            require(
                source["path"] == row["slug"] and source["commit"] == row["commit"],
                "Source pin drift",
            )
            require(
                source["repository"] == "https://github.com/madfam-org/" + row["repository"],
                "Source owner drift",
            )
            owner = {"solid": "yantra4d", "soft": "fashion-cabinet", "sheet": "pliego"}[row["kind"]]
            require(
                source["engine"]["repository"] == owner
                and re.fullmatch("[a-f0-9]{40}", source["engine"]["commit"]),
                "Owning evaluator pin missing",
            )
            manifest = json.loads(
                member(
                    folder,
                    "source-reference/" + row["repository"] + "/" + row["slug"] + "/project.json",
                ).read_text()
            )
            native_params = (
                {p["id"]: p.get("default") for p in manifest["parameters"]}
                | row.get("fixed", {})
                | params
            )
            require(source["parameters"] == native_params, "Native parameter resolution drift")
            require(
                doc["request"]["source_instance"] == source["resolved_instance_digest"],
                "Request/source identity drift",
            )
            base = {
                k: v
                for k, v in source.items()
                if k not in ("source_digest", "parameters", "engine", "resolved_instance_digest")
            }
            require(digest(canonical(base)) == source["source_digest"], "Source identity mismatch")
            resolved = {k: v for k, v in source.items() if k != "resolved_instance_digest"}
            require(
                digest(canonical(resolved)) == source["resolved_instance_digest"],
                "Resolved source mismatch",
            )
            for name, sha in source["files"].items():
                require(
                    digest(
                        member(
                            folder,
                            "source-reference/"
                            + row["repository"]
                            + "/"
                            + row["slug"]
                            + "/"
                            + name,
                        ).read_bytes()
                    )
                    == sha,
                    "Source disclosure mismatch",
                )
            paths = []
            for item in doc["artifacts"]:
                path = member(folder, item["path"])
                data = path.read_bytes()
                paths.append(item["path"])
                require(
                    len(data) == item["bytes"] and digest(data) == item["sha256"],
                    "Artifact integrity mismatch: " + item["path"],
                )
                artifacts += 1
            require(len(paths) == len(set(paths)), "Duplicate artifact path")
            verify_bom_exports(folder, doc)
            require(
                doc["geometry"]["kind"]
                == {"solid": "stl", "soft": "pattern", "sheet": "glb"}[row["kind"]],
                "Representation mismatch",
            )
            require(proof[tag]["fallback"] == doc["fallback"], "Preview binding mismatch")
            handoff = json.loads((folder / "accessory-handoff.json").read_text())
            require(
                handoff["instance_digest"] == key
                and handoff["visibility"] == "private"
                and handoff["manufacturing_qualified"] is False,
                "Private handoff drift",
            )
            require(
                handoff["parameters"] == params and handoff["sources"] == doc["sources"],
                "Handoff source or parameter drift",
            )
            report = json.loads((folder / "native-report.json").read_text())
            if row["kind"] == "solid":
                require(
                    report["brep_valid"]
                    and report["mesh_watertight"]
                    and report["mesh_winding_consistent"],
                    "Native solid verdict missing",
                )
                require(
                    report["brep_bodies"] == row["bodies"] == report["mesh_bodies"],
                    "Native body count mismatch",
                )
                require(
                    report["volume_mm3"] > 0 and report["triangles_read"] > 0,
                    "Empty native geometry",
                )
                require(
                    doc["metrics"]["volume_mm3"] == report["volume_mm3"]
                    and doc["metrics"]["physical_bodies"] == report["brep_bodies"],
                    "Solid readout drift",
                )
                measured = digest(
                    canonical(
                        {
                            k: report[k]
                            for k in ("volume_mm3", "bounds_mm", "brep_bodies", "triangles_read")
                        }
                    )
                )
            elif row["kind"] == "soft":
                pattern = json.loads((folder / "pattern.json").read_text())
                require(
                    report["pieces_read"] == len(pattern["pieces"]) > 0 and report["errors"] == 0,
                    "Empty or failed pattern",
                )
                require(all(s["ok"] for s in pattern["seams"]), "Failed declared seam")
                guide = pattern.get("metadata", {}).get("output_role") == "reference-guide"
                area_key = "reference_outline_area_mm2" if guide else "seam_line_area_mm2"
                area = sum(
                    p["area_mm2"] * p.get("cut", {}).get("quantity", 1) for p in pattern["pieces"]
                )
                require(
                    doc["metrics"].get(area_key) == area and "cut_area_mm2" not in doc["metrics"],
                    "Pattern area semantics drift",
                )
                require(
                    doc["metrics"]["pattern_pieces"] == len(pattern["pieces"])
                    and doc["metrics"]["declared_seams"] == len(pattern["seams"]),
                    "Pattern count drift",
                )
                require(len(doc["bom"]) == len(pattern["pieces"]), "Pattern BOM scope drift")
                for item, piece in zip(doc["bom"], pattern["pieces"], strict=True):
                    require(
                        item["id"] == piece["name"]
                        and item["quantity"] == piece.get("cut", {}).get("quantity", 1)
                        and item["unit"] == ("reference-guide" if guide else "cut"),
                        "Pattern BOM quantity or output role drift",
                    )
                verify_bom_exports(folder, doc, pattern)
                measured = digest(canonical({k: pattern[k] for k in ("pieces", "seams", "bom")}))
            else:
                require(report["faces_read"] > 0, "Empty sheet verification")
                measured = digest(member(folder, doc["geometry"]["file"]).read_bytes())
            require(
                measured == proof[tag]["native_signature"], "Native evidence signature mismatch"
            )
            observed_signatures.append(measured)
            with zipfile.ZipFile(folder / "design-bundle.zip") as archive:
                names = archive.namelist()
                require(
                    len(names) == len(set(names)) and set(names) == set(paths) | {"instance.json"},
                    "ZIP members differ from disclosed artifacts",
                )
                for name in names:
                    require(
                        archive.read(name) == member(folder, name).read_bytes(), "ZIP byte mismatch"
                    )
            instances += 1
        require(observed_signatures[0] != observed_signatures[1], "No changed native content")
    return {
        "families": 100,
        "native_instances_read": instances,
        "artifact_files_read": artifacts,
        "status": "integrity-passed",
        "scope": (
            "Recorded native evidence and source/export/ZIP parity; no kernel rerun, "
            "authorship authentication, Linux CI or physical qualification"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("studio")
    args = parser.parse_args()
    print(json.dumps(verify(args.studio), indent=2))
