#!/usr/bin/env python3
"""Verify jewelry-studio's experimental instance bundle without executing source code.

This is a local-draft adapter for madfam.jewellery-instance 0.1.0-draft, not a keystone standard.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import zipfile
from pathlib import Path, PurePosixPath


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def verify_insertion_report(report, reserved_mm, overrun_mm):
    """Check stored probe/readout parity; this does not execute OCCT."""
    require(
        report.get("profile") == "local-aglet-axis-probe-0.1",
        "Unsupported insertion probe",
    )
    fields = (
        "bore_stop_depth_mm",
        "external_length_mm",
        "guide_reserved_per_end_mm",
        "guide_overrun_per_end_mm",
    )
    require(
        all(
            isinstance(report.get(k), (int, float))
            and not isinstance(report[k], bool)
            and math.isfinite(report[k])
            for k in fields
        ),
        "Nonfinite insertion evidence",
    )
    depth = report["bore_stop_depth_mm"]
    require(0 < depth < report["external_length_mm"], "Invalid native axial stop")
    require(report["native_point_queries"] == 50, "Missing native axial probe coverage")
    require(
        report["guide_reserved_per_end_mm"] == reserved_mm,
        "Guide/probe insertion mismatch",
    )
    expected = round(max(0, reserved_mm - depth), 5)
    require(
        abs(report["guide_overrun_per_end_mm"] - expected) < 1e-4
        and abs(overrun_mm - expected) < 1e-4,
        "Insertion overrun/readout mismatch",
    )
    status = (
        "incompatible-insertion" if reserved_mm > depth + 1e-4 else "nominal-axis-fit"
    )
    require(report["status"] == status, "Insertion incompatibility was promoted")


def safe_file(root, name):
    require(isinstance(name, str) and "\\" not in name, "Invalid artifact path")
    path = PurePosixPath(name)
    require(
        not path.is_absolute()
        and bool(path.parts)
        and all(p not in (".", "..") for p in path.parts),
        "Artifact path escapes its instance",
    )
    resolved = root.joinpath(*path.parts).resolve()
    require(
        resolved.is_relative_to(root) and resolved.is_file(),
        "Artifact is absent or escapes its instance",
    )
    return resolved


def verify(directory, archive=True):
    root = Path(directory).resolve()
    doc = json.loads((root / "instance.json").read_text())
    require(
        doc.get("format") == "madfam.jewellery-instance"
        and doc.get("version") == "0.1.0-draft",
        "Unsupported instance profile",
    )
    body = {k: v for k, v in doc.items() if k != "document_digest"}
    require(digest(body) == doc["document_digest"], "Instance document digest mismatch")
    require(
        digest(doc["request"]) == doc["instance_digest"],
        "Source/parameter/adapter identity mismatch",
    )
    require(doc["units"] == "mm", "Unsupported construction units")
    require(
        doc["runtime_closure_verified"] is False
        and doc["manufacturing_qualified"] is False,
        "This draft adapter cannot promote runtime closure or manufacturing qualification",
    )
    family = doc["request"]["family"]
    require(family in ("ring", "braid", "mixed"), "Unsupported family")
    require(len(doc.get("artifacts", [])) > 0, "No artifacts read")
    seen = set()
    for item in doc["artifacts"]:
        name = item["path"]
        require(name not in seen, "Duplicate artifact path")
        seen.add(name)
        content = safe_file(root, name).read_bytes()
        require(
            len(content) == item["bytes"]
            and hashlib.sha256(content).hexdigest() == item["sha256"],
            f"Artifact changed: {name}",
        )
    require(
        json.loads((root / "request.json").read_text()) == doc["request"],
        "Exported request differs from instance",
    )
    require(
        len(doc.get("sources", [])) > 0 or family == "braid",
        "No source references read",
    )
    source_instances = set()
    for source in doc["sources"]:
        require(
            re.fullmatch(
                r"https://github\.com/madfam-org/[a-z0-9-]+", source["repository"]
            ),
            "Explicit canonical repository required",
        )
        require(
            re.fullmatch(r"[a-f0-9]{40}", source["commit"]),
            "Full immutable source commit required",
        )
        require(
            re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", source["path"]),
            "Invalid source object path",
        )
        original = {
            k: source[k] for k in ("repository", "commit", "path", "files", "license")
        }
        require(
            digest(original) == source["source_digest"],
            "Canonical source digest mismatch",
        )
        resolved = {k: v for k, v in source.items() if k != "resolved_instance_digest"}
        require(
            digest(resolved) == source["resolved_instance_digest"],
            "Resolved source/parameters/engine mismatch",
        )
        source_instances.add(source["resolved_instance_digest"])
        repo = source["repository"].rsplit("/", 1)[1]
        require(
            source["commit"] == doc["request"]["pins"][repo],
            "Source differs from requested pin",
        )
        require(
            source["engine"]["commit"]
            == doc["request"]["pins"][source["engine"]["repository"]],
            "Engine differs from requested pin",
        )
        require(
            set(source["files"]) == {"project.json", "main.py"},
            "Incomplete source file coverage",
        )
        for name, expected in source["files"].items():
            require(name in ("project.json", "main.py"), "Unknown source file coverage")
            actual = safe_file(
                root, f"source-reference/{repo}/{source['path']}/{name}"
            ).read_bytes()
            require(
                hashlib.sha256(actual).hexdigest() == expected,
                "Disclosed source bytes differ from lock",
            )
        require(
            f"source-reference/{repo}/LICENSE" in seen,
            "Upstream licence notice is absent",
        )
    bom_ids = set()
    for item in doc["bom"]:
        require(item["id"] not in bom_ids, "Duplicate physical BOM identity")
        bom_ids.add(item["id"])
        require(
            type(item["quantity"]) in (int, float)
            and math.isfinite(item["quantity"])
            and item["quantity"] > 0,
            "Invalid BOM quantity",
        )
        require(
            item["unit"] in ("piece", "mm")
            and (item["unit"] != "piece" or int(item["quantity"]) == item["quantity"]),
            "Invalid physical quantity unit",
        )
        require(
            item["source"] in source_instances
            or (
                family == "braid"
                and item["source"] == "local-experimental-strand-kernel"
            ),
            "BOM source instance is unresolved",
        )
    require(bool(bom_ids), "Empty physical BOM")
    with safe_file(root, "bill-of-materials.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == len(doc["bom"]), "CSV/BOM coverage mismatch")
    for row, item in zip(rows, doc["bom"], strict=True):
        require(
            all(row[k] == str(item[k]) for k in ("id", "source", "unit", "material"))
            and float(row["quantity"]) == item["quantity"],
            "CSV/BOM quantity or identity mismatch",
        )
    counts = {"passed": 0, "unverified": 0, "unsupported": 0}
    for check in doc["checks"]:
        require(
            check["status"] in counts and bool(check.get("scope")),
            "Unscoped or invalid check",
        )
        require(
            type(check["read_count"]) is int and check["read_count"] >= 0,
            "Invalid read-proof count",
        )
        require(
            check["status"] != "passed" or check["read_count"] > 0,
            "Zero reads cannot establish a pass",
        )
        counts[check["status"]] += 1
    require(
        counts["passed"] > 0 and len(doc.get("limits", [])) > 0,
        "Missing evidence or limits",
    )
    metrics = doc["metrics"]
    parameters = doc["request"]["parameters"]

    def load(name):
        return json.loads(safe_file(root, name).read_text())

    if family == "ring":
        source = next(s for s in doc["sources"] if s["path"] == "jewelry-blank")
        require(
            all(
                source["parameters"][k] == parameters[k]
                for k in ("ring_size", "band_w", "band_t", "profile")
            ),
            "Ring input/source parameter mismatch",
        )
        report = load("solid-report.json")
        require(
            report["brep_valid"]
            and report["bore_verified"]
            and report["mesh_watertight"],
            "Native ring report is not valid",
        )
        require(
            abs(report["requested_bore_mm"] - metrics["inner_diameter_mm"]) < 1e-8,
            "Displayed bore differs from native report",
        )
        require(
            abs(11.63 + 0.8128 * parameters["ring_size"] - metrics["inner_diameter_mm"])
            < 1e-8,
            "Input size differs from evaluated bore",
        )
        require(
            doc["bom"][0]["quantity"] == 1,
            "A one-piece band must remain one physical piece",
        )
    elif family == "braid":
        snapshot = load("snapshot.json")
        require(
            all(
                snapshot["parameters"][k] == parameters[k]
                for k in (
                    "inner_circumference_mm",
                    "gap_deg",
                    "wire_diameter_mm",
                    "finishing_allowance_mm",
                )
            ),
            "Braid input/snapshot parameter mismatch",
        )
        require(
            len(snapshot["paths"]) == 3
            and len(snapshot["crossings"]) == metrics["crossings"],
            "Braid path/crossing count mismatch",
        )
        for path in snapshot["paths"]:
            item = next(x for x in doc["bom"] if x["id"] == path["id"])
            require(
                abs(item["quantity"] - path["cut_length_estimate_mm"]) < 1e-8,
                "Braid cut quantity differs from source snapshot",
            )
        report = load("mesh-report.json")
        require(
            report["bodies_read"]
            == metrics["physical_parts"]
            == (9 if doc["request"]["parameters"]["end_caps"] else 3),
            "Physical body count mismatch",
        )
        require(
            abs(
                snapshot["verification"]["clearance"]["surface_lower_bound_mm"]
                - metrics["clearance_lower_bound_mm"]
            )
            < 1e-8,
            "Clearance readout mismatch",
        )
    else:
        sheet = next(s for s in doc["sources"] if s["path"] == "paper-beads")
        require(
            all(
                sheet["parameters"][k] == parameters[k]
                for k in ("style", "length", "width", "core", "stock")
            ),
            "Sheet input/source parameter mismatch",
        )
        soft = next(s for s in doc["sources"] if s["path"] == "cord-end-notion")
        require(
            all(
                soft["parameters"][k] == parameters[k]
                for k in ("cord_dia", "cord_length")
            ),
            "Cord input/source parameter mismatch",
        )
        cord = load("cord/guide.json")
        require(
            cord["metadata"]["cut_length_mm"] == metrics["source_guide_cut_mm"],
            "Cord guide/readout mismatch",
        )
        require(
            next(x for x in doc["bom"] if x["id"] == "cord")["quantity"]
            == metrics["source_guide_cut_mm"],
            "Cord guide/BOM mismatch",
        )
        require(
            next(x for x in doc["checks"] if x["id"] == "mixed-ASM-1")["status"]
            == "unsupported",
            "Unsupported mixed schema was promoted",
        )
        require(
            next(x for x in doc["checks"] if x["id"] == "cord-tip-length-semantics")[
                "status"
            ]
            == "unverified",
            "Unsolved joining interface was promoted",
        )
        if "tip_insertion_overrun_mm" in metrics:
            verify_insertion_report(
                load("interface-report.json"),
                soft["parameters"]["tip_length"],
                metrics["tip_insertion_overrun_mm"],
            )
    handoff = load("accessory-handoff.json")
    require(
        handoff["instance_digest"] == doc["instance_digest"]
        and handoff["parameters"] == doc["request"]["parameters"],
        "Accessory handoff differs from saved design",
    )
    require(
        handoff["visibility"] == "private"
        and handoff["manufacturing_qualified"] is False,
        "Draft handoff cannot publish or qualify a design",
    )
    if family == "mixed":
        require(
            handoff["transform"] is None
            and handoff["source_frame"] == "unresolved-component-frames",
            "Mixed placement cannot acquire an invented attachment transform",
        )
    archive_entries = 0
    if archive:
        with zipfile.ZipFile(root / "design-bundle.zip") as bundle:
            require(
                len(bundle.namelist()) == len(set(bundle.namelist())),
                "Duplicate ZIP entries",
            )
            require(
                set(bundle.namelist()) == seen | {"instance.json"},
                "ZIP does not contain exactly the declared design and source files",
            )
            for name in bundle.namelist():
                require(
                    bundle.read(name) == safe_file(root, name).read_bytes(),
                    f"ZIP contains stale bytes: {name}",
                )
            archive_entries = len(bundle.namelist())
    return {
        "status": "passed",
        "scope": "draft bundle integrity and stored-data parity only",
        "family": family,
        "instance_digest": doc["instance_digest"],
        "artifacts_read": len(seen),
        "source_instances_read": len(source_instances),
        "bom_items_read": len(bom_ids),
        "check_records_read": len(doc["checks"]),
        "check_status_counts": counts,
        "archive_entries_read": archive_entries,
        "native_geometry_recomputed": False,
        "browser_exercised": False,
        "manufacturing_qualified": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--no-archive", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.directory, not args.no_archive), indent=2))
    except (ValueError, KeyError, OSError, StopIteration, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}))
        raise SystemExit(1) from error
