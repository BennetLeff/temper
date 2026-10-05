"""Conservative screw/nut insertion envelopes before housing installation."""

from __future__ import annotations

import json
from math import cos, pi, sin, sqrt

import bolted_candidate as candidate
import check_capture as base


def main() -> None:
    parts = candidate.modified(0, 0, 0)
    excluded = {
        "fixed_carrier_housing",
        "glass_4mm_hole18_ENVELOPE",
        "Kalrez6375_CUSTOM_rolling_membrane_ENVELOPE",
        "Kalrez6375_CUSTOM_static_face_gasket_ENVELOPE",
    }
    rows = []
    for i, angle in enumerate(candidate.ANGLES, 1):
        # Head and shaft volumes swept along a straight 8 mm approach.
        screw_sweep = candidate.cylinder(1.5, -7.7, 9.6, candidate.AXIS).fuse(
            candidate.cylinder(0.8, -11.7, 12.0, candidate.AXIS)
        )
        # Circumscribed rotating nut swept 4 mm upward; threaded engagement remains nominal.
        nut_sweep = candidate.cylinder(3.2 / sqrt(3), -14.3, 5.3, candidate.AXIS).cut(
            candidate.cylinder(0.8, -14.4, 5.5, candidate.AXIS)
        )
        key_shaft = candidate.hexagon(1.5, -6.8, 10.0, candidate.AXIS)
        for label, shape in (
            ("screw_8mm_approach", screw_sweep),
            ("nut_rotation_and_4mm_approach", nut_sweep),
            ("minimum_1p5AF_key_shaft", key_shaft),
        ):
            moved = base.r7.b.rotate(shape, angle)
            fixtures = [p for p in parts if p.name not in excluded]
            if label == "screw_8mm_approach":
                fixtures = [
                    p
                    for p in fixtures
                    if not p.name.startswith("C9_A4_M1p6_nut_")
                    and p.name != f"C9_A4_M1p6x4_screw_THREAD_ENVELOPE_{i}"
                ]
            elif label == "nut_rotation_and_4mm_approach":
                fixtures = [p for p in fixtures if p.name != f"C9_A4_M1p6_nut_THREAD_ENVELOPE_{i}"]
            else:
                fixtures = [
                    p for p in fixtures if p.name != f"C9_A4_M1p6x4_screw_THREAD_ENVELOPE_{i}"
                ]
            hits = [
                {"part": p.name, "volume_mm3": volume}
                for p in fixtures
                if (volume := base.solid_overlap(moved, p.shape)) > 1e-6
            ]
            rows.append({"joint": i, "check": label, "hits": hits})
    sequential = []
    for i, angle in enumerate(candidate.ANGLES, 1):
        own = {
            f"C9_316L_catch_bracket_{i}",
            f"C9_A4_M1p6x4_screw_THREAD_ENVELOPE_{i}",
            f"C9_A4_M1p6_nut_THREAD_ENVELOPE_{i}",
        }
        bracket = base.part(parts, f"C9_316L_catch_bracket_{i}")
        counterparts = [p for p in parts if p.name not in excluded | own]
        for offset in (4.0, 3.0, 2.0, 1.0, 0.5, 0.0):
            moved = bracket.shape.translate(
                (offset * cos(angle * pi / 180), offset * sin(angle * pi / 180), 0)
            )
            hits = [
                {"part": p.name, "volume_mm3": volume}
                for p in counterparts
                if (volume := base.solid_overlap(moved, p.shape)) > 1e-6
            ]
            sequential.append(
                {
                    "moving_bracket": i,
                    "radial_offset_mm": offset,
                    "omitted_own_not_yet_installed": sorted(own - {bracket.name}),
                    "installed_other_fasteners": sorted(
                        p.name for p in counterparts if p.name.startswith("C9_")
                    ),
                    "hits": hits,
                }
            )
    payload = {
        "status": "PASS_MINIMUM_FASTENER_ACCESS_GEOMETRY"
        if not any(r["hits"] for r in rows + sequential)
        else "ACCESS_BLOCKED",
        "physical_result": "NOT_RUN",
        "source_sha256": base.PINS,
        "scope": "Housing, glass and seal envelopes absent. Conservative screw and rotating-nut swept outer envelopes; minimum hex-key shaft only. No chosen wrench/driver handle, torque stroke, thread manufacturing, preload or operator access qualification.",
        "checks": rows,
        "sequential_bracket_with_other_fasteners": sequential,
    }
    (base.OUT / "fastener-access-checks.json").write_text(json.dumps(payload, indent=2) + "\n")
    if payload["status"] != "PASS_MINIMUM_FASTENER_ACCESS_GEOMETRY":
        raise RuntimeError("Fastener access blocked; inspect JSON")
    print("Nine minimum fastener/access checks and 18 sequential bracket checks passed.")


if __name__ == "__main__":
    main()
