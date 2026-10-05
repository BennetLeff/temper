"""PR2 dimensional CAD only. Dynamics/thermal arithmetic belong to Rust models.

Dry instrumented prototype: open witness/lead passages are explicitly NOT sealed.
Units mm; glass top z0; common stroke and cap-local stroke are independent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import cos, radians, sin
from pathlib import Path

import cadquery as cq

OUT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Part:
    name: str
    shape: cq.Shape
    group: str
    envelope: bool = False


def ring(ro: float, ri: float, z: float, h: float) -> cq.Shape:
    return cq.Workplane("XY").workplane(offset=z).circle(ro).circle(ri).extrude(h).val()


def box(x: float, y: float, z: float, at: tuple[float, float, float]) -> cq.Shape:
    return cq.Workplane("XY").box(x, y, z).translate(at).val()


def rotate(s: cq.Shape, angle: float) -> cq.Shape:
    return s.rotate((0, 0, 0), (0, 0, 1), angle)


def build(
    common: float = 0.0,
    local: float = 0.0,
    maximum_chip: bool = False,
    material: str = "316L",
    optimized: bool = True,
    spider: bool = True,
) -> list[Part]:
    parts = []

    def add(name: str, s: cq.Shape, group: str = "frame", envelope: bool = False) -> None:
        dz = 0.0 if group == "fixed" else -common - local if group == "island" else -common
        parts.append(Part(name, s.translate((0, 0, dz)), group, envelope))

    # Fixed body and glass: aperture made only in mock glass, not a strength claim.
    add("glass_4mm_hole18_ENVELOPE", ring(25, 9, -4, 4), "fixed", True)
    body = ring(14, 12.5, -24, 19.3).fuse(ring(14, 7.7, -5.3, 0.6)).fuse(ring(8.5, 7.7, -4.7, 3.9))
    add("fixed_carrier_housing", body, "fixed")
    # Main plunger platform carries seal and flexure outer anchors. It may jam.
    frame = ring(12, 4.7, -9, 1).fuse(ring(5.4, 4.7, -8, 6.8))
    frame = frame.fuse(ring(3, 1.4, -25, 16))
    for a in (0, 120, 240):
        frame = frame.fuse(rotate(box(3.5, 2.0, 1, (3.9, 0, -8.5)), a))
        frame = frame.fuse(rotate(box(1, 2.5, 1.92, (11.5, 0, -7.04)), a))
    for a in (0, 120, 240):
        frame = frame.cut(rotate(box(1.6, 2.5, 0.8, (5.0, 0, -6.1)), a))
    for a in (60, 180, 300):
        frame = frame.fuse(rotate(box(3.5, 2.0, 1, (3.9, 0, -8.5)), a))
    add("main_carrier_and_stem_D6_bore2p8", frame)
    # Local island: central ceramic stalk; tabs for independent flexible beams.
    post_length = 2.0 if optimized else 1.15
    puck_top = 0.45 - post_length
    puck_bottom = puck_top - 0.7
    puck = ring(3.6, 1.1, puck_bottom, 0.7)
    if optimized and spider:
        puck = ring(1.6, 1.1, puck_bottom, 0.7)
        for a in (0, 60, 120, 180, 240, 300):
            arm = box(2.3, 0.8 if a % 120 == 0 else 0.6, 0.7, (2.45, 0, puck_bottom + 0.35))
            puck = puck.fuse(rotate(arm, a))
    puck = puck.cut(box(3.0, 2.8, 1.1, (0, 0, -0.65)))
    # Closed pocket floor with small wire holes; pocket clearance inspected separately.
    puck = puck.fuse(ring(1.6, 1.1, -6.8, puck_bottom + 6.8))
    island_base = ring(4, 1.1, -6.8, 0.72)
    # Bulk support does not contact full cap: only 3 small ceramic posts.
    for a in (60, 180, 300):
        x, y = 3.1 * cos(radians(a)), 3.1 * sin(radians(a))
        post = (
            cq.Workplane("XY")
            .workplane(offset=puck_top)
            .center(x, y)
            .circle(0.15 if optimized else 0.25)
            .extrude(post_length)
            .val()
        )
        puck = puck.fuse(post)
    add("ceramic_island_puck_stalk_and_posts", puck.fuse(island_base), "island")
    # Three isolated X750 blades. No circumferential metallic ring.
    for i, a in enumerate((0, 120, 240)):
        wp = cq.Workplane("YZ")
        lastz = 0.0
        for n in range(17):
            q = n / 16
            z = -6.04 - local * (1 - 3 * q * q + 2 * q * q * q)
            wp = (
                wp.workplane(offset=4 if n == 0 else 7 / 16)
                .center(0, z if n == 0 else z - lastz)
                .rect(2.1, 0.08)
            )
            lastz = z
        blade = (
            wp.loft(combine=True)
            .val()
            .fuse(box(0.5, 2.1, 0.08, (3.75, 0, -6.04 - local)))
            .fuse(box(0.6, 2.1, 0.08, (11.3, 0, -6.04)))
        )
        add(f"X750_blade_{i + 1}_freeL7_w2p1_t0p08", rotate(blade, a), "frame")
        # Top clamps bind blade pads, never its free length.
        add(f"outer_ceramic_blade_clamp_{i + 1}", rotate(box(0.6, 2.5, 0.3, (11.3, 0, -5.85)), a))
        add(
            f"inner_ceramic_blade_clamp_{i + 1}",
            rotate(box(0.5, 2.5, 0.3, (3.75, 0, -5.85)), a),
            "island",
        )
    # Local overload stop: island bottom -6.8, frame pads top -7.05 =>0.25mm.
    for i, a in enumerate((60, 180, 300)):
        add(f"ceramic_overload_pad_{i + 1}", rotate(box(1.0, 1.0, 0.95, (3.5, 0, -7.525)), a))
    # Three positive upward capture fingers: 0.10mm lift clearance at local rest.
    for i, a in enumerate((60, 180, 300)):
        capture = box(0.5, 0.8, 2.32, (4.3, 0, -6.84)).fuse(box(1.3, 0.8, 0.3, (3.9, 0, -5.83)))
        add(f"ceramic_upper_capture_finger_{i + 1}", rotate(capture, a))
    # Skirtless cap and discrete mechanical capture hooks.
    roof = 0.15 if material == "316L" else 0.25
    cap = cq.Workplane("XY").workplane(offset=0.6 - roof).circle(4).extrude(roof).val()
    if material == "316L":
        for a in (0, 120, 240):
            toe_top = puck_bottom - 0.05
            hook = (
                box(0.85, 0.8, 0.15, (3.625, 0, 0.375))
                .fuse(
                    box(0.15, 0.8, 0.45 - (toe_top - 0.15), (3.975, 0, (0.45 + toe_top - 0.15) / 2))
                )
                .fuse(box(0.75, 0.8, 0.15, (3.675, 0, toe_top - 0.075)))
            )
            cap = cap.fuse(rotate(hook, a))
    add("cap_" + material + "_D8_positive_capture", cap, "island")
    chip = (2.5, 2.3, 1.2) if maximum_chip else (2.3, 2.1, 0.9)
    bond = 0.15 if maximum_chip else 0.1
    underside = 0.6 - roof
    add("Resbond908_bond_candidate", box(2.7, 2.5, bond, (0, 0, underside - bond / 2)), "island")
    add(
        "M222_body_max" if maximum_chip else "M222_body",
        box(*chip, (0, 0, underside - bond - chip[2] / 2)),
        "island",
    )
    # FFKM material candidate membrane envelope; no modulus/force inference.
    z = -1.2 - common
    profile = [
        (5.4, z),
        (5.8, z),
        (6.5, -2.5 - common / 2),
        (7.5, -0.8),
        (8.5, -0.8),
        (8.5, -1.1),
        (7.5, -1.1),
        (6.5, -2.8 - common / 2),
        (5.8, z - 0.3),
        (5.4, z - 0.3),
    ]
    seal = cq.Workplane("XZ").polyline(profile).close().revolve().val()
    add("Kalrez6375_CUSTOM_rolling_membrane_ENVELOPE", seal, "fixed", True)
    # Custom static axial gasket, 1mm free ->0.7mm target installed thickness.
    add("Kalrez6375_CUSTOM_static_face_gasket_ENVELOPE", ring(12, 9.3, -4.7, 0.7), "fixed", True)
    # Dry bench witness routes. Rods must not be represented as leakproof penetrations.
    for name, x, group, top in [("island", 0.8, "island", -6.8), ("carrier", -0.8, "frame", -9.0)]:
        lower = -38 if name == "island" else -40
        rod = (
            cq.Workplane("XY")
            .workplane(offset=lower)
            .center(x, 0)
            .circle(0.2)
            .extrude(top - lower)
            .val()
        )
        add(name + "_D0p4_witness_rod_UNSEALED", rod, group, True)
        add(name + "_optical_flag_2x2", box(2, 2, 0.4, (x, 0, lower - 0.2)), group, True)
    add(
        "four_wires_D0p9_bundle_RESERVED",
        cq.Workplane("XY").workplane(offset=-38).center(0, 0.6).circle(0.45).extrude(35).val(),
        "frame",
        True,
    )
    return parts


def inspect(parts: list[Part]) -> dict:
    rigid = [p for p in parts if not p.envelope]
    overlaps = []
    for i, a in enumerate(rigid):
        for b in rigid[i + 1 :]:
            v = a.shape.intersect(b.shape).Volume()
            if v > 1e-5:
                overlaps.append({"a": a.name, "b": b.name, "volume_mm3": v})
    return {
        "valid": all(p.shape.isValid() for p in parts),
        "rigid_intersections": overlaps,
        "part_count": len(parts),
        "volumes_mm3": {p.name: p.shape.Volume() for p in parts},
    }


def main() -> None:
    states = {}
    for name, common, local, maxchip in [
        ("rest", 0, 0, False),
        ("loaded", 0.45, 0.15, False),
        ("local_stop", 0, 0.25, True),
        ("full_stroke", 1.2, 0.25, False),
        ("upper_capture", 0, -0.1, False),
    ]:
        parts = build(common, local, maxchip)
        asm = cq.Assembly(name="PR2_" + name)
        for p in parts:
            asm.add(
                p.shape,
                name=p.name,
                color=cq.Color(0.7, 0.75, 0.78) if "cap_" in p.name else cq.Color(0.75, 0.7, 0.56),
            )
        asm.save(str(OUT / f"PR2-{name}.step"))
        states[name] = inspect(parts)
        imported = cq.importers.importStep(str(OUT / f"PR2-{name}.step")).solids().vals()
        states[name]["step_roundtrip_valid"] = all(s.isValid() for s in imported)
    initial = inspect(build(optimized=False))
    long_solid = inspect(build(optimized=True, spider=False))
    parts = build()
    clip = box(60, 30, 100, (0, 15, -15))
    section = cq.Compound.makeCompound(
        [p.shape.intersect(clip) for p in parts if p.shape.intersect(clip).Volume() > 1e-8]
    )
    cq.exporters.export(section, str(OUT / "PR2-section.step"))
    cq.exporters.export(
        section,
        str(OUT / "PR2-section.svg"),
        opt={
            "width": 700,
            "height": 950,
            "projectionDir": (0, -1, 0),
            "showAxes": False,
            "showHidden": False,
        },
    )
    cap = next(p for p in parts if p.name.startswith("cap_"))
    geom = {
        "revision": "PR2",
        "status": "DRY instrumented prototype, witness and lead passages NOT spill sealed",
        "cap": {
            "material": "316L",
            "contact_diameter_mm": 8,
            "face_thickness_mm": 0.15,
            "cad_volume_mm3": cap.shape.Volume(),
            "density_kg_m3": 8000,
            "heat_capacity_j_kgk": 500,
            "retention": "3discrete welded hooks, no closed metal ring",
            "hook_width_mm": 0.8,
            "hook_thickness_mm": 0.15,
            "hook_release_gap_mm": 0.05,
        },
        "support": {
            "material": "Morgan CIM Zirconia custom prototype; vendorpartdrawing notyetaccepted",
            "post_count": 3,
            "post_diameter_mm": 0.3,
            "post_length_mm": 2.0,
            "head_support_spider": "hubD3.2bore2.2,6radialarmsL2.3w0.6or0.8t0.7; projectedarea CADoutput",
            "cap_contact_conductance_w_k": "unmeasured; include finite support node",
            "normal_contact": "three posts only; retention hook toes separated0.05mm",
            "density_kg_m3_min": 6000,
            "heat_capacity_j_kgk_typical": 610,
            "thermal_conductivity_w_mk_at20c": 2.9,
            "supplier_url": "https://www.morganthermalceramics.com/media/00td54fl/cim-zirconia.pdf",
        },
        "local_flexure": {
            "material": "X750 strip UNSN07750 process pending",
            "count": 3,
            "free_length_mm": 7,
            "width_mm": 2.1,
            "thickness_mm": 0.08,
            "normal_stroke_mm": 0.2,
            "overload_stop_mm": 0.25,
            "isolation": "all seal and guide reactions act on maincarrier, not localisland",
        },
        "seal": {
            "compound": "DuPont Kalrez6375",
            "published_max_c": 275,
            "custom_membrane_thickness_mm": 0.3,
            "force_curve": "unknown; supplier finite-strain and life data required",
            "assembly_seal_status": "incomplete because witness/lead passages open",
        },
        "states": states,
        "initial_alumina_short_posts": initial,
        "long_posts_solid_puck": long_solid,
    }
    island = next(p for p in parts if p.name.startswith("ceramic_island_puck"))
    geom["support"]["spider_projected_area_mm2"] = (
        island.shape.intersect(box(30, 30, 0.1, (0, 0, -1.9))).Volume() / 0.1
    )
    geom["support"]["island_volume_mm3"] = island.shape.Volume()
    geom["support"]["inner_clamps_volume_mm3"] = sum(
        p.shape.Volume() for p in parts if p.name.startswith("inner_ceramic")
    )
    geom["local_flexure"]["total_blade_volume_mm3"] = sum(
        p.shape.Volume() for p in parts if p.name.startswith("X750")
    )
    (OUT / "geometry.json").write_text(json.dumps(geom, indent=2) + "\n")
    for p in [*OUT.glob("*.step"), *OUT.glob("*.svg")]:
        p.write_text("\n".join(x.rstrip() for x in p.read_text().splitlines()) + "\n")
    assert all(
        v["valid"] and v["step_roundtrip_valid"] and not v["rigid_intersections"]
        for v in states.values()
    )
    print(
        json.dumps(
            {
                n: {"valid": s["valid"], "overlaps": s["rigid_intersections"]}
                for n, s in states.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
