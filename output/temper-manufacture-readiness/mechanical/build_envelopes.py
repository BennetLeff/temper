"""Adapt saved R4 STEP parts into explicitly incomplete packaging studies.

No product CAD is regenerated or modified. Dimensional study inputs are JSON;
OpenCascade supplies solid intersections and STEP export/reimport validation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
R4 = HERE.parents[1] / "temper-flush-front-r4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    data = json.loads((HERE / "envelopes.json").read_text())
    if digest(R4 / "STEP/assembly.step") != data["r4_assembly_sha256"]:
        raise ValueError("R4 assembly drift: review inputs before rerunning")
    inventory_path = HERE.parent / "pcb/native18-geometry.json"
    inventory = json.loads(inventory_path.read_text())
    if inventory["board_sha256"] != data["native18_board_sha256"]:
        raise ValueError("PCB identity differs from the study")
    for case in data["cases"]:
        for entry in case["boxes"]:
            if entry["name"] == "native18_BARE_OUTLINE_ONLY":
                if entry["size"][2] != inventory["kicad_board_thickness_mm"]:
                    raise ValueError("PCB thickness differs from the inventory")
    catalog = json.loads((R4 / "catalog.json").read_text())
    excluded = tuple(data["omitted_r4_name_prefixes"])
    context = []
    hashes = {}
    for entry in catalog:
        if entry["name"].startswith(excluded):
            continue
        path = R4 / entry["file"]
        if not path.is_file():
            raise FileNotFoundError(path)
        shape = cq.importers.importStep(str(path)).val()
        if not shape.isValid():
            raise ValueError(f"Invalid R4 part: {entry['name']}")
        context.append((entry["name"], shape))
        hashes[entry["file"]] = digest(path)
    report = {"status": data["status"], "cadquery": cq.__version__,
              "inputs": {"envelopes.json": digest(HERE / "envelopes.json"),
                         "catalog.json": digest(R4 / "catalog.json"),
                         "build_envelopes.py": digest(Path(__file__)),
                         "../pcb/native18-geometry.json": digest(inventory_path),
                         "r4_parts": hashes}, "cases": []}
    for case in data["cases"]:
        assembly = cq.Assembly(name=case["id"])
        for name, shape in context:
            assembly.add(shape, name=name, color=cq.Color(.65, .68, .7, .25))
        hits = []
        study_shapes = []
        for entry in case["boxes"]:
            shape = cq.Solid.makeBox(*entry["size"], cq.Vector(*entry["min"]))
            assembly.add(shape, name=entry["name"], color=cq.Color(.85, .42, .16, .7))
            study_shapes.append((entry["name"], shape))
            for name, fixed in context:
                a, b = shape.BoundingBox(), fixed.BoundingBox()
                if any(getattr(a, axis + "max") <= getattr(b, axis + "min") or
                       getattr(b, axis + "max") <= getattr(a, axis + "min")
                       for axis in ("x", "y", "z")):
                    continue
                volume = shape.intersect(fixed).Volume()
                if volume > 1e-5:
                    hits.append({"study_part": entry["name"], "r4_part": name,
                                 "intersection_mm3": round(volume, 6)})
        pair_hits = []
        for i, (name, shape) in enumerate(study_shapes):
            for other_name, other in study_shapes[i + 1:]:
                volume = shape.intersect(other).Volume()
                if volume > 1e-5:
                    pair_hits.append({"a": name, "b": other_name,
                                      "intersection_mm3": round(volume, 6)})
        path = HERE / (case["id"] + ".step")
        assembly.export(str(path))
        imported = cq.importers.importStep(str(path)).val()
        if not imported.isValid():
            raise ValueError(f"Invalid STEP roundtrip: {path.name}")
        result = {"id": case["id"], "file": path.name, "sha256": digest(path),
                  "valid_reimport": True, "solids": len(imported.Solids()),
                  "context_parts": len(context), "study_envelopes": len(case["boxes"]),
                  "hits_against_included_r4_parts": hits,
                  "study_to_study_hits": pair_hits,
                  "limits": "Only envelope-to-included-R4 volume collisions; no safety clearance, population, mounts, thermal path, wire or duct proof."}
        report["cases"].append(result)
        print(case["id"], len(hits), "envelope-to-context intersections", flush=True)
    (HERE / "checks.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
