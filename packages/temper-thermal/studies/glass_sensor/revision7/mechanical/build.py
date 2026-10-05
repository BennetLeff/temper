"""R7 experimental coupon CAD: dimensions are not supplier/process qualification."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import cadquery as cq

OUT = Path(__file__).resolve().parent
R5_HASH = "f4507ebc3f8c7bf82c19c5b38b9099dbd6c7af1d3190635577c72ec466c7feca"
source = OUT.parents[1] / "revision5/mechanical/build.py"
if not source.exists():
    source = OUT / "r5_pinned.py"
if hashlib.sha256(source.read_bytes()).hexdigest() != R5_HASH:
    raise RuntimeError("R5 CAD source identity changed")
spec = importlib.util.spec_from_file_location("r5_coupon_source", source)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load pinned R5 CAD")
r5 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = r5
spec.loader.exec_module(r5)
b = r5.b


@dataclass(frozen=True)
class Variant:
    name: str
    bond: float
    x: float
    y: float
    height: float
    lead_diameter: float
    substrate: float
    film_path: float


VARIANTS = (
    Variant("M222_control_010", 0.1, 2.3, 2.1, 0.9, 0.2, 0.9, 0.45),
    Variant("M222_thin_0075", 0.075, 2.3, 2.1, 0.9, 0.2, 0.9, 0.45),
    Variant("IST308_thin_0075", 0.075, 0.8, 3.0, 0.6, 0.15, 0.25, 0.125),
)
POSES = (
    ("rest", 0.0, 0.0, 0.0),
    ("loaded", 0.490909, 0.109091, 0.0),
    ("full_stroke", 1.2, 0.25, 0.0),
    ("cap_capture", 0.0, 0.0, 0.2),
)


def preserve_unchanged_baseline(row: dict, original: dict) -> None:
    changed = {
        "variant",
        "bond_volume_mm3",
        "bond_thickness_mm",
        "cover_volume_mm3",
        "cover_bond_volume_mm3",
        "cover_bond_area_mm2",
        "anchor_pad_volume_mm3",
    }
    for key, previous in original.items():
        if key in changed:
            continue
        measured = row[key]
        # R5 text is retained only after any independently measured scalar agrees.
        # 1e-7 absolute permits CAD roundoff, not a manufacturing tolerance.
        if isinstance(measured, (float, int)) and not math.isclose(
            measured, float(previous), rel_tol=0, abs_tol=1e-7
        ):
            raise RuntimeError(
                f"Undeclared M222 CAD scalar change: {key}: {measured} != {previous}"
            )
        row[key] = previous


def native(variant: Variant, sign: int) -> tuple[cq.Shape, float]:
    if variant.name.startswith("M222"):
        return cq.Solid.makeCylinder(
            variant.lead_diameter / 2, 1.0, cq.Vector(sign * 0.7, 1.05, 0), cq.Vector(0, 1, 0)
        ), 1.0
    # Hypothesis: leads exit the short package end at x +/-0.2, z0.
    # Full installed lead after trimming; stock 7mm is NOT silently retained.
    p0 = cq.Vector(sign * 0.2, 1.5, 0)
    p1 = cq.Vector(sign * 0.7, 1.7, 0)
    p2 = cq.Vector(sign * 0.7, 2.05, 0)
    u = (p1 - p0).normalized()
    v = (p2 - p1).normalized()
    theta = math.acos(u.dot(v))
    radius = 0.5  # forming hypothesis, needs supplier approval
    tangent = radius * math.tan(theta / 2)
    pin, pout = p1 - u * tangent, p1 + v * tangent
    center = p1 + (v - u).normalized() * (radius / math.cos(theta / 2))
    middle = center + (p1 - center).normalized() * radius
    path = cq.Wire.assembleEdges(
        [
            cq.Edge.makeLine(p0, pin),
            cq.Edge.makeThreePointArc(pin, middle, pout),
            cq.Edge.makeLine(pout, p2),
        ]
    )
    plane = cq.Plane(origin=p0, normal=u)
    shape = (
        cq.Workplane(plane)
        .circle(variant.lead_diameter / 2)
        .sweep(cq.Workplane(obj=path), isFrenet=True)
        .val()
    )
    return shape, path.Length()


def ist_route(index: int, shift: float) -> tuple[cq.Shape, float, float, float, float]:
    x = (-0.42, -0.14, 0.14, 0.42)[index]
    sign = -1 if index < 2 else 1
    lane = sign * (1.55 + 0.4 * ((1 - index % 2) if index < 2 else index % 2))
    height = 0.15 if index % 2 == 0 else -0.15
    hot = [
        (sign * 0.7 + (index % 2 - 0.5) * 0.28, 2.05, height),
        (lane, 1.6, height),
        (lane, -1.9, height),
        (x, -1.9, height),
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


def make(variant: Variant, common: float, local: float, lift: float) -> tuple[list, list]:
    parts, routes = r5.build(3.0, common, local, lift)
    dz = -common - local + lift
    ist = variant.name.startswith("IST")
    bond_x, bond_y = (1.2, 3.4) if ist else (2.7, 2.5)
    chip = b.box(
        variant.x, variant.y, variant.height, (0, 0, 0.45 - variant.bond - variant.height / 2 + dz)
    )
    bond = b.box(bond_x, bond_y, variant.bond, (0, 0, 0.45 - variant.bond / 2 + dz))
    # An explicit pocket keeps joins/covers clear of the longer IST package.
    pocket_x, pocket_y, pocket_h = (1.1, 3.3, 1.0) if ist else (2.6, 2.4, 1.35)
    pocket_z = 0.45 - variant.bond - 0.9 / 2 if ist else -0.25
    pocket = b.box(pocket_x, pocket_y, pocket_h, (0, 0, pocket_z + dz))
    result = []
    for part in parts:
        if part.name.startswith(("M222", "Resbond908", "native_Ni")):
            continue
        shape = part.shape
        if ist and part.name.startswith("PFA_route"):
            index = int(part.name.split("_")[2])
            shape, hot, cold, amp, _ = ist_route(index, dz)
            anchor_envelope = b.box(1.3, 1.5, 0.72, (0, -2, 0.09 + dz))
            anchored = shape.intersect(anchor_envelope).Volume() / (math.pi * 0.116**2)
            routes[index].update(
                hot_length_mm=hot,
                cold_length_mm=cold,
                total_length_mm=hot + cold,
                hot_before_anchor_mm=hot - anchored,
                anchored_mm=anchored,
                cold_after_anchor_mm=cold,
                loop_y_mm=amp,
            )
        if part.name.startswith(("cap_moving_ceramic_cover", "cover_Resbond", "cap_moving_anchor")):
            shape = shape.cut(pocket).cut(bond)
            for sign in (-1, 1):
                lead, _ = native(replace(variant, lead_diameter=variant.lead_diameter + 0.05), sign)
                # Lead bore clearance .025mm radial; no insulation claim.
                shape = shape.cut(lead.translate((0, 0, dz)))
            if ist and part.name.startswith("cap_moving_anchor"):
                for i in range(4):
                    shape = shape.cut(ist_route(i, dz)[0])
        result.append(b.Part(part.name, shape, part.group, part.envelope))
    result.append(b.Part("RTD_package_ENVELOPE_" + variant.name, chip, "cap"))
    result.append(b.Part("Resbond908_candidate_bond", bond, "cap"))
    for index, sign in enumerate((-1, 1)):
        lead, _ = native(variant, sign)
        result.append(
            b.Part(f"native_Ni_installed_{index}", lead.translate((0, 0, dz)), "cap", True)
        )
    return result, routes


def verify(parts: list, variant: Variant, dz: float) -> dict:
    inspection = b.inspect(parts)
    if not inspection["valid"] or inspection["rigid_intersections"]:
        raise RuntimeError(f"Invalid rigid assembly {variant.name}: {inspection}")
    wires = [p for p in parts if p.name.startswith("PFA_route")]
    natives = [p for p in parts if p.name.startswith("native_Ni")]
    beads = [p for p in parts if p.name.startswith("Cu_Ni")]
    rigid = [p for p in parts if not p.envelope]
    hits = []
    for wire in wires + natives + beads:
        for solid in rigid:
            volume = wire.shape.intersect(solid.shape).Volume()
            # Native leads enter chip at its face; numerical contact must not become overlap.
            if volume > 1e-6 and not (
                wire.name.startswith("native_Ni") and solid.name.startswith("RTD_package")
            ):
                hits.append({"a": wire.name, "b": solid.name, "volume_mm3": volume})
    for i, wire in enumerate(wires):
        for other in wires[i + 1 :]:
            volume = wire.shape.intersect(other.shape).Volume()
            if volume > 1e-6:
                hits.append({"a": wire.name, "b": other.name, "volume_mm3": volume})
    connectivity = []
    for i, bead in enumerate(beads):
        native_index = i // 2
        row = {
            "wire": i,
            "native": native_index,
            "bead_wire_overlap_mm3": bead.shape.intersect(wires[i].shape).Volume(),
            "bead_native_overlap_mm3": bead.shape.intersect(natives[native_index].shape).Volume(),
            "wrong_native_overlap_mm3": bead.shape.intersect(
                natives[1 - native_index].shape
            ).Volume(),
        }
        if (
            row["bead_wire_overlap_mm3"] <= 0
            or row["bead_native_overlap_mm3"] <= 0
            or row["wrong_native_overlap_mm3"] > 1e-8
        ):
            raise RuntimeError(f"Broken electrical topology: {row}")
        connectivity.append(row)
    if hits:
        raise RuntimeError(f"Lead/solid interference {variant.name}: {hits}")
    inspection["lead_wire_intersections"] = hits
    inspection["electrical_topology"] = connectivity
    inspection["contact_status"] = (
        "geometric overlaps only; no electrical/insulation/weld qualification"
    )
    return inspection


def total_volume(parts: list, prefix: str) -> float:
    return sum(p.shape.Volume() for p in parts if p.name.startswith(prefix))


def main() -> None:
    # Preserve the complete R5 scalar schema; derive every changed scalar from B-reps.
    baseline = OUT.parents[1] / "revision5/mechanical/thermal_geometry.csv"
    if not baseline.exists():
        baseline = OUT / "r5_thermal_geometry.csv"
    if (
        hashlib.sha256(baseline.read_bytes()).hexdigest()
        != "420fdbe70bef0dbaf73cb7b03821721cec9e9065e2e85f774eff2d2a9d0219e3"
    ):
        raise RuntimeError("R5 scalar contract identity changed")
    with baseline.open() as stream:
        original = next(row for row in csv.DictReader(stream) if row["variant"] == "D6")
    rows = []
    states = {}
    for variant in VARIANTS:
        states[variant.name] = {}
        for pose, common, local, lift in POSES:
            parts, routes = make(variant, common, local, lift)
            info = verify(parts, variant, -common - local + lift)
            compound = cq.Compound.makeCompound([p.shape for p in parts])
            target = OUT / f"R7-{variant.name}-{pose}.step"
            cq.exporters.export(compound, str(target))
            imported = cq.importers.importStep(str(target)).solids().vals()
            info["step_roundtrip_valid"] = bool(imported) and all(s.isValid() for s in imported)
            info["step_roundtrip_volume_mm3"] = sum(s.Volume() for s in imported)
            info["source_volume_mm3"] = sum(p.shape.Volume() for p in parts)
            if (
                not info["step_roundtrip_valid"]
                or abs(info["step_roundtrip_volume_mm3"] - info["source_volume_mm3"]) > 1e-4
            ):
                raise RuntimeError("STEP parity failed")
            info["routes"] = routes
            states[variant.name][pose] = info
            print(variant.name, pose, "PASS", flush=True)
        parts, routes = make(variant, 0, 0, 0)

        row = dict(original)
        row.update(
            variant=variant.name,
            bond_volume_mm3=total_volume(parts, "Resbond908"),
            bond_footprint_mm2=total_volume(parts, "Resbond908") / variant.bond,
            bond_thickness_mm=variant.bond,
            cover_volume_mm3=total_volume(parts, "cap_moving_ceramic_cover"),
            anchor_pad_volume_mm3=total_volume(parts, "cap_moving_anchor"),
            cover_bond_volume_mm3=total_volume(parts, "cover_Resbond"),
            cover_bond_area_mm2=total_volume(parts, "cover_Resbond") / 0.075,
            wire_hot_length_mm=sum(r["hot_length_mm"] for r in routes) / 4,
            wire_anchor_length_mm=sum(r["anchored_mm"] for r in routes) / 4,
            wire_cold_length_mm=sum(r["cold_length_mm"] for r in routes) / 4,
            native_nickel_length_mm=native(variant, 1)[1],
            native_nickel_diameter_mm=variant.lead_diameter,
            native_lead_volume_mm3=total_volume(parts, "native_Ni"),
            rtd_volume_mm3=total_volume(parts, "RTD_package"),
            rtd_length_mm=variant.y if variant.name.startswith("IST") else variant.x,
            rtd_width_mm=variant.x if variant.name.startswith("IST") else variant.y,
            rtd_height_mm=variant.height,
            rtd_substrate_height_mm=variant.substrate,
            film_path_mm=variant.film_path,
            native_stock_length_mm=7 if variant.name.startswith("IST") else 10,
            native_lead_installation="TRIMMED_FULL_INSTALLED_GEOMETRY_PROCESS_UNQUALIFIED",
            film_orientation="UNKNOWN_PROXY_SENSITIVITY_REQUIRED",
            package_part="P0K1.308.3K.A.007" if variant.name.startswith("IST") else "32208550",
            geometry_status="EXPERIMENTAL_CAD_NOT_PRODUCTION_RELEASE",
            physical_result="NOT_RUN",
        )
        actual_support = total_volume(parts, "ceramic_island")
        if abs(actual_support - float(original["support_volume_mm3"])) > 1e-8:
            raise RuntimeError("R7 rest support differs from R5 baseline")
        row.update(contract_pose="rest", support_volume_mm3=actual_support)
        mx, my, mh = (3.2, 1.0, 0.9) if variant.name.startswith("IST") else (2.5, 2.3, 1.2)
        row.update(
            rtd_max_length_mm=mx,
            rtd_max_width_mm=my,
            rtd_max_height_mm=mh,
            rtd_max_envelope_volume_mm3=mx * my * mh,
        )
        if not variant.name.startswith("IST"):
            preserve_unchanged_baseline(row, original)
        row = {
            key: (round(value, 9) if isinstance(value, float) else value)
            for key, value in row.items()
        }
        rows.append(row)
        section = cq.Compound.makeCompound(
            [
                p.shape.intersect(b.box(70, 35, 120, (0, 17.5, -20)))
                for p in parts
                if p.shape.intersect(b.box(70, 35, 120, (0, 17.5, -20))).Volume() > 1e-8
            ]
        )
        cq.exporters.export(
            section,
            str(OUT / f"R7-{variant.name}-section.svg"),
            opt={
                "width": 900,
                "height": 1000,
                "projectionDir": (0, -1, 0),
                "showAxes": False,
                "showHidden": False,
            },
        )
        # Separate hot-head assembly makes joins/bond available for inspection without hiding the cartridge.
        hot = cq.Compound.makeCompound([p.shape for p in parts if p.group == "cap"])
        cq.exporters.export(hot, str(OUT / f"R7-{variant.name}-head.step"))
    with (OUT / "thermal_geometry.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "geometry.json").write_text(
        json.dumps(
            {
                "stage": "EXPERIMENTAL_CAD_NOT_PRODUCTION_RELEASE",
                "physical_result": "NOT_RUN",
                "states": states,
                "thermal_geometry": rows,
            },
            indent=2,
        )
        + "\n"
    )
    (OUT / "dependency-pins.json").write_text(
        json.dumps(
            {
                "r5_source": {
                    "path": str(source),
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                },
                "r2_source": {
                    "path": str(r5.SOURCE),
                    "sha256": hashlib.sha256(r5.SOURCE.read_bytes()).hexdigest(),
                },
                "r5_geometry": {
                    "path": str(baseline),
                    "sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
                },
            },
            indent=2,
        )
        + "\n"
    )
    for output in [*OUT.glob("R7-*.step"), *OUT.glob("R7-*.svg")]:
        output.write_text(
            "\n".join(line.rstrip() for line in output.read_text().splitlines()) + "\n"
        )


if __name__ == "__main__":
    main()
