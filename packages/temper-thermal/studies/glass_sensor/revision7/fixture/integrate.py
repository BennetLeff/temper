"""Check actual exported R7 cartridge solids against the actual fixture STEP."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parent
VARIANTS = ("M222_control_010", "M222_thin_0075", "IST308_thin_0075")
POSES = {"rest": 0.0, "loaded": -0.6, "full_stroke": -1.45, "cap_capture": 0.2}
LOADTRAIN = {"cap_force_coupon_D6x3", "thermal_standoff_D4", "force_transducer_ENVELOPE_UNSELECTED"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(shape: cq.Shape) -> list[float]:
    b = shape.BoundingBox()
    return [b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax]


def overlaps_boxes(a: list[float], b: list[float]) -> bool:
    return all(min(a[k + 1], b[k + 1]) > max(a[k], b[k]) for k in [0, 2, 4])


def pairs(left: list[tuple[str, cq.Shape]], right: list[tuple[str, cq.Shape]]) -> dict[str, object]:
    hits = []
    tested = 0
    for a_name, a_shape in left:
        for b_name, b_shape in right:
            if not overlaps_boxes(bounds(a_shape), bounds(b_shape)):
                continue
            tested += 1
            volume = a_shape.intersect(b_shape).Volume()
            if volume > 1e-6:
                hits.append({"left": a_name, "right": b_name, "overlap_mm3": volume})
    return {
        "all_pairs": len(left) * len(right),
        "bbox_overlap_pairs_checked_by_boolean": tested,
        "intersections_above_1e_minus6_mm3": hits,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise ValueError("usage: integrate.py MECHANICAL_DIRECTORY")
    mech = Path(sys.argv[1]).resolve()
    contract = json.loads((ROOT / "geometry.json").read_text())
    cartridge = json.loads((mech / "geometry.json").read_text())
    frame_path = ROOT / "force-displacement-frame.step"
    remaining = list(cq.importers.importStep(str(frame_path)).solids().vals())
    frame: list[tuple[str, cq.Shape]] = []
    for name, data in contract["frame"]["parts"].items():
        matches = [
            i
            for i, shape in enumerate(remaining)
            if abs(shape.Volume() - data["volume_mm3"]) < 1e-5
            and max(abs(a - b) for a, b in zip(bounds(shape), data["bounds_mm"], strict=True))
            < 1e-5
        ]
        if len(matches) != 1:
            raise ValueError(f"Cannot identify actual STEP fixture part {name}: {matches}")
        frame.append((name, remaining.pop(matches[0])))
    if remaining:
        raise ValueError("Unmapped fixture STEP solids")
    fixed = [
        (name, shape)
        for name, shape in frame
        if name not in LOADTRAIN and name != "mock_glass_D50_hole18"
    ]
    loadtrain = [(name, shape) for name, shape in frame if name in LOADTRAIN]
    accessory_path = ROOT / "pan-coupon-accessory.step"
    accessory = cq.importers.importStep(str(accessory_path)).val()
    inputs = {
        "fixture/force-displacement-frame.step": digest(frame_path),
        "fixture/geometry.json": digest(ROOT / "geometry.json"),
        "fixture/pan-coupon-accessory.step": digest(accessory_path),
        "mechanical/geometry.json": digest(mech / "geometry.json"),
    }
    states = []
    failures = []
    for variant in VARIANTS:
        for pose, shift in POSES.items():
            source = mech / f"R7-{variant}-{pose}.step"
            inputs[f"mechanical/{source.name}"] = digest(source)
            solids = cq.importers.importStep(str(source)).solids().vals()
            if not solids or not all(shape.isValid() for shape in solids):
                raise ValueError(f"Invalid actual cartridge STEP: {source}")
            names = [(f"actual_step_solid_{i}", s) for i, s in enumerate(solids)]
            volume_map = cartridge["states"][variant][pose]["volumes_mm3"]
            wire_volumes = [v for name, v in volume_map.items() if name.startswith("PFA_route")]
            wire_solids = [
                (name, s)
                for name, s in names
                if any(abs(s.Volume() - volume) < 1e-5 for volume in wire_volumes)
            ]
            if len(wire_volumes) != 4 or len(wire_solids) != 4:
                raise ValueError(f"Expected four actual complete wire solids: {variant}/{pose}")
            for route in cartridge["states"][variant][pose]["routes"]:
                if abs(route["total_length_mm"] - 60.0) > 1e-5:
                    raise ValueError("Wire route contract is not60mm")
            record: dict[str, object] = {
                "variant": variant,
                "pose": pose,
                "actual_STEP_solids": len(solids),
                "cartridge_bounds_mm": bounds(cq.Compound.makeCompound(solids)),
                "fixed_fixture_all_solids": pairs(names, fixed),
                "wire_bounds_mm": [
                    {"actual_step_id": name, "bounds_mm": bounds(s), "volume_mm3": s.Volume()}
                    for name, s in wire_solids
                ],
                "complete_four_wire_vs_fixed_fixture": pairs(wire_solids, fixed),
            }
            if pose == "cap_capture":
                record["loadtrain"] = {
                    "status": "REMOVED_FOR_RETENTION_POSE",
                    "reason": "Pan/force train is absent during cap-lift retention; no fixed pan clash is hidden as a pass.",
                }
            else:
                positioned = [(name, s.translate((0, 0, shift))) for name, s in loadtrain]
                record["loadtrain"] = {
                    "status": "SEPARATELY_POSITIONED_CAP_FORCE_COUPON",
                    "z_translation_mm": shift,
                    "bounds_mm": {name: bounds(s) for name, s in positioned},
                    "vs_cartridge": pairs(positioned, names),
                    "vs_fixed_fixture": pairs(positioned, fixed),
                    "limitations": "Stage transmission/guide travel and loadcell attachment are unengineered; no actuator kinematic or strength qualification.",
                }
            if pose == "full_stroke":
                glass_volume = volume_map["glass_4mm_hole18_ENVELOPE"]
                glasses = [(name, s) for name, s in names if abs(s.Volume() - glass_volume) < 1e-5]
                if len(glasses) != 1:
                    raise ValueError(
                        "Cannot identify shared glass for negative interference control"
                    )
                control = pairs(
                    [("UNSUITABLE_D36_PAN_FULL_STROKE", accessory.translate((0, 0, shift)))],
                    glasses,
                )
                if not control["intersections_above_1e_minus6_mm3"]:
                    raise ValueError("Negative control failed to detect large pan/glass clash")
                record["negative_large_pan_control"] = control
            checks = [
                record["fixed_fixture_all_solids"],
                record["complete_four_wire_vs_fixed_fixture"],
            ]
            if pose != "cap_capture":
                checks.extend(
                    [record["loadtrain"]["vs_cartridge"], record["loadtrain"]["vs_fixed_fixture"]]
                )
            for check in checks:
                if check["intersections_above_1e_minus6_mm3"]:
                    failures.append({"variant": variant, "pose": pose, "check": check})
            states.append(record)
            print(variant, pose, "CHECKED", flush=True)
    report = {
        "status": "NOMINAL_GEOMETRY_CLEAR" if not failures else "COLLISIONS_FOUND",
        "physical_result": "NOT_RUN",
        "method": "Imported actual STEP solids; matched fixture part labels by unique volume+bbox against export metadata. Checked every cartridge solid, including fixed parts, moving parts and all four full60mm wire solids; bounding-box rejection then solid Boolean volume. No regenerated cartridge geometry used.",
        "inputs_sha256": inputs,
        "excluded_fixture_parts": {
            "mock_glass_D50_hole18": "Same physical mock glass is already included in each cartridge STEP; duplicate fixture glass excluded. Cartridge glass remains checked against every fixed fixture component and positioned load train.",
            "three_loadtrain_parts": "Handled separately at measured cap surface offsets; absent for retention pose.",
        },
        "housing_clamp_interface": "Not excluded from collision checks: uncompressed28.2mm bore around28mm housing is clear. Actual tightening/deformation/fasteners are unengineered and not proven by this clearance.",
        "optical_access": "UNVERIFIED: no optical instruments/ray paths/targets integrated",
        "frames_checked": states,
        "failures": failures,
    }
    for label, expected_hash in inputs.items():
        base, filename = label.split("/", 1)
        path = (ROOT if base == "fixture" else mech) / filename
        if digest(path) != expected_hash:
            raise ValueError(f"Input changed during integration: {path}")
    (ROOT / "integration.json").write_text(json.dumps(report, indent=2) + "\n")
    if failures:
        raise ValueError(f"Fixture integration has collisions: {failures}")


if __name__ == "__main__":
    main()
