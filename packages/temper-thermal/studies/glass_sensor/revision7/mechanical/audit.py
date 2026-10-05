"""Independent dimensional, tolerance-envelope and deliberate-fault CAD checks."""

from __future__ import annotations

import json
import math
from pathlib import Path

import build

OUT = Path(__file__).resolve().parent


def require_clear_envelopes(records: list[dict]) -> None:
    failures = [r["variant"] for r in records if r["intersections"]]
    if failures:
        raise RuntimeError(f"Maximum package envelope collision: {failures}")


def main() -> None:
    checks = []
    tolerance = []
    for variant in build.VARIANTS:
        parts, routes = build.make(variant, 0, 0, 0)
        leads = [p for p in parts if p.name.startswith("native_Ni")]
        length = build.native(variant, 1)[1]
        larger = build.replace(variant, lead_diameter=variant.lead_diameter + 0.05)
        clearance_shape, clearance_length = build.native(larger, 1)
        clearance_volume = math.pi * (larger.lead_diameter / 2) ** 2 * clearance_length
        if abs(clearance_shape.Volume() - clearance_volume) > 1e-6:
            raise RuntimeError("Native clearance sweep ignores requested diameter")
        expected = 2 * math.pi * (variant.lead_diameter / 2) ** 2 * length
        measured = sum(p.shape.Volume() for p in leads)
        if abs(expected - measured) > 1e-6:
            raise RuntimeError("Native sweep volume does not match centerline length")
        expected_wire = math.pi * (0.116**2 * 59.5 + 0.04**2 * 0.5)
        for p in parts:
            if p.name.startswith("PFA_route") and abs(p.shape.Volume() - expected_wire) > 1e-5:
                raise RuntimeError("Wire sweep volume does not match full 60mm")
        # Datasheet package maximum screens (lead-pad pitch remains unknown).
        x, y, h = (1.0, 3.2, 0.9) if variant.name.startswith("IST") else (2.5, 2.3, 1.2)
        maximum = build.b.box(x, y, h, (0, 0, 0.45 - variant.bond - h / 2))
        collisions = []
        for p in parts:
            if p.name.startswith(("RTD_package", "Resbond908", "native_Ni")):
                continue
            volume = maximum.intersect(p.shape).Volume()
            if volume > 1e-6:
                collisions.append({"part": p.name, "volume_mm3": volume})
        tolerance.append(
            {
                "variant": variant.name,
                "maximum_package_mm": [x, y, h],
                "intersections": collisions,
                "result": "FAIL_MAXIMUM_ENVELOPE" if collisions else "PASS_GEOMETRY_ONLY",
                "physical_result": "NOT_RUN",
            }
        )
        checks.append(
            {
                "variant": variant.name,
                "native_volume_expected_mm3": expected,
                "native_volume_cad_mm3": measured,
                "four_60mm_wire_volumes": "PASS",
            }
        )
    # A failed envelope screen must prevent the runner's success receipt.
    try:
        require_clear_envelopes(
            [{"variant": "deliberate_fault", "intersections": [{"volume_mm3": 0.1}]}]
        )
    except RuntimeError as error:
        if "Maximum package envelope collision" not in str(error):
            raise
        envelope_fault = "PASS_REJECTED_MAXIMUM_ENVELOPE_COLLISION"
    else:
        raise RuntimeError("Maximum-envelope collision was accepted")
    unchanged = {"native_nickel_length_mm": 1.0}
    baseline = {"native_nickel_length_mm": "1"}
    build.preserve_unchanged_baseline(unchanged, baseline)
    if unchanged != baseline:
        raise RuntimeError("Unchanged baseline text was not preserved")
    try:
        build.preserve_unchanged_baseline({"native_nickel_length_mm": 1.01}, baseline)
    except RuntimeError as error:
        if "Undeclared M222 CAD scalar change" not in str(error):
            raise
        scalar_fault = "PASS_REJECTED_UNDECLARED_CAD_SCALAR_CHANGE"
    else:
        raise RuntimeError("Changed native lead scalar was overwritten by baseline")
    variant = build.VARIANTS[0]
    parts, _ = build.make(variant, 0, 0, 0)
    mutated = [
        build.b.Part(p.name, p.shape.translate((0, 0, -10)), p.group, p.envelope)
        if p.name.startswith("Cu_Ni_WELD_BEAD_0")
        else p
        for p in parts
    ]
    try:
        build.verify(mutated, variant, 0)
    except RuntimeError as error:
        if "Broken electrical topology" not in str(error):
            raise
        fault = "PASS_REJECTED_DISCONNECTED_WELD"
    else:
        raise RuntimeError("Disconnected weld was accepted")
    (OUT / "independent-audit.json").write_text(
        json.dumps(
            {
                "dimensional_checks": checks,
                "tolerance_envelopes": tolerance,
                "negative_test": fault,
                "envelope_negative_test": envelope_fault,
                "scalar_negative_test": scalar_fault,
            },
            indent=2,
        )
        + "\n"
    )
    require_clear_envelopes(tolerance)
    print(
        json.dumps(
            {
                "dimensional_checks": len(checks),
                "negative_test": fault,
                "tolerance_failures": sum(bool(r["intersections"]) for r in tolerance),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
