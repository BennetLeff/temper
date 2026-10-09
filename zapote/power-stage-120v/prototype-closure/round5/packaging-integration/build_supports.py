"""Candidate drill/fastener ECOs; never changes an input STEP or native PCB."""

from __future__ import annotations

import json

import cadquery as cq
from build_integration import OUT, bounds, box, cylinder, export, hits, read_parts, sha


def bolt(a, axis, length, diameter, head_d, head_h):
    a = cq.Vector(*a)
    u = cq.Vector(*axis)
    return cylinder(a.toTuple(), (a + u * length).toTuple(), diameter / 2).fuse(
        cylinder((a - u * head_h).toTuple(), a.toTuple(), head_d / 2)
    )


def main():
    (OUT / "support-receipt.json").write_text('{"status":"INCOMPLETE"}\n')
    spaces = {
        k: read_parts(OUT / f"{k}-nine-board-integration-candidate.step") for k in ("r4", "pod")
    }
    original = {k: dict(v) for k, v in spaces.items()}
    new = {k: {} for k in spaces}
    changed = {k: {} for k in spaces}
    records = []

    def cut(space, name, tool, reason):
        old = spaces[space][name]
        spaces[space][name] = old.cut(tool)
        changed[space][name] = {
            "reason": reason,
            "removed_mm3": old.Volume() - spaces[space][name].Volume(),
        }

    floor = "BASE_BASE_R4_two_bend_bottom_and_sides"
    # Front tray is retained by four blind-threaded guard posts, from below and above.
    for x, y in [(-86, 26), (131, 26), (-86, 70), (131, 80)]:
        ztop = 24 if (x, y) == (-86, 26) else 43
        key = f"FRONT_GUARD_INSULATING_TIE_POST_{x}_{y}"
        spaces["r4"][key] = (
            cylinder((x, y, 12), (x, y, ztop), 3)
            .cut(cylinder((x, y, 11), (x, y, 17.2), 1.5))
            .cut(cylinder((x, y, ztop - 5.2), (x, y, ztop + 1), 1.5))
        )
        cut(
            "r4",
            floor,
            cylinder((x, y, 7), (x, y, 11), 1.7),
            "Four new Ø3.4 floor holes; canonical source unchanged",
        )
        new["r4"][f"FRONT_FLOOR_M3x8_{x}_{y}"] = bolt((x, y, 8), (0, 0, 1), 8, 3, 5.5, 2)
        new["r4"][f"FRONT_PEEK_SHIM_{x}_{y}"] = cylinder((x, y, 10), (x, y, 10.5), 3).cut(
            cylinder((x, y, 9), (x, y, 11), 1.7)
        )
        new["r4"][f"FRONT_GUARD_PEEK_M3x6_{x}_{y}"] = bolt(
            (x, y, ztop + 1), (0, 0, -1), 6, 3, 5.5, 2
        )
        records.append(
            {
                "id": key,
                "xy": [x, y],
                "floor_hole_d": 3.4,
                "post_length": ztop - 12,
                "post_blind_threads": "M3 × 5.2 deep each end; nominal thread void modeled at Ø3",
                "bottom_screw": "M3×8; 4 mm engagement",
                "top_screw": "SIP-M3-6-PEEK; 5 mm engagement",
            }
        )
    coords = json.loads((OUT / "installation-coordinates.json").read_text())
    # Board fasteners follow actual NPTH positions. Recessed pan heads avoid the narrow floor gap.
    for key, r in coords.items():
        space = r["space"]
        axis = (0, -1, 0) if space == "pod" else (-1, 0, 0) if key == "catch" else (0, 0, 1)
        for i, m in enumerate(r["mounts"], 1):
            pos = cq.Vector(*m["substrate_underside_world"])
            u = cq.Vector(*axis)
            dia = 3 if key == "central" else 2.5
            hd = 5.5 if dia == 3 else 4.5
            hh = 2 if dia == 3 else 1.7
            if key == "out":
                a = (pos.x, pos.y, 67.5)
                length = 12
            elif key in ("bus", "tank"):
                panel = "OUT_SENSOR_TRAY" if key == "out" else "FRONT_SENSOR_REMOVABLE_TRAY"
                bottom = pos.z - 5.5
                bearing = bottom + 1.8
                boss = cylinder((pos.x, pos.y, bottom + 1.5), (pos.x, pos.y, bottom + 3), 3.5)
                spaces[space][panel] = spaces[space][panel].fuse(boss)
                cut(
                    space,
                    panel,
                    cylinder((pos.x, pos.y, bottom - 1), (pos.x, pos.y, bearing), 2.35),
                    "Ø4.7 × 1.8 pan-head recess with integral Ø7 boss",
                )
                cut(
                    space,
                    panel,
                    cylinder((pos.x, pos.y, bearing), (pos.x, pos.y, pos.z), 1.35),
                    "M2.5 board bolt clearance",
                )
                spaces[space][f"{key}_NONCONDUCTIVE_STANDOFF_{i}"] = cylinder(
                    (pos.x, pos.y, bottom + 3), pos.toTuple(), 2.5
                ).cut(cylinder((pos.x, pos.y, bottom + 2), (pos.x, pos.y, pos.z + 1), 1.35))
                a = (pos.x, pos.y, bearing)
                length = 10
            elif key == "catch":
                a = (121, pos.y, pos.z)
                length = 12
                cut(
                    space,
                    "REMOVABLE_UPPER_GUARD",
                    cylinder((117, pos.y, pos.z), (125, pos.y, pos.z), 1.45),
                    "Three catch-card M2.5 through holes clamp rail to removable guard",
                )
            else:
                panel_y = 192 if key in ("line", "pre") else 82
                a = (pos.x, panel_y, pos.z)
                length = 25 if key in ("central", "line", "pre") else 20
            new[space][f"{key}_PEEK_BOARD_BOLT_{i}"] = bolt(a, axis, length, dia, hd, hh)
            # Custom PEEK round nut reservation; thread engagement specified independently.
            n = pos + u * 1.6
            thick = 2.4 if dia == 3 else 2
            new[space][f"{key}_PEEK_BOARD_NUT_{i}"] = cylinder(
                n.toTuple(), (n + u * thick).toTuple(), 3.2 if dia == 3 else 2.9
            ).cut(cylinder((n - u).toTuple(), (n + u * (thick + 1)).toTuple(), dia / 2))
            records.append(
                {
                    "id": f"{key}_board_mount_{i}",
                    "board_bottom_mm": pos.toTuple(),
                    "screw_bearing_mm": a,
                    "direction": axis,
                    "thread_d_mm": dia,
                    "length_mm": length,
                    "nut_material": "unfilled PEEK candidate; torque/creep qualification required",
                }
            )
    # Four backplate posts support the removable supervisor panel.
    pod = spaces["pod"]
    back = next(k for k in pod if "BACKPLATE" in k)

    def podpost(name, x, z, front, length, dia=4):
        end = front + length
        p = cylinder((x, front, z), (x, end, z), 6 if dia == 4 else 5)
        p = (
            p.cut(cylinder((x, front - 1, z), (x, front + 8.5, z), dia / 2)).cut(
                cylinder((x, end - 8.5, z), (x, end + 1, z), dia / 2)
            )
            if length > 17
            else p.cut(cylinder((x, front - 1, z), (x, end + 1, z), dia / 2))
        )
        new["pod"][name] = p
        for panel in [
            "SUPERVISOR_REMOVABLE_INSULATING_PANEL",
            "CT_INSULATING_PANEL",
            "VOLTAGE_SENSOR_PANEL",
            back,
        ]:
            if panel in pod:
                cut(
                    "pod",
                    panel,
                    cylinder((x, front - 4, z), (x, end + 4, z), dia / 2 + 0.25),
                    "Support-frame fastener clearance",
                )
        new["pod"][name + "_FRONT_SCREW"] = bolt(
            (x, front - 2, z),
            (0, 1, 0),
            10 if length > 17 else 6,
            dia,
            7 if dia == 4 else 5.5,
            4 if dia == 4 else 2,
        )
        if length > 17:
            new["pod"][name + "_BACK_SCREW"] = bolt((x, end + 3, z), (0, -1, 0), 10, dia, 7, 4)
        records.append(
            {
                "id": name,
                "axis_y": [front, end],
                "x": x,
                "z": z,
                "panel_hole_d": dia + 0.5,
                "material": "6061-T6 with dedicated PE continuity provision; not insulation",
            }
        )

    for x in (29, 306):
        for z in (34, 248):
            podpost(f"CENTRAL_FRAME_POST_{x}_{z}", x, z, 82, 118)
    # CT carrier shares the front frame on its left; right posts avoid the AUX supply.
    for z in (129, 166):
        podpost(f"CT_OUTER_FRAME_POST_{z}", 469, z, 82, 118)
    for z in (130, 148):
        bridge = box((301, 82, z - 5), (39, 3, 10))
        for x in (306, 329):
            bridge = bridge.cut(cylinder((x, 79, z), (x, 86, z), 1.7))
            for panel in ("SUPERVISOR_REMOVABLE_INSULATING_PANEL", "CT_INSULATING_PANEL"):
                cut(
                    "pod",
                    panel,
                    cylinder((x, 79, z), (x, 86, z), 1.7),
                    "M3 CT-to-central removable bridge",
                )
            new["pod"][f"CT_BRIDGE_M3_{x}_{z}"] = bolt((x, 80, z), (0, 1, 0), 8, 3, 5.5, 2)
            new["pod"][f"CT_BRIDGE_NUT_{x}_{z}"] = cylinder((x, 85, z), (x, 87.4, z), 3.2).cut(
                cylinder((x, 84, z), (x, 89, z), 1.5)
            )
        new["pod"][f"CT_PEEK_BRIDGE_{z}"] = bridge
    # Rear card panel: through bolts and locking nuts behind backplate; short posts cannot accept opposed blind screws.
    for x in (387, 453):
        for z in (361, 468):
            name = f"VOLTAGE_PANEL_SPACER_{x}_{z}"
            new["pod"][name] = cylinder((x, 192, z), (x, 200, z), 5).cut(
                cylinder((x, 191, z), (x, 201, z), 1.7)
            )
            for panel in ("VOLTAGE_SENSOR_PANEL", back):
                cut(
                    "pod",
                    panel,
                    cylinder((x, 189, z), (x, 204, z), 1.7),
                    "M3 through-bolt for rear card carrier",
                )
            new["pod"][name + "_M3x18"] = bolt((x, 190, z), (0, 1, 0), 18, 3, 5.5, 2)
            new["pod"][name + "_NUT"] = cylinder((x, 203, z), (x, 205.4, z), 3.2).cut(
                cylinder((x, 202, z), (x, 207, z), 1.5)
            )
    # Reject the narrow D22/PE side slot. The accepted alternative uses two
    # front posts through local *candidate* hood apertures, clear of the PE path.
    frame = (
        box((-131, 327, 67.5), (6, 83, 2))
        .fuse(box((-76, 327, 67.5), (6, 83, 2)))
        .fuse(box((-131, 375, 67.5), (61, 6, 2)))
    )
    frame = frame.fuse(box((-131, 327, 63.5), (2, 83, 4))).fuse(box((-76, 327, 63.5), (2, 83, 4)))
    # Board screws now pass through tray and frame, capturing the complete stack.
    for m in coords["out"]["mounts"]:
        x, y, _ = m["substrate_underside_world"]
        frame = frame.cut(cylinder((x, y, 63), (x, y, 71), 1.35)).cut(
            cylinder((x, y, 63), (x, y, 67.5), 2.4)
        )
    for x in (-128, -73):
        # Machined bracket steps underneath the PE allocation (Z16..17), then
        # rises at Y328..331, between PE end327 and filter front332.
        bx = x - 1.5 if x == -128 else x
        foot = box((bx - 6, 312, 10), (12, 19, 5))
        bracket = foot.fuse(box((bx - 6, 328, 15), (12, 3, 49.5))).fuse(
            box((bx - 6, 328, 64.5), (12, 10, 3))
        )
        for xx in (bx - 3.5, bx + 3.5):
            cut(
                "r4",
                floor,
                cylinder((xx, 316, 7), (xx, 316, 11), 1.7),
                "OUT bracket floor anchors beneath the native-board rear edge",
            )
            bracket = bracket.cut(cylinder((xx, 316, 9), (xx, 316, 14.5), 1.5))
            new["r4"][f"OUT_FLOOR_M3x6_{xx}"] = bolt((xx, 316, 8), (0, 0, 1), 6, 3, 5.5, 2)
        bracket = bracket.cut(cylinder((x, 335, 64.5), (x, 335, 68), 1.5))
        frame = frame.cut(box((bx - 6.1, 327.9, 63), (12.2, 10.2, 4.5))).cut(
            cylinder((x, 335, 67), (x, 335, 71), 1.7)
        )
        for wall in ("BASE_PROPOSAL_LEFT_WALL", "BASE_PROPOSAL_REAR_WALL"):
            old = spaces["r4"][wall]
            aperture = box((bx - 6.2, 311.8, 9.8), (12.4, 19.4, 5.4))
            if old.intersect(aperture).Volume() > 1e-6:
                cut("r4", wall, aperture, "Local lower-edge hood notch for OUT bracket foot")
                seal = old.intersect(aperture).cut(foot)
                new["r4"][f"OUT_FOOT_EDGE_SEAL_{x}_{wall}"] = seal
        new["r4"][f"OUT_MACHINED_BRACKET_{x}"] = bracket
        new["r4"][f"OUT_FRAME_M3x5_{x}"] = bolt((x, 335, 69.5), (0, 0, -1), 5, 3, 5.5, 2)
        records.append(
            {
                "id": f"OUT_CANTILEVER_{x}",
                "floor_holes_xy_d": [[bx - 3.5, 316, 3.4], [bx + 3.5, 316, 3.4]],
                "foot_bounds_mm": [bx - 6, 312, 10, bx + 6, 331, 15],
                "upright_bounds_mm": [bx - 6, 328, 15, bx + 6, 331, 64.5],
                "top_flange_bounds_mm": [bx - 6, 328, 64.5, bx + 6, 338, 67.5],
                "top_screw_xy": [x, 335],
                "material": "Machined 6061-T6 angle bracket and 2 mm downstand frame; independent PE continuity required",
                "mechanical_target": "Foot top15 versus PE allocation bottom16; upright front328 versus PE end327; upright rear331 versus filter front332: each1.0 mm nominal. Frame web bottom63.5 versus cover62:1.5 mm. Combined adverse variation <=0.6 mm required.",
            }
        )
    new["r4"]["OUT_CANTILEVER_FRAME"] = frame
    for x in (-128, -73):
        names = [k for k in new["r4"] if k.startswith(f"OUT_FOOT_EDGE_SEAL_{x}_")]
        if names:
            seal = new["r4"].pop(names[0])
            for n in names[1:]:
                seal = seal.fuse(new["r4"].pop(n))
            new["r4"][f"OUT_FOOT_EDGE_SEAL_{x}"] = seal
    checks = {
        k: {
            "new_vs_retained": hits(new[k], spaces[k]),
            "new_cross": [],
            "added_material_vs_retained": [],
        }
        for k in spaces
    }
    for sp in spaces:
        for name, shape in spaces[sp].items():
            if shape is original[sp][name]:
                continue
            delta = shape.cut(original[sp][name])
            if delta.Volume() > 1e-6:
                checks[sp]["added_material_vs_retained"] += hits(
                    {name: delta}, {k: v for k, v in spaces[sp].items() if k != name}
                )
    for key, record in coords.items():
        space = record["space"]
        for conn in record["connectors"]:
            ref = conn["ref"]
            if not (
                key == "central"
                or (key in ("iproof", "iline") and ref == "J1")
                or (key not in ("central", "iproof", "iline") and ref == "J2")
            ):
                continue
            pts = [p["world_mm"] for p in conn["pads"]]
            lo = [min(p[i] for p in pts) - 4 for i in range(3)]
            hi = [max(p[i] for p in pts) + 4 for i in range(3)]
            normal_axis = 1 if space == "pod" else 0 if key == "catch" else 2
            origin = record["translation_mm"][normal_axis]
            if normal_axis in (0, 1):
                lo[normal_axis], hi[normal_axis] = origin - 25.2, origin - 10.2
            else:
                lo[normal_axis], hi[normal_axis] = origin + 10.2, origin + 25.2
            envelope = box(lo, [hi[i] - lo[i] for i in range(3)])
            checks[space].setdefault("new_vs_connector_access", []).extend(
                hits(new[space], {key + "_" + ref: envelope})
            )
    distances = []
    for name in ("OUT_MACHINED_BRACKET_-128", "OUT_MACHINED_BRACKET_-73", "OUT_CANTILEVER_FRAME"):
        for target in (
            "BASE_BASE_R2_PE_BOND_ROUTE_ALLOCATION",
            "BASE_BASE_R2_FILTER_INSULATING_COVER_ALLOCATION",
            next(k for k, v in spaces["r4"].items() if "CARRIER_RAIL_" in k and bounds(v)[3] < 0),
        ):
            distances.append(
                {
                    "new": name,
                    "retained": target,
                    "nominal_distance_mm": new["r4"][name].distance(spaces["r4"][target]),
                }
            )
    (OUT / "support-critical-distances.json").write_text(
        json.dumps(
            {"status": "MECHANICAL_DISTANCES_NOT_INSULATION_ACCEPTANCE", "pairs": distances},
            indent=2,
        )
        + "\n"
    )
    for space in spaces:
        ns = list(new[space])
        for i, a in enumerate(ns):
            for b in ns[i + 1 :]:
                checks[space]["new_cross"] += hits({a: new[space][a]}, {b: new[space][b]})
    for sp, c in checks.items():
        for hit in c["new_vs_retained"]:
            hit["intersection_bounds_mm"] = bounds(
                new[sp][hit["new"]].intersect(spaces[sp][hit["context"]])
            )
    (OUT / "support-checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    (OUT / "support-patterns.json").write_text(
        json.dumps({"records": records, "candidate_modified_parts": changed}, indent=2) + "\n"
    )
    print(json.dumps(checks, indent=2))
    if any(v for c in checks.values() for v in c.values()):
        raise RuntimeError("Support interference; no export")
    exports = {
        k: export(k + "-supported-integration-candidate", {**spaces[k], **new[k]}) for k in spaces
    }
    (OUT / "support-receipt.json").write_text(
        json.dumps(
            {
                "status": "NOMINAL_CANDIDATE_NOT_RELEASED",
                "power_geometry_status": "RIGID_POWER_CORRECTION_NOMINAL_CHECKS_PASSED",
                "inputs": {
                    k: sha(OUT / f"{k}-nine-board-integration-candidate.step") for k in spaces
                },
                "exports": exports,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
