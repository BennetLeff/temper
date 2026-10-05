"""Separate dry prototype: positive bolted catch brackets; no structural qualification."""

from __future__ import annotations

import hashlib
import json
from math import cos, pi, sin, sqrt

import cadquery as cq
import check_capture as base

ANGLES = (60, 180, 300)
AXIS = 7.1


def cylinder(radius: float, z: float, height: float, x: float = 0.0) -> cq.Shape:
    return cq.Solid.makeCylinder(radius, height, cq.Vector(x, 0, z))


def hexagon(across_flats: float, z: float, height: float, x: float) -> cq.Shape:
    return (
        cq.Workplane("XY")
        .workplane(offset=z)
        .center(x, 0)
        .polygon(6, across_flats * 2 / sqrt(3))
        .extrude(height)
        .val()
    )


def modified(common: float, local: float, lift: float, tall_passage: bool = True) -> list:
    parts, _ = base.r7.make(base.r7.VARIANTS[0], common, local, lift)
    frame = base.part(parts, "main_carrier_and_stem")
    original_fingers = [p for p in parts if p.name.startswith("ceramic_upper_capture_finger_")]
    carrier = frame.shape.translate((0, 0, common))
    for angle in ANGLES:
        holes = cylinder(0.9, -9.1, 1.6, AXIS)
        holes = holes.fuse(base.r7.b.box(1.8, 3.6, 0.4, (4.9, 0, -7.8)))
        if tall_passage:
            holes = holes.fuse(base.r7.b.box(1.2, 1.0, 2.1, (5.0, 0, -6.55)))
        carrier = carrier.cut(base.r7.b.rotate(holes, angle))
    result = [p for p in parts if p is not frame and p not in original_fingers]
    result.append(base.r7.b.Part(frame.name, carrier.translate((0, 0, -common)), "frame", False))
    for i, angle in enumerate(ANGLES, 1):
        finger = base.part(parts, f"ceramic_upper_capture_finger_{i}")
        foot = base.r7.b.box(4.75, 3.4, 0.3, (6.425, 0, -7.85)).cut(cylinder(0.9, -8.1, 0.5, AXIS))
        bracket = finger.shape.fuse(
            base.r7.b.rotate(foot, angle).translate((0, 0, -common))
        ).clean()
        bolt = cylinder(1.5, -7.7, 1.6, AXIS).fuse(cylinder(0.8, -11.7, 4.0, AXIS))
        bolt = bolt.cut(hexagon(1.5, -6.8, 0.8, AXIS))
        nut = hexagon(3.2, -10.3, 1.3, AXIS).cut(cylinder(0.8, -10.4, 1.5, AXIS))
        result.append(base.r7.b.Part(f"C9_316L_catch_bracket_{i}", bracket, "frame", False))
        result.append(
            base.r7.b.Part(
                f"C9_A4_M1p6x4_screw_THREAD_ENVELOPE_{i}",
                base.r7.b.rotate(bolt, angle).translate((0, 0, -common)),
                "frame",
                False,
            )
        )
        result.append(
            base.r7.b.Part(
                f"C9_A4_M1p6_nut_THREAD_ENVELOPE_{i}",
                base.r7.b.rotate(nut, angle).translate((0, 0, -common)),
                "frame",
                False,
            )
        )
    return result


def chain(parts: list) -> dict:
    island = base.part(parts, "ceramic_island")
    frame = base.part(parts, "main_carrier_and_stem")
    result = {"island_to_bracket": [], "bracket_to_head": [], "nut_to_carrier": []}
    for i in range(1, 4):
        bracket = base.part(parts, f"C9_316L_catch_bracket_{i}")
        screw = base.part(parts, f"C9_A4_M1p6x4_screw_THREAD_ENVELOPE_{i}")
        nut = base.part(parts, f"C9_A4_M1p6_nut_THREAD_ENVELOPE_{i}")
        for key, a, b in (
            ("island_to_bracket", island, bracket),
            ("bracket_to_head", bracket, screw),
            ("nut_to_carrier", nut, frame),
        ):
            result[key].extend(
                {"joint": i, **row} for row in base.horizontal_contacts(a.shape, b.shape)
            )
    return result


def valid_chain(contacts: dict, engaged: bool) -> bool:
    targets = {
        "island_to_bracket": 0.59465863795558 if engaged else 0.0,
        "bracket_to_head": pi * (1.5**2 - 0.9**2),
        "nut_to_carrier": sqrt(3) * 3.2**2 / 2 - pi * 0.9**2,
    }
    return all(
        abs(sum(row["area_mm2"] for row in contacts[key] if row["joint"] == i) - area) < 1e-6
        for key, area in targets.items()
        for i in range(1, 4)
    )


def export(parts: list, label: str) -> dict:
    filename = base.OUT / f"C9-BOLTED-M222-control-{label}.step"
    assembly = cq.Assembly(name=f"C9-BOLTED-{label}")
    for p in parts:
        assembly.add(p.shape, name=p.name)
    assembly.save(str(filename))
    filename.write_text(
        "\n".join(line.rstrip() for line in filename.read_text().splitlines()) + "\n"
    )
    solids = cq.importers.importStep(str(filename)).solids().vals()
    if (
        not all(s.isValid() for s in solids)
        or abs(sum(s.Volume() for s in solids) - sum(p.shape.Volume() for p in parts)) > 1e-4
    ):
        raise RuntimeError("Candidate STEP volume/validity failure")
    restored = []
    for p in parts:
        if p.name.startswith(
            (
                "C9_",
                "ceramic_island",
                "main_carrier",
                "cap_316L",
                "fixed_carrier_housing",
                "outer_ceramic_blade_clamp",
                "X750_blade_",
            )
        ):
            matches = [
                s
                for s in solids
                if abs(s.Volume() - p.shape.Volume()) < 1e-5
                and all(
                    abs(a - b) < 1e-5 for a, b in zip(base.bbox(s), base.bbox(p.shape), strict=True)
                )
            ]
            if len(matches) != 1:
                raise RuntimeError(f"STEP candidate mapping failed: {p.name}")
            restored.append(base.r7.b.Part(p.name, matches[0], p.group, False))
    return {
        "step": filename.name,
        "sha256": hashlib.sha256(filename.read_bytes()).hexdigest(),
        "valid_reimport": True,
        "actual_step_chain": chain(restored),
        "actual_step_retained_chain": base.contacts(restored),
    }


def main() -> None:
    (base.OUT / "bolted-candidate-checks.json").unlink(missing_ok=True)
    rows = []
    failures = []
    for label, common, local, lift in (
        ("rest", 0, 0, 0),
        ("combined", 0, -0.1, 0.2),
        ("housing-capture", -0.4, -0.1, 0.2),
    ):
        parts = modified(common, local, lift)
        checks = base.census(parts)
        contacts = chain(parts)
        retained = base.contacts(parts)
        retained_counts = {
            "cap_to_island": 0 if label == "rest" else 3,
            "carrier_to_housing": 3 if label == "housing-capture" else 0,
            "carrier_to_outer_blade_pad": 3,
            "outer_blade_pad_to_clamp": 3,
        }
        if (
            not checks["valid_breps"]
            or checks["unexpected_intersections"]
            or checks["missing_electrical_joins"]
            or not valid_chain(contacts, label != "rest")
        ):
            failures.append({"pose": label, "checks": checks, "chain": contacts})
        exported = export(parts, label)
        if not valid_chain(exported["actual_step_chain"], label != "rest"):
            failures.append({"pose": label, "step_chain": exported["actual_step_chain"]})
        for retained_chain in (retained, exported["actual_step_retained_chain"]):
            if any(len(retained_chain[key]) != count for key, count in retained_counts.items()):
                failures.append({"pose": label, "retained_chain": retained_chain})
        rows.append(
            {
                "pose": label,
                "checks": checks,
                "chain": contacts,
                "retained_chain": retained,
                "export": exported,
            }
        )
        print(
            label,
            len(checks["unexpected_intersections"]),
            {k: len(v) for k, v in contacts.items()},
            flush=True,
        )
    # Assembly before fixed housing/glass; each bracket slides radially inward.
    parts = modified(0, 0, 0)
    fixtures = [
        p
        for p in parts
        if p.name
        not in {
            "glass_4mm_hole18_ENVELOPE",
            "fixed_carrier_housing",
            "Kalrez6375_CUSTOM_rolling_membrane_ENVELOPE",
            "Kalrez6375_CUSTOM_static_face_gasket_ENVELOPE",
        }
        and not p.name.startswith("C9_")
    ]
    insertion = []
    for i, angle in enumerate(ANGLES, 1):
        bracket = base.part(parts, f"C9_316L_catch_bracket_{i}")
        other_brackets = [
            p for p in parts if p.name.startswith("C9_316L_catch_bracket_") and p is not bracket
        ]
        for offset in (4.0, 3.0, 2.0, 1.0, 0.5, 0.0):
            shifted = bracket.shape.translate(
                (offset * cos(angle * pi / 180), offset * sin(angle * pi / 180), 0)
            )
            hits = [
                {"part": p.name, "volume_mm3": v}
                for p in fixtures + other_brackets
                if (v := base.solid_overlap(shifted, p.shape)) > 1e-6
            ]
            insertion.append({"bracket": i, "radial_offset_mm": offset, "hits": hits})
            if hits:
                failures.append({"insertion": insertion[-1]})
    shallow = modified(0, 0, 0, tall_passage=False)
    finger = base.part(shallow, "C9_316L_catch_bracket_2").shape.translate((-1, 0, 0))
    shallow_collision = base.solid_overlap(finger, base.part(shallow, "main_carrier").shape)
    if shallow_collision <= 1e-6:
        failures.append({"shallow_passage_counterexample_missing": shallow_collision})
    body = base.part(parts, "fixed_carrier_housing")
    internal = [
        p
        for p in parts
        if p.name
        not in {
            "fixed_carrier_housing",
            "glass_4mm_hole18_ENVELOPE",
            "Kalrez6375_CUSTOM_rolling_membrane_ENVELOPE",
            "Kalrez6375_CUSTOM_static_face_gasket_ENVELOPE",
        }
    ]
    housing_assembly = []
    for up in (30.0, 20.0, 10.0, 5.0, 2.0, 0.0):
        moved = body.shape.translate((0, 0, up))
        hits = [
            {"part": p.name, "volume_mm3": v}
            for p in internal
            if (v := base.solid_overlap(moved, p.shape)) > 1e-6
        ]
        housing_assembly.append({"housing_up_mm": up, "hits": hits})
        if hits:
            failures.append({"housing_insertion": housing_assembly[-1]})
    payload = {
        "status": "PASS_NOMINAL_BOLTED_CANDIDATE" if not failures else "CANDIDATE_BLOCKED",
        "physical_result": "NOT_RUN",
        "source_sha256": base.PINS,
        "geometry": {
            "bolt_axis_radius_mm": AXIS,
            "clearance_hole_diameter_mm": 1.8,
            "foot_radial_extent_mm": [4.05, 8.8],
            "foot_width_mm": 3.4,
            "foot_thickness_mm": 0.3,
            "thread_nominal_mm": 1.6,
            "thread_pitch_mm": 0.35,
            "nominal_nut_engagement_mm": 1.3,
        },
        "thread_interface": "Screw and nut are matching M1.6x0.35 nominal supplier envelopes. Helical thread flanks, clearance class, preload, locking and hot strength are NOT modeled or qualified. Head/foot and nut/carrier bearing faces are explicitly checked.",
        "material": "Three 316L brackets plus natural A4 screw/nut reference envelopes. Carrier material and machining process remain undefined. Exact candidate thermal/EM response is NOT inherited from R7.",
        "states": rows,
        "bracket_insertion_before_housing": insertion,
        "shallow_passage_collision_mm3": shallow_collision,
        "housing_lowering_after_brackets": housing_assembly,
        "failures": failures,
        "scope": "Three operating/catch poses and discrete assembly path samples only; no continuous swept-volume, tool-access, tolerance, strength, torque, hot preload, vibration or lifecycle proof.",
    }
    (base.OUT / "bolted-candidate-checks.json").write_text(json.dumps(payload, indent=2) + "\n")
    if failures:
        raise RuntimeError(f"Candidate blocked: {failures}")


if __name__ == "__main__":
    main()
