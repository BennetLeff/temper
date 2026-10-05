"""R3 retained-cap coupon: measured opposing area, larger thermal gap.

Reuse the source-pinned R2 dry fixture. No force, conductance or strength calculation
belongs here; those are owned by the sibling Rust model.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import cadquery as cq

OUT = Path(__file__).resolve().parent
BASE_PATH = OUT.parents[1] / "revision2/mechanical/build.py"
SPEC = importlib.util.spec_from_file_location("temper_r2_cad", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load pinned R2 CAD generator")
base = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = base
SPEC.loader.exec_module(base)


def retained_cap(gap: float) -> cq.Shape:
    face = cq.Workplane("XY").workplane(offset=0.45).circle(4).extrude(0.15).val()
    toe_top = -2.25 - gap
    for angle in (0, 120, 240):
        hook = (
            base.box(0.85, 0.8, 0.15, (3.625, 0, 0.375))
            .fuse(
                base.box(
                    0.15, 0.8, 0.45 - (toe_top - 0.15), (3.975, 0, (0.45 + toe_top - 0.15) / 2)
                )
            )
            .fuse(base.box(0.75, 0.8, 0.15, (3.675, 0, toe_top - 0.075)))
        )
        face = face.fuse(base.rotate(hook, angle))
    return face


def facing_area(cap: cq.Shape, island: cq.Shape, gap: float) -> float:
    depth = 0.01
    bottom = -2.25
    toe_top = bottom - gap
    toe = cap.intersect(base.box(30, 30, depth, (0, 0, toe_top - depth / 2)))
    underside = island.intersect(base.box(30, 30, depth, (0, 0, bottom + depth / 2)))
    aligned = underside.translate((0, 0, -gap - depth))
    return toe.intersect(aligned).Volume() / depth


def anchor_coupon() -> tuple[cq.Shape, list[cq.Shape]]:
    # Dimensioned coupon volume, not a verified ceramic/PFA bonding process.
    pad = base.box(1.3, 1.5, 0.42, (0, -2.0, 0.24))
    wires = []
    for x in (-0.42, -0.14, 0.14, 0.42):
        wire = cq.Solid.makeCylinder(0.116, 1.5, cq.Vector(x, -2.75, 0.234), cq.Vector(0, 1, 0))
        pad = pad.cut(wire)
        wires.append(wire)
    return pad, wires


def build(common: float, local: float, maxchip: bool = False, cap_lift: float = 0.0) -> list:
    parts = base.build(common, local, maxchip)
    result = []
    for p in parts:
        shape = p.shape
        if p.name.startswith("cap_"):
            shape = retained_cap(0.2).translate((0, 0, -common - local))
        if p.name.startswith(("cap_", "Resbond", "M222")):
            shape = shape.translate((0, 0, cap_lift))
        result.append(base.Part(p.name, shape, p.group, p.envelope))
    pad, wires = anchor_coupon()
    dz = -common - local + cap_lift
    result.append(
        base.Part(
            "cap_thermal_anchor_COUPON_PROCESS_UNQUALIFIED", pad.translate((0, 0, dz)), "island"
        )
    )
    for i, wire in enumerate(wires):
        result.append(
            base.Part(
                f"anchor_PFA_wire_segment_{i + 1}_route_NOT_MODELLED",
                wire.translate((0, 0, dz)),
                "island",
            )
        )
    return result


def main() -> None:
    original = base.build()
    oldcap = next(p.shape for p in original if p.name.startswith("cap_"))
    island = next(p.shape for p in original if p.name.startswith("ceramic_island_puck"))
    assert abs(retained_cap(0.05).Volume() - oldcap.Volume()) < 1e-9
    caps = []
    for gap in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        cap = retained_cap(gap)
        caps.append(
            {
                "gap_mm": gap,
                "cap_volume_mm3": cap.Volume(),
                "disc_volume_mm3": cq.Workplane("XY").circle(4).extrude(0.15).val().Volume(),
                "opposing_hook_area_mm2": facing_area(cap, island, gap),
                "anchor_pad_volume_mm3": anchor_coupon()[0].Volume(),
            }
        )
    states = {}
    for name, common, local, maxchip, lift in [
        ("rest", 0.0, 0.0, False, 0.0),
        ("loaded", 0.45, 0.15, False, 0.0),
        ("local_stop", 0.0, 0.25, True, 0.0),
        ("full_stroke", 1.2, 0.25, False, 0.0),
        ("upper_capture", 0.0, -0.1, False, 0.0),
        ("cap_capture", 0.0, 0.0, False, 0.2),
    ]:
        parts = build(common, local, maxchip, lift)
        assembly = cq.Assembly(name="R3_" + name)
        for p in parts:
            assembly.add(p.shape, name=p.name)
        target = OUT / f"R3-{name}.step"
        cq.exporters.export(assembly.toCompound(), str(target))
        check = base.inspect(parts)
        imported = cq.importers.importStep(str(target)).solids().vals()
        check["step_roundtrip_valid"] = bool(imported) and all(s.isValid() for s in imported)
        if not check["valid"] or check["rigid_intersections"] or not check["step_roundtrip_valid"]:
            raise RuntimeError(f"{name}: {check}")
        states[name] = check
    cq.exporters.export(retained_cap(0.2), str(OUT / "R3-cap.step"))
    section = cq.Compound.makeCompound(
        [
            p.shape.intersect(base.box(60, 30, 100, (0, 15, -15)))
            for p in build(0.0, 0.0)
            if not p.envelope
        ]
    )
    cq.exporters.export(
        section,
        str(OUT / "R3-section.svg"),
        opt={
            "width": 700,
            "height": 950,
            "projectionDir": (0, -1, 0),
            "showAxes": False,
            "showHidden": False,
        },
    )
    result = {
        "status": "DRY PROTOTYPE; cap free lift increased; formed harness/strength/sealing unqualified",
        "selected_gap_mm": 0.2,
        "caps": caps,
        "states": states,
    }
    (OUT / "geometry.json").write_text(json.dumps(result, indent=2) + "\n")
    # CAD scalars consumed by Rust; avoid another hand-copied cap mass or facing area.
    with (OUT / "thermal_geometry.csv").open("w") as stream:
        stream.write(
            "gap_mm,cap_volume_mm3,disc_volume_mm3,opposing_hook_area_mm2,anchor_pad_volume_mm3\n"
        )
        for row in caps:
            stream.write(",".join(f"{v:.12f}" for v in row.values()) + "\n")
    for output in [*OUT.glob("*.step"), *OUT.glob("*.svg")]:
        output.write_text(
            "\n".join(line.rstrip() for line in output.read_text().splitlines()) + "\n"
        )
    print(
        json.dumps(
            {
                "caps": caps,
                "states": {
                    k: {
                        "valid": v["valid"],
                        "intersections": v["rigid_intersections"],
                        "step_roundtrip_valid": v["step_roundtrip_valid"],
                    }
                    for k, v in states.items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
