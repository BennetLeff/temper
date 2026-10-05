"""Derived R9 nominal capture-path CAD inspection; no new mechanics/strength model."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import cadquery as cq

OUT = Path(__file__).resolve().parent
STUDY = Path(
    os.environ.get(
        "TEMPER_GLASS_STUDY_ROOT",
        "/Users/bennet/.codex/worktrees/glass-sensor-simulation/temper/packages/temper-thermal/studies/glass_sensor",
    )
)
PINS = {
    "revision7/mechanical/build.py": "1c9451a3af11f7025e4abd8d1f91d9c17d09c9c710d0de2b454e595dca6f2281",
    "revision5/mechanical/build.py": "f4507ebc3f8c7bf82c19c5b38b9099dbd6c7af1d3190635577c72ec466c7feca",
    "revision2/mechanical/build.py": "3057c0ede6adeeed338d0dc554b63100dfe5040e9bef562fb622199807f6499d",
    "revision7/mechanical/thermal_geometry.csv": "72c6da410ee03d91aeee04386fba74b70ce14e504348abbb4515f3b8241a5343",
}
for name, expected in PINS.items():
    if hashlib.sha256((STUDY / name).read_bytes()).hexdigest() != expected:
        raise RuntimeError(f"Inherited source identity mismatch: {name}")
spec = importlib.util.spec_from_file_location(
    "r7_capture_source", STUDY / "revision7/mechanical/build.py"
)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to import R7 CAD")
r7 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = r7
spec.loader.exec_module(r7)


def bbox(shape: cq.Shape) -> list[float]:
    bounds = shape.BoundingBox()
    return [bounds.xmin, bounds.xmax, bounds.ymin, bounds.ymax, bounds.zmin, bounds.zmax]


def solid_overlap(a: cq.Shape, b: cq.Shape) -> float:
    aa, bb = bbox(a), bbox(b)
    if any(min(aa[i + 1], bb[i + 1]) - max(aa[i], bb[i]) <= 1e-8 for i in (0, 2, 4)):
        return 0.0
    return a.intersect(b).Volume()


def census(parts: list) -> dict:
    """All rigid and wire/witness interactions; declared join overlaps stay explicit."""
    omitted = {
        "Kalrez6375_CUSTOM_rolling_membrane_ENVELOPE",
        "Kalrez6375_CUSTOM_static_face_gasket_ENVELOPE",
    }
    checks = [p for p in parts if p.name not in omitted]
    hits = []
    expected_joins = []
    for index, a in enumerate(checks):
        for b in checks[index + 1 :]:
            volume = solid_overlap(a.shape, b.shape)
            if volume <= 1e-6:
                continue
            names = (a.name, b.name)
            bead = next((name for name in names if name.startswith("Cu_Ni_WELD_BEAD_")), None)
            native = next((name for name in names if name.startswith("native_Ni_installed_")), None)
            wire = next((name for name in names if name.startswith("PFA_route_")), None)
            chip = any(name.startswith("RTD_package_") for name in names)
            allowed = False
            if bead and wire:
                allowed = int(bead.split("_")[4]) == int(wire.split("_")[2])
            if bead and native:
                allowed = int(bead.split("_")[4]) // 2 == int(native.split("_")[-1])
            if native and chip:
                allowed = True
            if all(name.startswith("Cu_Ni_WELD_BEAD_") for name in names):
                allowed = int(names[0].split("_")[4]) // 2 == int(names[1].split("_")[4]) // 2
            row = {"a": a.name, "b": b.name, "overlap_mm3": volume}
            (expected_joins if allowed else hits).append(row)
    connected = {
        (row["a"], row["b"])
        for row in expected_joins
        if "Cu_Ni_WELD_BEAD_" in row["a"] or "Cu_Ni_WELD_BEAD_" in row["b"]
    }
    missing = []
    for i in range(4):
        bead = part(parts, f"Cu_Ni_WELD_BEAD_{i}_").name
        for other in (
            part(parts, f"PFA_route_{i}_").name,
            part(parts, f"native_Ni_installed_{i // 2}").name,
        ):
            if (bead, other) not in connected and (other, bead) not in connected:
                missing.append([bead, other])
    return {
        "valid_breps": all(p.shape.isValid() for p in parts),
        "unexpected_intersections": hits,
        "missing_electrical_joins": missing,
        "declared_join_intersections": expected_joins,
        "excluded_flexible_seal_envelopes": sorted(omitted),
    }


def horizontal_contacts(a: cq.Shape, b: cq.Shape) -> list[dict]:
    contacts = []
    for fa in a.Faces():
        if fa.geomType() != "PLANE" or fa.normalAt().z < 0.99:
            continue
        ba = bbox(fa)
        if ba[5] - ba[4] > 1e-6:
            continue
        for fb in b.Faces():
            if fb.geomType() != "PLANE" or fb.normalAt().z > -0.99:
                continue
            bb = bbox(fb)
            if bb[5] - bb[4] > 1e-6 or abs((ba[4] + ba[5]) - (bb[4] + bb[5])) > 2e-6:
                continue
            if any(min(ba[i + 1], bb[i + 1]) <= max(ba[i], bb[i]) + 1e-8 for i in (0, 2)):
                continue
            common = fa.intersect(fb)
            area = common.Area()
            if area > 1e-7:
                c = common.Center()
                contacts.append(
                    {"area_mm2": area, "centroid_mm": [c.x, c.y, c.z], "bounds_mm": bbox(common)}
                )
    return contacts


def part(parts: list, prefix: str):
    matches = [p for p in parts if p.name.startswith(prefix)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected unique part {prefix}: {len(matches)}")
    return matches[0]


def contacts(parts: list) -> dict:
    cap = part(parts, "cap_316L")
    island = part(parts, "ceramic_island")
    housing = part(parts, "fixed_carrier_housing")
    carrier = part(parts, "main_carrier_and_stem")
    stages = {
        "cap_to_island": horizontal_contacts(cap.shape, island.shape),
        "island_to_carrier": [],
        "carrier_to_housing": [],
        "carrier_to_outer_blade_pad": [],
        "outer_blade_pad_to_clamp": [],
    }
    for p in parts:
        if p.name.startswith("ceramic_upper_capture_finger"):
            for row in horizontal_contacts(island.shape, p.shape):
                stages["island_to_carrier"].append({"receiver": p.name, **row})
        if p.name.startswith("outer_ceramic_blade_clamp"):
            for row in horizontal_contacts(p.shape, housing.shape):
                stages["carrier_to_housing"].append({"transmitter": p.name, **row})
            blade = part(parts, f"X750_blade_{p.name.split('_')[-1]}_")
            for row in horizontal_contacts(carrier.shape, blade.shape):
                stages["carrier_to_outer_blade_pad"].append({"receiver": blade.name, **row})
            for row in horizontal_contacts(blade.shape, p.shape):
                stages["outer_blade_pad_to_clamp"].append({"receiver": p.name, **row})
    return stages


def export_endpoint(parts: list, name: str) -> dict:
    path = OUT / f"{name}.step"
    cq.exporters.export(cq.Compound.makeCompound([p.shape for p in parts]), str(path))
    path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    solids = cq.importers.importStep(str(path)).solids().vals()
    if not solids or not all(s.isValid() for s in solids):
        raise RuntimeError(f"Invalid STEP reimport {path.name}")
    volume = sum(s.Volume() for s in solids)
    source_volume = sum(p.shape.Volume() for p in parts)
    if abs(volume - source_volume) > 1e-4:
        raise RuntimeError(f"STEP volume discrepancy {path.name}")
    restored = []
    # Critical contact parts are each single solids; match actual exported B-reps.
    for p in parts:
        if p.name.startswith(
            (
                "cap_316L",
                "ceramic_island",
                "fixed_carrier_housing",
                "ceramic_upper_capture_finger",
                "outer_ceramic_blade_clamp",
                "main_carrier_and_stem",
                "X750_blade_",
            )
        ):
            matches = [
                s
                for s in solids
                if abs(s.Volume() - p.shape.Volume()) < 1e-5
                and all(abs(a - b) < 1e-5 for a, b in zip(bbox(s), bbox(p.shape), strict=True))
            ]
            if len(matches) != 1:
                raise RuntimeError(f"Exported part mapping ambiguous: {p.name}")
            restored.append(r7.b.Part(p.name, matches[0], p.group, p.envelope))
    return {
        "step": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "valid": True,
        "source_volume_mm3": source_volume,
        "reimport_volume_mm3": volume,
        "actual_step_contacts": contacts(restored),
    }


def main() -> None:
    results = []
    failures = []
    # Sequential cap take-up, then local island take-up, carrier held fixed.
    poses = [(f"cap_{i:02d}", 0.0, 0.0, i * 0.1) for i in range(3)]
    poses += [(f"island_{i:02d}", 0.0, -i * 0.05, 0.2) for i in range(1, 3)]
    # Further common take-up is a separate geometric load-path investigation.
    poses += [(f"carrier_{i:02d}", -i * 0.2, -0.1, 0.2) for i in range(1, 3)]
    for variant in r7.VARIANTS:
        for pose, common, local, lift in poses:
            parts, routes = r7.make(variant, common, local, lift)
            state = census(parts)
            state.update(
                variant=variant.name,
                pose=pose,
                common_down_mm=common,
                local_down_mm=local,
                cap_lift_mm=lift,
                cap_up_absolute_mm=-common - local + lift,
                island_up_absolute_mm=-common - local,
                carrier_up_absolute_mm=-common,
                contacts=contacts(parts),
                routes=routes,
            )
            if (
                not state["valid_breps"]
                or state["unexpected_intersections"]
                or state["missing_electrical_joins"]
            ):
                failures.append(
                    {
                        "variant": variant.name,
                        "pose": pose,
                        "hits": state["unexpected_intersections"],
                        "missing_joins": state["missing_electrical_joins"],
                    }
                )
            expected_counts = {
                "cap_to_island": 3 if lift >= 0.2 else 0,
                "island_to_carrier": 3 if local <= -0.1 else 0,
                "carrier_to_housing": 3 if common <= -0.4 else 0,
                "carrier_to_outer_blade_pad": 3,
                "outer_blade_pad_to_clamp": 3,
            }
            for stage, count in expected_counts.items():
                if len(state["contacts"][stage]) != count:
                    failures.append(
                        {
                            "variant": variant.name,
                            "pose": pose,
                            "contact_count": stage,
                            "expected": count,
                            "actual": len(state["contacts"][stage]),
                        }
                    )
            if pose in ("island_02", "carrier_02"):
                state["export"] = export_endpoint(parts, f"R9-{variant.name}-{pose}")
                for stage, count in expected_counts.items():
                    if len(state["export"]["actual_step_contacts"][stage]) != count:
                        failures.append(
                            {"variant": variant.name, "pose": pose, "step_contact_count": stage}
                        )
            results.append(state)
            print(variant.name, pose, len(state["unexpected_intersections"]), flush=True)
    # Positive overlap after overtravel must be detected, not accepted as more range.
    negatives = []
    for stage, common, local, lift, pair in [
        ("cap_overtravel", 0.0, 0.0, 0.21, ("cap_316L", "ceramic_island")),
        (
            "island_overtravel",
            0.0,
            -0.11,
            0.2,
            ("ceramic_island", "ceramic_upper_capture_finger_1"),
        ),
        (
            "carrier_overtravel",
            -0.41,
            -0.1,
            0.2,
            ("outer_ceramic_blade_clamp_1", "fixed_carrier_housing"),
        ),
    ]:
        parts, _ = r7.make(r7.VARIANTS[0], common, local, lift)
        overlap = solid_overlap(part(parts, pair[0]).shape, part(parts, pair[1]).shape)
        negatives.append(
            {"case": stage, "pair": pair, "overlap_mm3": overlap, "detected": overlap > 1e-6}
        )
        if overlap <= 1e-6:
            failures.append({"negative_control_failed": stage})
    payload = {
        "status": "PASS_NOMINAL_GEOMETRY" if not failures else "COLLISIONS_OR_CHECK_FAILURES",
        "physical_result": "NOT_RUN",
        "source_root": str(STUDY),
        "source_sha256": PINS,
        "sampled_states": results,
        "negative_controls": negatives,
        "failures": failures,
        "scope": "Axial sequential nominal geometry. No strength, hot-tolerance, lateral escape, fatigue, seal, installed bond qualification or continuous swept-volume proof.",
    }
    (OUT / "capture-checks.json").write_text(json.dumps(payload, indent=2) + "\n")
    for name, expected in PINS.items():
        if hashlib.sha256((STUDY / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Inherited input changed during run: {name}")
    if failures:
        raise RuntimeError(f"Capture path findings: {failures}")


if __name__ == "__main__":
    main()
