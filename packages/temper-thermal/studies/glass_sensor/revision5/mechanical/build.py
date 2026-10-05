"""R5 dimensioned dry cartridge CAD; all physical qualification remains NOT_RUN."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import cadquery as cq

SOURCE = Path(__file__).resolve().parents[2] / "revision2/mechanical/build.py"
if not SOURCE.exists():
    SOURCE = Path(__file__).resolve().parent / "r2_pinned.py"
if (
    hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    != "3057c0ede6adeeed338d0dc554b63100dfe5040e9bef562fb622199807f6499d"
):
    raise RuntimeError("Pinned R2 geometry source changed")
SPEC = importlib.util.spec_from_file_location("temper_r2_cad", SOURCE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load pinned R2 CAD")
b = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = b
SPEC.loader.exec_module(b)

OUT = Path(__file__).resolve().parent


def cap(radius: float) -> cq.Shape:
    shape = cq.Workplane("XY").workplane(offset=0.45).circle(radius).extrude(0.15).val()
    for a in (0, 120, 240):
        if radius < 4:
            shape = shape.fuse(b.rotate(b.box(1.25, 0.8, 0.15, (3.325, 0, 0.375)), a))
        hook = (
            b.box(0.85, 0.8, 0.15, (3.625, 0, 0.375))
            .fuse(b.box(0.15, 0.8, 3.05, (3.975, 0, -1.075)))
            .fuse(b.box(0.75, 0.8, 0.15, (3.675, 0, -2.525)))
        )
        shape = shape.fuse(b.rotate(hook, a))
    # Additional three recessed support ears lie over the ceramic posts.
    if radius < 4:
        for a in (60, 180, 300):
            shape = shape.fuse(b.rotate(b.box(0.9, 0.65, 0.15, (3.05, 0, 0.375)), a))
    return shape


def weld_bead(index: int) -> cq.Shape:
    sign = -1 if index < 2 else 1
    start = cq.Vector(
        sign * 0.7 + (index % 2 - 0.5) * 0.28, 2.05, 0.15 if index % 2 == 0 else -0.15
    )
    terminal = cq.Vector(sign * 0.7, 2.02, 0)
    delta = start - terminal
    return cq.Solid.makeCylinder(0.08, delta.Length, terminal, delta.normalized()).fuse(
        cq.Solid.makeSphere(0.08, start, angleDegrees1=-90)
    )


@lru_cache(maxsize=1)
def components() -> tuple[cq.Shape, cq.Shape, list[cq.Shape], list[cq.Shape]]:
    anchor = b.box(1.3, 1.5, 0.72, (0, -2, 0.09))
    for i, x in enumerate((-0.42, -0.14, 0.14, 0.42)):
        anchor = anchor.cut(
            cq.Solid.makeCylinder(
                0.116, 1.5, cq.Vector(x, -2.75, 0.15 if i % 2 == 0 else -0.15), cq.Vector(0, 1, 0)
            )
        )
    covers = []
    joins = []
    for x in (-0.7, 0.7):
        cover = b.box(1, 1.4, 0.8, (x, 1.8, 0.05))
        cavity = b.box(0.72, 1.15, 0.36, (x, 1.8, 0.02))
        cover = cover.cut(cavity).cut(b.box(2.7, 2.5, 0.1, (0, 0, 0.4))).cut(cap(3))
        cover = cover.cut(
            cq.Solid.makeCylinder(0.15, 1.5, cq.Vector(x, 1.05, 0), cq.Vector(0, 1, 0))
        )
        covers.append(cover)
        joins.append(cq.Solid.makeCylinder(0.10, 1, cq.Vector(x, 1.05, 0), cq.Vector(0, 1, 0)))
    for i in range(4):
        wire, *_ = route(i, 0)
        anchor = anchor.cut(wire)
        covers = [cover.cut(wire).cut(weld_bead(i)) for cover in covers]
    return anchor, cq.Compound.makeCompound(covers), covers, joins


def route(index: int, shift: float) -> tuple[cq.Shape, float, float, float, float]:
    x = (-0.42, -0.14, 0.14, 0.42)[index]
    sign = -1 if index < 2 else 1
    lane = sign * (1.55 + 0.4 * ((1 - index % 2) if index < 2 else index % 2))
    height = 0.15 if index % 2 == 0 else -0.15
    hot = [
        (sign * 0.7 + (index % 2 - 0.5) * 0.28, 2.05, height),
        (lane, 1.6, height),
        (lane, -1.4, height),
        (x, -1.25, height),
        (x, -2.75, height),
    ]
    hot = [cq.Vector(px, py, pz + shift) for px, py, pz in hot]

    def make(amplitude: float) -> tuple[cq.Wire, float]:
        points = hot + [
            cq.Vector(x, -3.5, height + shift),
            cq.Vector(x, -3.5, -1.15 + shift),
            cq.Vector(x, 0.45, -1.15 + shift),
            cq.Vector(x, 0.45, -12 + shift),
            cq.Vector(x, 0.45, -30 + shift),
            cq.Vector(x, amplitude, -40),
            cq.Vector(x, 0.45, -47),
        ]
        edges = []
        last = points[0]
        hot_length = 0.0
        for i in range(1, len(points) - 1):
            p = points[i]
            u = (p - points[i - 1]).normalized()
            v = (points[i + 1] - p).normalized()
            theta = math.acos(max(-1.0, min(1.0, u.dot(v))))
            if theta < 1e-7:
                edges.append(cq.Edge.makeLine(last, p))
                last = p
                if i == 4:
                    hot_length = sum(e.Length() for e in edges)
                continue
            radius = 2.0 if i >= 9 else 0.5
            tangent = radius * math.tan(theta / 2)
            if tangent >= min((p - points[i - 1]).Length, (points[i + 1] - p).Length):
                raise ValueError(f"fillet exceeds segment at corner{i}")
            pin = p - u * tangent
            pout = p + v * tangent
            center = p + (v - u).normalized() * (radius / math.cos(theta / 2))
            midpoint = center + (p - center).normalized() * radius
            if (pin - last).Length > 1e-8:
                edges.append(cq.Edge.makeLine(last, pin))
            edges.append(cq.Edge.makeThreePointArc(pin, midpoint, pout))
            last = pout
            if i == 4:
                hot_length = sum(e.Length() for e in edges)
        edges.append(cq.Edge.makeLine(last, points[-1]))
        return cq.Wire.assembleEdges(edges), hot_length

    lo, hi = 2.0, 20.0
    for _ in range(35):
        mid = (lo + hi) / 2
        path, _ = make(mid)
        if path.Length() > 60:
            hi = mid
        else:
            lo = mid
    path, hot_length = make((lo + hi) / 2)
    plane = cq.Plane(origin=path.startPoint(), normal=path.Edges()[0].tangentAt(0))
    solid = cq.Workplane(plane).circle(0.116).sweep(cq.Workplane(obj=path), isFrenet=True).val()
    start = path.startPoint()
    direction = path.Edges()[0].tangentAt(0)
    strip = cq.Solid.makeCylinder(0.117, 0.5, start, direction)
    bare = cq.Solid.makeCylinder(0.04, 0.5, start, direction)
    solid = solid.cut(strip).fuse(bare)
    return solid, hot_length, path.Length() - hot_length, (lo + hi) / 2, 0.5


def build(radius: float, common: float, local: float, lift: float) -> tuple[list, list]:
    parts = []
    dz = -common - local + lift
    for p in b.build(common, local):
        if p.name.startswith(("cap_", "four_wires")):
            continue
        shape = p.shape
        if p.name.startswith(("Resbond", "M222")):
            shape = shape.translate((0, 0, lift))
        if radius < 4 and p.name.startswith("ceramic_island"):
            for a in (60, 180, 300):
                x, y = 3.1 * math.cos(math.radians(a)), 3.1 * math.sin(math.radians(a))
                shape = shape.cut(b.box(0.4, 0.4, 0.15, (x, y, 0.375 - common - local)))
        parts.append(b.Part(p.name, shape, p.group, p.envelope))
    parts.append(
        b.Part("cap_316L_D" + str(int(radius * 2)), cap(radius).translate((0, 0, dz)), "cap")
    )
    anchor, _, covers, joins = components()
    parts.append(b.Part("cap_moving_anchor_PROCESS_COUPON", anchor.translate((0, 0, dz)), "cap"))
    for i, s in enumerate(covers):
        film = s.intersect(b.box(20, 20, 0.075, (0, 0, 0.4125)))
        ceramic = s.cut(film)
        parts.append(b.Part(f"cap_moving_ceramic_cover_{i}", ceramic.translate((0, 0, dz)), "cap"))
        parts.append(
            b.Part(f"cover_Resbond_attachment_film_{i}", film.translate((0, 0, dz)), "cap")
        )
    for i, s in enumerate(joins):
        parts.append(
            b.Part(f"native_Ni_terminal_weld_region_{i}", s.translate((0, 0, dz)), "cap", True)
        )
    metrics = []
    for i in range(4):
        wire, hot, cold, amp, max_radius = route(i, dz)
        parts.append(
            b.Part(f"PFA_route_{i}_R0p5_STATIC_R2_DYNAMIC_STRIP0p5", wire, "flexible", True)
        )
        parts.append(
            b.Part(
                f"Cu_Ni_WELD_BEAD_{i}_PROCESS_ENVELOPE",
                weld_bead(i).translate((0, 0, dz)),
                "cap",
                True,
            )
        )
        metrics.append(
            {
                "wire": i,
                "hot_length_mm": hot,
                "cold_length_mm": cold,
                "total_length_mm": hot + cold,
                "loop_y_mm": amp,
                "maximum_uniform_fillet_radius_mm": max_radius,
                "static_minimum_radius_mm": 0.5,
                "dynamic_minimum_radius_mm": 2,
                "bend_status": "STATIC_FORMING_APPROVAL_PENDING; DYNAMIC_R2_GEOMETRY",
                "hot_before_anchor_mm": hot - 1.0,
                "anchored_mm": 1.0,
                "cold_after_anchor_mm": cold,
                "stripped_length_mm": 0.5,
                "insulated_length_mm": 59.5,
                "core_volume_mm3": math.pi * 0.04**2 * 60,
                "jacket_volume_mm3": math.pi * (0.116**2 - 0.04**2) * 59.5,
            }
        )
    return parts, metrics


def main() -> None:
    rows = []
    results = {}
    for name, radius in [("D8", 4.0), ("D6", 3.0)]:
        cap_shape = cap(radius)
        anchor, cover, _, _ = components()
        states = {}
        for pose, common, local, lift in [
            ("rest", 0, 0, 0),
            ("loaded", 0.490909, 0.109091, 0),
            ("local_stop", 0, 0.25, 0),
            ("full_stroke", 1.2, 0.25, 0),
            ("upper_capture", 0, -0.1, 0),
            ("cap_capture", 0, 0, 0.2),
        ]:
            parts, routes = build(radius, common, local, lift)
            compound = cq.Compound.makeCompound([p.shape for p in parts])
            target = OUT / f"R5-{name}-{pose}.step"
            cq.exporters.export(compound, str(target))
            imported = cq.importers.importStep(str(target)).solids().vals()
            inspection = b.inspect(parts)
            inspection["step_roundtrip_valid"] = bool(imported) and all(
                s.isValid() for s in imported
            )
            if (
                not inspection["valid"]
                or inspection["rigid_intersections"]
                or not inspection["step_roundtrip_valid"]
            ):
                raise RuntimeError(f"Invalid assembly {name}/{pose}: {inspection}")
            inspection["routes"] = routes
            inspection["wire_geometry_status"] = (
                "Continuous smooth60mm centerline; staticR0.5 and dynamicR2mm; forming/fatigue NOT_RUN"
            )
            states[pose] = inspection
            print(name, pose, inspection["valid"], inspection["rigid_intersections"], flush=True)
        parts, routes = build(radius, 0, 0, 0)
        support = next(p.shape for p in parts if p.name.startswith("ceramic_island"))
        disc = math.pi * radius**2 * 0.15
        hookvol = cap(4).Volume() - math.pi * 16 * 0.15
        hot = sum(r["hot_length_mm"] for r in routes) / 4
        rows.append(
            {
                "variant": name,
                "head_radius_mm": radius,
                "disc_thickness_mm": 0.15,
                "cap_volume_mm3": cap_shape.Volume(),
                "disc_volume_mm3": disc,
                "hook_volume_mm3": hookvol,
                "ear_volume_mm3": cap_shape.Volume() - disc - hookvol,
                "opposing_hook_area_mm2": 0.72,
                "gap_mm": 0.2,
                "bond_volume_mm3": 0.675,
                "bond_footprint_mm2": 6.75,
                "bond_thickness_mm": 0.1,
                "cover_volume_mm3": cover.cut(b.box(20, 20, 0.075, (0, 0, 0.4125))).Volume(),
                "cover_bond_volume_mm3": cover.intersect(
                    b.box(20, 20, 0.075, (0, 0, 0.4125))
                ).Volume(),
                "cover_bond_thickness_mm": 0.075,
                "cover_bond_area_mm2": cover.intersect(
                    b.box(20, 20, 0.075, (0, 0, 0.4125))
                ).Volume()
                / 0.075,
                "anchor_pad_volume_mm3": anchor.Volume(),
                "support_volume_mm3": support.Volume(),
                "support_inner_clamp_volume_mm3": sum(
                    p.shape.Volume()
                    for p in parts
                    if p.name.startswith("inner_ceramic_blade_clamp")
                ),
                "witness_rod_volume_mm3": sum(
                    p.shape.Volume() for p in parts if p.name.startswith("island_D0p4")
                ),
                "witness_flag_volume_mm3": sum(
                    p.shape.Volume() for p in parts if p.name.startswith("island_optical")
                ),
                "ear_max_radius_mm": math.hypot(4.05, 0.4),
                "ear_recess_mm": 0.15,
                "post_length_mm": 2 if radius == 4 else 1.85,
                "post_diameter_mm": 0.3,
                "wire_total_length_mm": 60,
                "wire_hot_length_mm": hot,
                "wire_anchor_length_mm": 1.0,
                "wire_cold_length_mm": 60 - hot,
                "wire_copper_diameter_mm": 0.08,
                "wire_outer_diameter_mm": 0.232,
                "wire_stripped_length_mm": 0.5,
                "native_nickel_length_mm": 1,
                "weld_bead_volume_mm3": sum(weld_bead(i).Volume() for i in range(4)),
                "cover_outer_radius_mm": 2.774887385,
                "cover_inner_radius_mm": 1.118033989,
                "cover_wall_mm": 0.14,
                "ear_count": 6 if radius < 4 else 0,
                "ear_neck_total_width_mm": 4.35 if radius < 4 else 0,
                "ear_neck_width_mm": 0.65,
                "ear_neck_length_mm": 0.5,
                "ear_thickness_mm": 0.15,
            }
        )
        cq.exporters.export(cap_shape, str(OUT / f"R5-{name}-cap.step"))
        section = cq.Compound.makeCompound(
            [
                p.shape.intersect(b.box(70, 35, 120, (0, 17.5, -20)))
                for p in parts
                if not p.envelope
                and p.shape.intersect(b.box(70, 35, 120, (0, 17.5, -20))).Volume() > 1e-8
            ]
        )
        cq.exporters.export(
            section,
            str(OUT / f"R5-{name}-section.svg"),
            opt={
                "width": 900,
                "height": 1000,
                "projectionDir": (0, -1, 0),
                "showAxes": False,
                "showHidden": False,
            },
        )
        results[name] = states
    with (OUT / "thermal_geometry.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "geometry.json").write_text(
        json.dumps(
            {
                "stage": "DRY ENGINEERING PROTOTYPE PREPARATION; NOT_RUN physical",
                "states": results,
                "thermal_geometry": rows,
            },
            indent=2,
        )
        + "\n"
    )

    for output in [*OUT.glob("*.step"), *OUT.glob("*.svg")]:
        output.write_text(
            "\n".join(line.rstrip() for line in output.read_text().splitlines()) + "\n"
        )


if __name__ == "__main__":
    main()
