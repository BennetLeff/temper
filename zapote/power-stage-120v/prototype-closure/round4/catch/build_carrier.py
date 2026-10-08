"""CadQuery adapter for catch carrier, physical bleed card and routed harness.

Declared geometry is nominal. Exported checks deliberately retain collisions and
unresolved terminal landing coordinates; they are not hardware release evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round4/catch"
sys.path.insert(0, str(HERE.parents[1] / "round3/packaging"))
from build_proposal import box, hits, read_parts  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cylinder(a, b, radius):
    start, end = cq.Vector(*a), cq.Vector(*b)
    d = end - start
    return cq.Solid.makeCylinder(radius, d.Length, start, d.normalized())


def rounded_route(points, radius):
    """Fillet a spatial polyline using true circular arcs, checking tangent room."""
    v = [cq.Vector(*p) for p in points]
    corners = []
    for i in range(1, len(v) - 1):
        a = (v[i] - v[i - 1]).normalized()
        b = (v[i + 1] - v[i]).normalized()
        angle = math.acos(max(-1.0, min(1.0, a.dot(b))))
        distance = radius * math.tan(angle / 2)
        center = v[i] + (b - a).normalized() * (radius / math.cos(angle / 2))
        t1, t2 = v[i] - a * distance, v[i] + b * distance
        middle = center + (v[i] - center).normalized() * radius
        corners.append((t1, middle, t2, distance))
    margins = []
    for i in range(len(v) - 1):
        used = (corners[i - 1][3] if i else 0) + (corners[i][3] if i < len(corners) else 0)
        margin = (v[i + 1] - v[i]).Length - used
        margins.append(margin)
        if margin <= 0:
            raise ValueError(f"Route fillets overlap on segment {i}: {margin}")
    edges, current = [], v[0]
    for t1, middle, t2, _ in corners:
        edges.append(cq.Edge.makeLine(current, t1))
        edges.append(cq.Edge.makeThreePointArc(t1, middle, t2))
        current = t2
    edges.append(cq.Edge.makeLine(current, v[-1]))
    path = cq.Wire.assembleEdges(edges)
    plane = cq.Plane(origin=v[0], normal=(v[1] - v[0]).normalized())
    return path, plane, margins


def export(name, parts):
    assembly = cq.Assembly(name=name)
    for key, shape in parts.items():
        if not shape.isValid():
            raise ValueError(f"Invalid part {key}")
        assembly.add(shape, name=key)
    path = OUT / (name + ".step")
    assembly.export(str(path))
    model = cq.importers.importStep(str(path)).val()
    if not model.isValid():
        raise ValueError("STEP reimport invalid")
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha(path),
        "valid_solids": len(model.Solids()),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    receipt = OUT / "carrier-checks.json"
    receipt.write_text('{"status":"INCOMPLETE"}\n')
    d = json.loads((HERE / "interface.json").read_text())
    board_source = ROOT / "zapote/power-stage-120v/native-19/section.kicad_pcb"
    if sha(board_source) != d["native19_sha256"]:
        raise ValueError("Native19 board changed; update integration before rebuilding")
    if d["wire"]["design_bend_radius_mm"] < d["wire"]["minimum_bend_radius_mm"]:
        raise ValueError("Wire bend radius violates selected conductor requirement")
    source = ROOT / d["baseline_step"]
    if sha(source) != d["baseline_step_sha256"]:
        raise ValueError("Round3 source STEP changed")
    all_context = read_parts(source)
    removed = [k for k in all_context if k.startswith("CATCH_CATCH_") or k.startswith("SHELL_")]
    context = {k: v for k, v in all_context.items() if k not in removed}
    context["CATCH_US141_ROTATED"] = context["CATCH_US141_ROTATED"].translate((0, -6, 0))
    parts = {}
    # Existing holder stays in context; capacitor is now accompanied by real leads.
    cap = d["catch_circuit"]["capacitor"]
    parts["CC1_BODY_MAX"] = box(cap["origin_mm"], cap["body_max_mm"])
    for x in (27.5, 80):
        for z in (49.85, 70.15):
            parts[f"CC1_LEAD_{x}_{z}"] = cylinder([x, 349, z], [x, 355, z], 0.625)
    # Pin carrier carries no mass of the capacitor: body cradle + straps below do.
    interposer = box([21, 352.1, 42], [65, 1.6, 36])
    for x in (27.5, 80):
        for z in (49.85, 70.15):
            interposer = interposer.cut(cylinder([x, 351, z], [x, 355, z], 1.4))
        interposer = interposer.cut(cylinder([x, 351, 60], [x, 355, 60], 2.15))
        strap = box([x - 4, 351.1, 46], [8, 1, 28])
        for z, r in ((49.85, 1.4), (70.15, 1.4), (60, 2.15)):
            strap = strap.cut(cylinder([x, 350, z], [x, 354, z], r))
        parts[f"CC1_COPPER_STRAP_{x}"] = strap
        parts[f"CC1_M4_TERMINAL_{x}"] = cylinder([x, 344, 60], [x, 354.6, 60], 2)
    parts["CC1_PIN_CARRIER"] = interposer
    # Body support/contact is intentional. The 1mm layer is a replaceable pad
    # allocation; no compression/temperature rating is asserted.
    parts["CC1_CRADLE_FLOOR"] = box([22, 353, 41.5], [64, 50, 2.5]).cut(interposer)
    parts["CC1_SUPPORT_PAD"] = box([25, 356, 44], [57.5, 43, 1])
    for x in (22, 83.5):
        parts[f"CC1_CRADLE_WALL_{x}"] = box([x, 354, 44], [2.5, 49, 32])
    for x, wall_x in ((23, 22), (84, 83.5)):
        wall_name = f"CC1_CRADLE_WALL_{wall_x}"
        parts[wall_name] = parts[wall_name].fuse(box([x - 1.5, 353.7, 43], [3, 6.3, 35]))
        parts["CC1_CRADLE_FLOOR"] = parts["CC1_CRADLE_FLOOR"].cut(parts[wall_name])
        for z in (44, 76):
            hole = cylinder([x, 351, z], [x, 360, z], 1.1)
            parts["CC1_PIN_CARRIER"] = parts["CC1_PIN_CARRIER"].cut(hole)
            parts[wall_name] = parts[wall_name].cut(hole)
            parts["CC1_CRADLE_FLOOR"] = parts["CC1_CRADLE_FLOOR"].cut(hole)
            parts[f"PIN_CARRIER_M2_{x}_{z}"] = cylinder([x, 351.7, z], [x, 359.7, z], 1)
    for y in (361, 394):
        parts[f"CC1_RETENTION_STRAP_{y}"] = box([22, y, 76], [64, 3, 1.5])
    parts["BLEED_SUPPORT_CROSSBAR"] = box([22, 383, 78.5], [86, 8, 1])
    for x in (22, 83.5):
        parts[f"BLEED_CROSSBAR_RISER_{x}"] = box([x, 383, 76], [2.5, 8, 2.5])
    # Actual resistor bodies and leads tied to the local KiCad placement contract.
    c = d["bleed_card"]
    ox, oy, oz = c["world_origin_mm"]
    board = box([ox, oy, oz], c["size_mm"])
    for x, y, diameter in c["npth_mm"]:
        board = board.cut(
            cylinder([ox + x, oy + y, oz - 1], [ox + x, oy + y, oz + 3], diameter / 2)
        )
        through_hole = cylinder([ox + x, oy + y, 76], [ox + x, oy + y, 82], 1.6)
        parts["BLEED_SUPPORT_CROSSBAR"] = parts["BLEED_SUPPORT_CROSSBAR"].cut(through_hole)
        parts[f"BLEED_PEEK_POST_{x}"] = cylinder(
            [ox + x, oy + y, 79.5], [ox + x, oy + y, 81], 3
        ).cut(through_hole)
        parts[f"BLEED_PEEK_NUT_{x}"] = cylinder(
            [ox + x, oy + y, 76.5], [ox + x, oy + y, 78.5], 2.75
        ).cut(cylinder([ox + x, oy + y, 76], [ox + x, oy + y, 79], 1.4))
        parts[f"BLEED_PEEK_M3_{x}"] = cylinder(
            [ox + x, oy + y, 76.6], [ox + x, oy + y, 82.6], 1.5
        ).fuse(cylinder([ox + x, oy + y, 82.6], [ox + x, oy + y, 84.6], 2.75))
    parts["BLEED_PCB"] = board
    for row, y in enumerate(c["row_y_mm"]):
        for col, x in enumerate(c["resistor_x_mm"]):
            ref = f"R{1 + 4 * row + col}"
            cx, cy, cz = ox + x, oy + y, oz + 1.6 + 2.5
            parts[ref + "_BODY_MAX"] = cylinder([cx + 3, cy, cz], [cx + 12, cy, cz], 2)
            parts[ref + "_COATED_END_MAX"] = cylinder([cx + 1.5, cy, cz], [cx + 13.5, cy, cz], 0.55)
            # Orthogonal formed leads are fabrication centerlines; bend-form
            # process at coated transitions must be approved before build.
            for end in (0, 15):
                parts[f"{ref}_LEAD_{end}"] = cylinder(
                    [cx + end, cy, oz - 1], [cx + end, cy, cz], 0.365
                ).fuse(
                    cylinder([cx + end, cy, cz], [cx + (1.5 if end == 0 else 13.5), cy, cz], 0.365)
                )
    # Sensor remains explicitly separated from the completed bleed board.
    parts["SENSE_CARD_OWNER_ALLOCATION"] = box(
        d["sense_card"]["origin_mm"], d["sense_card"]["max_size_mm"]
    )
    # PG-TO247-3: pin1 NC, pin2 cathode/case, pin3 anode. Conservative
    # body envelope; exact lead-plane and thermal clamp fit remain qualified
    # drawing inputs, not inferred from an unrelated TO247 transistor.
    parts["DC1_TO247_BODY_ENVELOPE"] = box([30, 335, 52], [16, 5.2, 21.1])
    for pin, x in ((1, 32.56), (2, 38), (3, 43.44)):
        parts[f"DC1_PIN_{pin}"] = box([x - 0.65, 338.4, 43], [1.3, 0.8, 9])
    parts["DC1_LOCAL_CARRIER"] = box([29, 333, 44], [32, 17, 1.6])
    for x in (32.56, 38, 43.44):
        parts["DC1_LOCAL_CARRIER"] = parts["DC1_LOCAL_CARRIER"].cut(
            cylinder([x, 338.8, 43], [x, 338.8, 47], 1.0)
        )
    parts["DC1_FLOATING_CATHODE_SPREADER"] = box([25, 340.2, 50], [26, 2, 27])
    # Shaped copper link, 5x1mm nominal cross-section. This is a fabrication
    # proposal, not a selected connector or a pulse-rated production joint.
    cathode_link = (
        box([35.5, 338.8, 46], [5, 9.2, 1])
        .fuse(box([25, 347, 46], [15.5, 1, 5]))
        .fuse(box([25, 347, 46], [5, 1, 16]))
    )
    parts["CATHODE_FORMED_COPPER_LINK"] = cathode_link.cut(
        cylinder([27.5, 346, 60], [27.5, 349, 60], 2.15)
    )
    # Replace obsolete hats with removable 1.5mm guarded upper shell. Front
    # remains removable for holder service; upper cover uses captive M3 screws.
    outer = box([15.5, 328.5, 10], [111, 99, 31.5])
    lower = outer.cut(box([17, 330, 11.5], [108, 96, 31]))
    lower = lower.fuse(box([15.5, 330, 40], [111, 96, 1.5]))
    for x, y in ((23, 334), (118, 334), (23, 424), (118, 424)):
        lower = lower.cut(cylinder([x, y, 9], [x, y, 12], 1.7))
    parts["LOWER_CARRIER"] = lower
    cover = (
        box([19.5, 331, 41.5], [101.5, 38, 39])
        .fuse(box([19.5, 369, 41.5], [101.5, 41, 49]))
        .cut(box([21, 332.5, 41], [98.5, 35, 38]))
        .cut(box([21, 367.5, 41], [98.5, 41, 48]))
    )
    parts["REMOVABLE_UPPER_GUARD"] = cover
    for x, y in ((24.5, 335), (116, 345), (24.5, 406), (95, 406)):
        top = 80.5 if y < 360 else 90.5
        screw = cylinder([x, y, top - 7.5], [x, y, top], 1.5).fuse(
            cylinder([x, y, top], [x, y, top + 2], 2.75)
        )
        parts[f"GUARD_PEEK_BOSS_{x}_{y}"] = cylinder([x, y, 41.5], [x, y, top - 1.5], 2.5).cut(
            cylinder([x, y, top - 9], [x, y, top], 1.4)
        )
        parts[f"GUARD_M3_{x}_{y}"] = screw
        parts["REMOVABLE_UPPER_GUARD"] = parts["REMOVABLE_UPPER_GUARD"].cut(
            cylinder([x, y, 73], [x, y, 93], 1.7)
        )
    # Screw-retained insulated bracket; dedicated vertical DIN rail, no PCB holes.
    parts["DIN35_RAIL_PROPOSED_CUT_LENGTH"] = (
        box([53.2, 425, 12], [28.6, 1, 26.5])
        .fuse(box([53.2, 419.5, 12], [1, 5.5, 26.5]))
        .fuse(box([80.8, 419.5, 12], [1, 5.5, 26.5]))
        .fuse(box([50, 418.5, 12], [4.2, 1, 26.5]))
        .fuse(box([80.8, 418.5, 12], [4.2, 1, 26.5]))
    )
    parts["LOWER_CARRIER"] = parts["LOWER_CARRIER"].fuse(box([45, 426, 11.5], [45, 1.5, 29]))
    # Use the manufacturer 5D minimum, not square routing corners.
    routes = {
        "BUS_P": [
            [-118.397193, 204.565, 36],
            [-116, 255, 73],
            [-116, 317, 73],
            [-15, 317, 73],
            [-15, 384, 25],
            [17, 384, 25],
        ],
        "HV_RET": [
            [-39.37, 192.5, 36],
            [-46.436503223, 250, 78],
            [-110, 270, 78],
            [-110, 322, 78],
            [55, 322, 78],
            [80, 349, 60],
        ],
        "FUSED_P_TO_ANODE": [[124, 384, 25], [138, 384, 55], [138, 338.8, 55], [43.44, 338.8, 48]],
    }
    geometry = []
    ports = {}
    for name, points in routes.items():
        path, plane, margins = rounded_route(points, d["wire"]["design_bend_radius_mm"])
        solid = (
            cq.Workplane(plane)
            .circle(d["wire"]["od_max_mm"] / 2)
            .sweep(cq.Workplane().newObject([path]), isFrenet=True)
            .val()
        )
        parts[name + "_INSULATED_WIRE_MAX"] = solid
        port = (
            cq.Workplane(plane)
            .circle(3.5)
            .sweep(cq.Workplane().newObject([path]), isFrenet=True)
            .val()
        )
        ports[name] = port
        for guard in ("LOWER_CARRIER", "REMOVABLE_UPPER_GUARD"):
            collar = port.intersect(parts[guard])
            if collar.Volume() > 1e-5:
                bore = (
                    cq.Workplane(plane)
                    .circle(2.1)
                    .sweep(cq.Workplane().newObject([path]), isFrenet=True)
                    .val()
                )
                parts[name + "_" + guard + "_SPLIT_PTFE_COLLAR"] = collar.cut(bore)
                parts[guard] = parts[guard].cut(port)
        samples = [list(path.positionAt(i / 400).toTuple()) for i in range(401)]
        geometry.append(
            {
                "name": name,
                "control_points_mm": points,
                "sampled_centerline_mm": samples,
                "length_mm": path.Length(),
                "bend_radius_mm": 22,
                "minimum_tangent_margin_mm": min(margins),
                "od_max_mm": d["wire"]["od_max_mm"],
                "copper_area_mm2": 3.29,
                "terminal_coordinates_are_provisional": name != "HV_RET",
            }
        )
    # Separate native-stud lugs from wire sweeps; dimensions derive from selected
    # 24.13mm TE part, but shape is a conservative envelope, not vendor CAD.
    for name, x in (("J8", -97.5), ("J10", -63.5)):
        angle = 60 if name == "J8" else -90
        lug = (
            box([-4, -4, 0], [8, 28.13, 0.76])
            .cut(cylinder([0, 0, -1], [0, 0, 2], 2.15))
            .rotate((0, 0, 0), (0, 0, 1), angle)
            .translate((x, 192.5, 35))
        )
        parts[name + "_LUG_ENVELOPE"] = lug
        boot = (
            cylinder([0, 0, 0.2], [0, 0, 7], 6.5)
            .cut(cylinder([0, 0, 0], [0, 0, 6], 5.1))
            .fuse(cylinder([0, 5, 3], [0, 27, 3], 3).cut(cylinder([0, 4, 3], [0, 28, 3], 2.15)))
            .rotate((0, 0, 0), (0, 0, 1), angle)
            .translate((x, 192.5, 35))
        )
        parts[name + "_BOOT_DESIGN"] = boot.cut(lug)
    # A split paired-wire saddle transfers pull into two chassis-mounted posts
    # outside the native PCB edge. Copper and Kelvin pads gain no mounting load.
    saddle = box([-121, 289, 70], [18, 6, 11])
    for x, z in ((-116, 73), (-110, 78)):
        saddle = saddle.cut(cylinder([x, 288, z], [x, 296, z], 2.15))
    parts["PAIRED_WIRE_SADDLE_LOWER"] = saddle.intersect(box([-122, 288, 69], [20, 8, 6.5]))
    parts["PAIRED_WIRE_SADDLE_UPPER"] = saddle.intersect(box([-122, 288, 75.5], [20, 8, 6.5]))
    parts["PAIRED_SADDLE_BASE"] = box([-121, 283, 68], [18, 18, 2])
    for y in (285, 293):
        parts[f"PAIRED_SADDLE_PEEK_POST_{y}"] = cylinder([-119, y, 16], [-119, y, 68], 2.5).cut(
            cylinder([-119, y, 15], [-119, y, 69], 1.7)
        )
        rail = "BASE_BASE_R2_CARRIER_RAIL_-122p5"
        context[rail] = context[rail].cut(cylinder([-119, y, 9], [-119, y, 17], 1.25))
    # Dedicated rear-wall apertures track the route intersection; do not make a
    # false no-collision claim by omitting the protective wall from the model.
    wall = "BASE_PROPOSAL_REAR_WALL"
    oldwall = context[wall]
    for name in routes:
        collar = ports[name].intersect(context[wall])
        if collar.Volume() > 1e-5:
            parts[name + "_PCB_HOOD_PTFE_COLLAR"] = collar.cut(parts[name + "_INSULATED_WIRE_MAX"])
        context[wall] = context[wall].cut(ports[name])
    harness = {k: v for k, v in parts.items() if "WIRE_MAX" in k or "LUG_" in k or "BOOT_" in k}
    physical = {k: v for k, v in parts.items() if k not in harness and "ALLOCATION" not in k}
    report = {
        "status": "CONDITIONAL_ENGINEERING_DESIGN_NOT_RELEASED",
        "input_sha256": sha(HERE / "interface.json"),
        "builder_sha256": sha(Path(__file__)),
        "removed_obsolete_parts": removed,
        "harness_vs_context": hits(harness, context),
        "carrier_vs_context": hits(physical, context),
        "sense_allocation_vs_context": hits(
            {"SENSE": parts["SENSE_CARD_OWNER_ALLOCATION"]}, context
        ),
        "rear_wall_removed_volume_mm3": oldwall.Volume() - context[wall].Volume(),
        "routes": geometry,
        "holder_shift_mm": [0, -6, 0],
        "service_requirement": "Remove PCB hood rear service panel and catch front panel after unplugging and verifying all stored nodes discharged; holder opening projection now starts Y324.5 and intersects installed PCB hood.",
        "limits": [
            "Custom split PTFE collars define7mmOD/4.2mmID wall pass-throughs; retention, manufacturing tolerance and material qualification remain open.",
            "US141 terminal centerlines are not dimensioned by its public body drawing; terminal wire endpoints are provisional.",
            "Wire paths are modeled, but exact holder internal current path, terminal joints, diode leads and native bus closure must be included before full-loop inductance is called extracted.",
            "No supplier orientation, diode hot pulse, fuse clearing, laminate insulation or physical temperature result is asserted.",
        ],
    }
    (OUT / "route-geometry.json").write_text(
        json.dumps({"routes": geometry, "wire": d["wire"]}, indent=2) + "\n"
    )
    (OUT / "route-lengths.csv").write_text(
        "name,length_mm\n"
        + "\n".join(f"{r['name']},{r['length_mm']:.12f}" for r in geometry)
        + "\n"
    )
    report["export"] = export("r4-catch-carrier-routed-design", context | parts)
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "routes"}, indent=2))


if __name__ == "__main__":
    main()
