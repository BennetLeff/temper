"""Proper native19 placement and candidate right-side catch takeoff, no historical edits."""

from __future__ import annotations

import json

import cadquery as cq
from build_harness import rounded_route, sweep
from build_integration import OUT, ROOT, bounds, box, cylinder, export, hits, read_parts, sha

CATCH_ROUTES = {
    "BUS_P": [
        [135.515488, 207.355491, 38],
        [135, 255, 73],
        [135, 317, 73],
        [-15, 317, 73],
        [-15, 384, 25],
        [17, 384, 25],
    ],
    "HV_RET": [
        [58.37, 192.5, 38],
        [35, 192.5, 38],
        [35, 250, 78],
        [129, 270, 78],
        [129, 335, 78],
        [55.87, 345, 63],
    ],
}


def correct(parts):
    parts = dict(parts)
    source = ROOT / "output/temper-prototype-closure/pcb/temper-power-native19-candidate.step"
    native = read_parts(source)
    native = {("SUBSTRATE" if k.startswith("=>") else k): v for k, v in native.items()}
    replaced = {}
    for k, v in native.items():
        name = "BASE_BASE_native19_" + k
        replaced[name] = "native STEP Rz180 translation[129.5,162,30.387]"
        parts[name] = v.rotate((0, 0, 0), (0, 0, 1), 180).translate((129.5, 162, 30.387))
    for ref, oldx, newx, angle in [("J8", -97.5, 116.5, -112), ("J10", -63.5, 82.5, 180)]:
        for suffix in ["LUG_ENVELOPE", "BOOT_DESIGN"]:
            key = ref + "_" + suffix
            parts[key] = (
                parts[key]
                .rotate((oldx, 192.5, 0), (oldx, 192.5, 1), angle)
                .translate((newx - oldx, 0, 0))
            )
            replaced[key] = {"stud_xy": [newx, 192.5], "rigid_angle_change": angle}
    # Restore only obsolete route apertures from their exact original sweep tools,
    # then recut the candidate. This closes unused openings without changing
    # unrelated mounting holes or the fused-branch ports.
    old_routes = json.loads(
        (ROOT / "output/temper-prototype-closure/round5/protection/route-geometry.json").read_text()
    )["routes"]
    raw_guard = (
        box([19.5, 331, 41.5], [101.5, 38, 39])
        .fuse(box([19.5, 369, 41.5], [101.5, 41, 49]))
        .cut(box([21, 332.5, 41], [98.5, 35, 38]))
        .cut(box([21, 367.5, 41], [98.5, 41, 48]))
    )
    raw_rear = box([-125, 325.5, 10], [267, 1.5, 72])
    for route in old_routes:
        if route["name"] not in CATCH_ROUTES:
            continue
        path, plane, _ = rounded_route(route["control_points_mm"], 22)
        port = sweep(path, plane, 3.5)
        for key, raw in [
            ("REMOVABLE_UPPER_GUARD", raw_guard),
            ("BASE_PROPOSAL_REAR_WALL", raw_rear),
        ]:
            patch = port.intersect(raw)
            if patch.Volume() > 1e-6:
                parts[key] = parts[key].fuse(patch)
                replaced[key] = "Restore obsolete catch apertures, then recut exact corrected route"
    for name in tuple(parts):
        if name.startswith("PAIRED_") or (
            any(name.startswith(n + "_") for n in CATCH_ROUTES)
            and ("COLLAR" in name or "WIRE_MAX" in name)
        ):
            parts.pop(name)
            replaced[name] = "new catch route or right-side support"
    parts["CC1_HV_RET_M4_RING_LUG_CANDIDATE"] = box([55.87, 348.84, 56], [28.13, 0.76, 8]).cut(
        cylinder([80, 344, 60], [80, 352, 60], 2.15)
    )
    parts["CC1_HV_RET_COPPER_M4_WASHER_1p5"] = cylinder([80, 349.6, 60], [80, 351.1, 60], 4).cut(
        cylinder([80, 349, 60], [80, 352, 60], 2.15)
    )
    parts["CC1_HV_RET_M4_NUT_ENVELOPE"] = cylinder([80, 345.64, 60], [80, 348.84, 60], 4.05).cut(
        cylinder([80, 344, 60], [80, 350, 60], 2.15)
    )
    routes = {}
    wires = {}
    ports = {}
    for name, points in CATCH_ROUTES.items():
        path, plane, margins = rounded_route(points, 22)
        wires[name + "_INSULATED_WIRE_MAX"] = sweep(path, plane, 3.937 / 2)
        ports[name] = sweep(path, plane, 3.5)
        ref = "J8" if name == "BUS_P" else "J10"
        # Custom boot candidate channel follows the actual cable departure.
        # Material, minimum wall and crimp lead-entry are qualification holds.
        parts[ref + "_BOOT_DESIGN"] = parts[ref + "_BOOT_DESIGN"].cut(sweep(path, plane, 2.15))
        routes[name] = {
            "points_mm": points,
            "length_mm": path.Length(),
            "tangent_margins_mm": margins,
            "sampled_centerline_mm": [list(path.positionAt(i / 400).toTuple()) for i in range(401)],
        }
    # New exact ports in candidate-only walls. Old unused openings require blanking
    # inserts; rebuilt guard inputs will supersede these historical perforations.
    for guard in ["LOWER_CARRIER", "REMOVABLE_UPPER_GUARD", "BASE_PROPOSAL_REAR_WALL"]:
        old = parts[guard]
        for name, port in ports.items():
            collar = port.intersect(old)
            if collar.Volume() > 1e-5:
                path, plane, _ = rounded_route(CATCH_ROUTES[name], 22)
                parts[name + "_" + guard + "_RIGID_ROUTE_COLLAR"] = collar.cut(
                    sweep(path, plane, 2.1)
                )
                parts[guard] = parts[guard].cut(port)
    saddle = box([122, 287, 70], [18, 10, 11])
    for x, z in [(135, 73), (129, 78)]:
        saddle = saddle.cut(cylinder([x, 286, z], [x, 298, z], 2.15))
    parts["PAIRED_WIRE_SADDLE_LOWER"] = saddle.intersect(box([121, 286, 69], [20, 12, 6.5]))
    parts["PAIRED_WIRE_SADDLE_UPPER"] = saddle.intersect(box([121, 286, 75.5], [20, 12, 6.5]))
    parts["PAIRED_SADDLE_BASE"] = box([122, 281, 68], [18, 19, 2])
    for y in [285, 295]:
        x = 135.5
        parts[f"PAIRED_SADDLE_PEEK_POST_{y}"] = cylinder([x, y, 16], [x, y, 68], 2.5).cut(
            cylinder([x, y, 15], [x, y, 69], 1.7)
        )
        rail = next(
            k for k, v in parts.items() if "CARRIER_RAIL_" in k and bounds(v)[0] < x < bounds(v)[3]
        )
        for obsolete_y in [285, 293]:
            parts[rail] = parts[rail].fuse(
                cylinder([138, obsolete_y, 10], [138, obsolete_y, 16], 1.25)
            )
        if y == 285:
            for obsolete_y in [285, 295]:
                parts[rail] = parts[rail].fuse(
                    cylinder([135.5, obsolete_y, 10], [135.5, obsolete_y, 16], 1.25)
                )
        parts[rail] = parts[rail].cut(cylinder([x, y, 9], [x, y, 17], 1.25))
        parts["PAIRED_SADDLE_BASE"] = (
            parts["PAIRED_SADDLE_BASE"]
            .cut(cylinder([x, y, 67], [x, y, 71], 1.7))
            .cut(cq.Solid.makeCone(1.7, 2.9, 1.2, cq.Vector(x, y, 68.8)))
        )
        parts[f"PAIRED_POST_M3x60_CS_{y}"] = cylinder([x, y, 10], [x, y, 68.6], 1.5).fuse(
            cq.Solid.makeCone(1.5, 2.9, 1.4, cq.Vector(x, y, 68.6))
        )
    for y in [289.5, 294.5]:
        x = 124.5
        for name, r in [("PAIRED_WIRE_SADDLE_UPPER", 1.1), ("PAIRED_WIRE_SADDLE_LOWER", 0.8)]:
            parts[name] = parts[name].cut(cylinder([x, y, 72.5], [x, y, 82], r))
        parts["PAIRED_WIRE_SADDLE_UPPER"] = parts["PAIRED_WIRE_SADDLE_UPPER"].cut(
            cq.Solid.makeCone(1.1, 2, 0.9, cq.Vector(x, y, 80.1))
        )
        parts[f"PAIRED_CLOSURE_M2x8_{y}"] = cylinder([x, y, 73], [x, y, 80], 1).fuse(
            cq.Solid.makeCone(1, 2, 1, cq.Vector(x, y, 80))
        )
        # Loose locating dowel holes prevent assembly shear; screw force / flexure
        # still requires the declared material and pull/temperature coupon.
        if y == 289.5:
            x = 138.5
            for name in ["PAIRED_WIRE_SADDLE_UPPER", "PAIRED_WIRE_SADDLE_LOWER"]:
                parts[name] = parts[name].cut(cylinder([x, y, 74], [x, y, 77.5], 0.8))
            parts[f"PAIRED_LOCATING_DOWEL_{y}"] = cylinder([x, y, 74.2], [x, y, 77.3], 0.75)
    # One machined PEEK piece: no unsecured lower saddle resting on a base.
    # Explicit driver wells reach both recessed mount heads before wires are fitted.
    parts["PAIRED_WIRE_SADDLE_LOWER"] = (
        parts["PAIRED_WIRE_SADDLE_LOWER"].fuse(parts.pop("PAIRED_SADDLE_BASE")).clean()
    )
    for y in [285, 295]:
        for key in ["PAIRED_WIRE_SADDLE_LOWER", "PAIRED_WIRE_SADDLE_UPPER"]:
            parts[key] = parts[key].cut(cylinder([135.5, y, 70], [135.5, y, 83], 3.1))
    assert len(parts["PAIRED_WIRE_SADDLE_LOWER"].Solids()) == 1
    parts["CC1_HV_RET_STRIPPED_TERMINATION_ENVELOPE"] = cylinder(
        [55.87, 345, 63], [58, 349.22, 60], 1.024
    )
    parts.update(wires)
    return parts, {
        "source_step_sha256": sha(source),
        "step_rotation_matrix": [[-1, 0, 0], [0, -1, 0], [0, 0, 1]],
        "step_translation_mm": [129.5, 162, 30.387],
        "determinant": 1,
        "component_side_normal_world": [0, 0, 1],
        "replacement_records": replaced,
        "catch_routes": routes,
        "saddle_construction": "ONE_MACHINED_PEEK_LOWER_AND_BASE_SOLID",
        "saddle_mount_axes_xy": [[135.5, 285], [135.5, 295]],
        "superseded_mount_map": {
            "PAIRED_POST_M3x60_CS_285": "PAIRED_POST_M3x60_CS_285",
            "PAIRED_POST_M3x60_CS_295": "PAIRED_POST_M3x60_CS_295",
        },
        "mount_driver_wells": {
            "diameter_mm": 6.2,
            "axis_xy": [[135.5, 285], [135.5, 295]],
            "open_from_z_mm": 70,
            "sequence": "Tighten mounts before wires; removal requires wire/terminal release.",
        },
        "saddle_service": "Guide only, not axial restraint: closed bores require threading before terminal formation and terminal release for removal. Qualify independent strain relief.",
        "catch_support_fasteners": {
            "post_centers_xy": [[135.5, 285], [135.5, 295]],
            "post_M3x60_countersunk_head_top_z": 70,
            "rail_thread_depth_mm": 6,
            "closure_M2x8_xy": [[124.5, 289.5], [124.5, 294.5]],
            "lower_half_thread_depth_mm": 2.5,
            "locating_dowels_xy": [[138.5, 289.5]],
            "qualification": "PEEK pull/flexure/thermal creep and screw torque not qualified",
        },
        "CC1_return_termination": {
            "jacket_end_mm": [55.87, 345, 63],
            "bare_termination_end_mm": [58, 349.22, 60],
            "ring_lug_plate_mm": [55.87, 348.84, 56, 28.13, 0.76, 8],
            "washer_OD_ID_thickness_mm": [8, 4.3, 1.5],
            "nut_envelope_OD_thickness_mm": [8.1, 3.2],
            "status": "Exact crimp/lead-entry/boot/torque qualification required; termination envelope is not a released solder or crimp process",
        },
    }


def main():
    source = (
        ROOT
        / "output/temper-prototype-closure/round5/protection/catch-with-power-interposer-review.step"
    )
    base = read_parts(source)
    parts, receipt = correct(base)
    changed = {
        k: v
        for k, v in parts.items()
        if k.startswith(("BASE_BASE_native19_", "J8_", "J10_", "PAIRED_", "BUS_P_", "HV_RET_"))
    }
    fixed = {k: v for k, v in parts.items() if k not in changed}
    # Only intentional source-stud/lug contact pairs are omitted from this screen.
    receipt["changed_vs_retained"] = hits(changed, fixed)
    receipt["catch_vs_native"] = hits(
        {k: v for k, v in changed.items() if not k.startswith("BASE_BASE_native19_")},
        {
            k: v
            for k, v in changed.items()
            if k.startswith("BASE_BASE_native19_")
            and k not in ["BASE_BASE_native19_J8", "BASE_BASE_native19_J10"]
        },
    )
    receipt["export"] = export("r4-rigid-catch-CORRECTION-IN-PROGRESS", parts)
    (OUT / "rigid-catch-correction.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in receipt.items()
                if k in ["changed_vs_retained", "catch_vs_native", "export"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
