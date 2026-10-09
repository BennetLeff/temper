"""Rigid CAD assembly adapter for an unreleased nine-board installation candidate."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/packaging-integration"
sys.path.insert(0, str(HERE.parents[1] / "round3/packaging"))
from build_proposal import bounds, box, hits, read_parts  # noqa: E402


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cylinder(a, b, r):
    a, b = cq.Vector(*a), cq.Vector(*b)
    d = b - a
    return cq.Solid.makeCylinder(r, d.Length, a, d.normalized())


def export(name, parts):
    a = cq.Assembly(name=name)
    for k, v in parts.items():
        if not v.isValid():
            raise ValueError(k)
        a.add(
            v, name=k.replace("=>", "BOARD").replace(":", "_").replace("[", "_").replace("]", "_")
        )
    p = OUT / (name + ".step")
    a.export(str(p))
    s = cq.importers.importStep(str(p)).val()
    return {
        "path": str(p.relative_to(ROOT)),
        "sha256": sha(p),
        "solids": len(s.Solids()),
        "valid": s.isValid(),
    }


PLACEMENTS = {
    "central": ("pod", "front", [30, 65, 260]),
    "line": ("pod", "front", [390, 175, 465]),
    "pre": ("pod", "front", [390, 175, 400]),
    "iproof": ("pod", "front", [330, 70, 165]),
    "iline": ("pod", "front", [400, 70, 165]),
    "catch": ("r4", "inward_reverse", [115, 408, 78]),
    "out": ("r4", "flat", [-130, 410, 75]),
    "tank": ("r4", "flat", [-75, 82, 16]),
    "bus": ("r4", "reverse", [125, 45, 16]),
}


def tf(s, rot, xyz):
    if rot == "front":
        s = s.rotate((0, 0, 0), (1, 0, 0), 90)
    if rot == "cyclic":
        s = s.rotate((0, 0, 0), (1, 1, 1), 120)
    if rot == "inward":
        s = s.rotate((0, 0, 0), (1, 1, 1), 120).rotate((0, 0, 0), (0, 1, 0), 180)
    if rot == "inward_reverse":
        s = (
            s.rotate((0, 0, 0), (1, 1, 1), 120)
            .rotate((0, 0, 0), (0, 1, 0), 180)
            .rotate((0, 0, 0), (1, 0, 0), 180)
        )
    if rot == "reverse":
        s = s.rotate((0, 0, 0), (0, 0, 1), 180)
    return s.translate(xyz)


def point(local, rot, xyz):
    x, y, z = local
    if rot == "front":
        x, y, z = x, -z, y
    if rot == "cyclic":
        x, y, z = z, x, y
    if rot == "inward":
        x, y, z = -z, x, -y
    if rot == "inward_reverse":
        x, y, z = -z, -x, y
    if rot == "reverse":
        x, y, z = -x, -y, z
    return [round(a + b, 6) for a, b in zip((x, y, z), xyz, strict=True)]


def main():
    (OUT / "geometry-receipt.json").write_text('{"status":"INCOMPLETE"}\n')
    native = json.loads((OUT / "native-capture.json").read_text())
    source = {
        key: ROOT / "output/temper-prototype-closure/round5/protection" / name
        for key, name in [
            ("pod", "pc125-pod-layout.step"),
            ("r4", "catch-with-power-interposer-review.step"),
        ]
    }
    base = {k: read_parts(v) for k, v in source.items()}
    from merge_rigid_correction import merge, screen

    base["r4"], power_receipt = merge(base["r4"])
    removed = {}
    for key, names in {
        "pod": [
            "PART_K1",
            "PART_K2",
            "PART_KB",
            "PART_CONTROL_ISOLATED_BOARD",
            "PART_FUSE_SERVICE_RESERVATION",
        ],
        "r4": ["SENSE_CARD_OWNER_ALLOCATION"],
    }.items():
        removed[key] = {n: bounds(base[key].pop(n)) for n in names}
    added = {"pod": {}, "r4": {}}
    access = {"pod": {}, "r4": {}}
    boardparts = {}
    records = {}
    for i, key in enumerate(["K1", "K2", "KB", "KPA", "KPB"]):
        added["pod"][key + "_LC1D18BD_CONSERVATIVE_BODY"] = box(
            [40 + 65 * i, 99, 100], [45, 101, 85]
        )
        access["pod"][key + "_TOP_WIRE_ACCESS"] = box([40 + 65 * i, 99, 185], [45, 55, 25])
        access["pod"][key + "_BOTTOM_WIRE_ACCESS"] = box([40 + 65 * i, 99, 75], [45, 55, 25])
    added["pod"]["THREE_FUSE_HOLDERS_SERVICE_ENVELOPE"] = box([375, 100, 205], [70, 100, 90])
    # These are new removable carriers, not changes to the canonical outer shell.
    panels = {
        "pod": {
            "SUPERVISOR_REMOVABLE_INSULATING_PANEL": box([23, 80, 13], [289, 2, 254]),
            "CT_INSULATING_PANEL": box([323, 80, 123], [153, 2, 49]),
            "VOLTAGE_SENSOR_PANEL": box([383, 190, 357], [74, 2, 115]),
        },
        "r4": {
            "FRONT_SENSOR_REMOVABLE_TRAY": box([-90, 22, 10.5], [225, 61, 1.5]),
            "FRONT_SENSOR_TOP_BARRIER": box([-90, 48, 43], [134, 35, 1]),
            "FRONT_SENSOR_LOW_BARRIER": box([-90, 22, 24], [134, 25, 1]),
            "FRONT_SENSOR_STEP_BARRIER": box([-90, 47, 24], [134, 1, 20]),
            "FRONT_SENSOR_RIGHT_HIGH_BARRIER": box([44, 22, 43], [91, 61, 1]),
            "FRONT_SENSOR_SIDE_STEP_BARRIER": box([43, 22, 24], [1, 26, 20]),
            "OUT_SENSOR_TRAY": box([-131, 374, 69.5], [62, 37, 1.5]),
            "CATCH_SENSOR_BACK_RAIL": box([118, 348, 43], [1.5, 60, 35]),
        },
    }
    for key, (space, rot, xyz) in PLACEMENTS.items():
        parts = read_parts(OUT / "boards" / f"{key}.step")
        # Native export lacks these two CT bodies and the U27 package. Explicit drawing-scale reservations.
        if key in ("iproof", "iline"):
            parts["T1_BODY_DRAWING_RESERVATION"] = box([8.1, -14.37, 1.595], [23.8, 11.12, 23.8])
        if key == "central":
            parts["U27_PACKAGE_RESERVATION"] = box([131.4, -162.6, 1.51], [7.2, 7.2, 1.8])
        world = {key + "_" + k: tf(v, rot, xyz) for k, v in parts.items()}
        boardparts[key] = world
        added[space].update(world)
        mounts = []
        standlength = (
            15
            if key in ("central", "line", "pre")
            else 10
            if key in ("iproof", "iline")
            else 3
            if key == "catch"
            else 4
            if key == "out"
            else 4
        )
        # Standoff touches the native substrate underside at local Z=0; drilled platform remains separate.
        for i, m in enumerate(native[key]["mounts"]):
            x, y = m["xy"]
            loc = [x, -y, 0]
            a = [x, -y, -standlength]
            stand = cylinder(a, loc, 2.5).cut(
                cylinder([x, -y, -standlength - 1], [x, -y, 1], m["drill"][0] / 2)
            )
            added[space][f"{key}_NONCONDUCTIVE_STANDOFF_{i + 1}"] = tf(stand, rot, xyz)
            mounts.append(
                {
                    "ref": m["ref"],
                    "diameter_mm": m["drill"][0],
                    "substrate_underside_world": point(loc, rot, xyz),
                    "support_foot_world": point(a, rot, xyz),
                    "stand_length_mm": standlength,
                }
            )
        conn = [f for f in native[key]["footprints"] if f["ref"].startswith("J")]
        for f in conn:
            if (
                (key == "central")
                or (key in ("iproof", "iline") and f["ref"] == "J1")
                or (key not in ("central", "iproof", "iline") and f["ref"] == "J2")
            ):
                # Local native pad extents, not footprint origin assumptions; 15 mm axial mate+wire working reservation.
                xs = [p["xy"][0] for p in f["pads"]]
                ys = [-p["xy"][1] for p in f["pads"]]
                mate = box(
                    [min(xs) - 4, min(ys) - 4, 10.2],
                    [max(xs) - min(xs) + 8, max(ys) - min(ys) + 8, 15],
                )
                access[space][key + "_" + f["ref"] + "_MATE_AND_WIRE_RESERVATION"] = tf(
                    mate, rot, xyz
                )
        records[key] = {
            "space": space,
            "rotation": rot,
            "translation_mm": xyz,
            "source_sha256": native[key]["sha256"],
            "step_sha256": native[key]["step"]["sha256"],
            "bounds_mm": bounds(cq.Compound.makeCompound(list(world.values()))),
            "mounts": mounts,
            "connectors": [
                {
                    "ref": f["ref"],
                    "pads": [
                        {
                            "pin": p["pin"],
                            "net": p["net"],
                            "world_mm": point([p["xy"][0], -p["xy"][1], 1.51], rot, xyz),
                        }
                        for p in f["pads"]
                    ],
                }
                for f in conn
            ],
        }
    floor_drill_pattern = [[-86, 26, 3.4], [131, 26, 3.4], [-86, 70, 3.4], [131, 80, 3.4]]
    for x, y, d in floor_drill_pattern:
        panels["r4"]["FRONT_SENSOR_REMOVABLE_TRAY"] = panels["r4"][
            "FRONT_SENSOR_REMOVABLE_TRAY"
        ].cut(cylinder([x, y, 9], [x, y, 14], d / 2))
        panels["r4"]["FRONT_SENSOR_LOW_BARRIER"] = panels["r4"]["FRONT_SENSOR_LOW_BARRIER"].cut(
            cylinder([x, y, 23], [x, y, 26], d / 2)
        )
        panels["r4"]["FRONT_SENSOR_RIGHT_HIGH_BARRIER"] = panels["r4"][
            "FRONT_SENSOR_RIGHT_HIGH_BARRIER"
        ].cut(cylinder([x, y, 42], [x, y, 45], d / 2))
        panels["r4"]["FRONT_SENSOR_TOP_BARRIER"] = panels["r4"]["FRONT_SENSOR_TOP_BARRIER"].cut(
            cylinder([x, y, 42], [x, y, 45], d / 2)
        )
        added["r4"][f"FRONT_GUARD_INSULATING_TIE_POST_{x}_{y}"] = cylinder(
            [x, y, 12], [x, y, 24 if y == 26 and x < 44 else 43], 3
        ).cut(cylinder([x, y, 11], [x, y, 44], d / 2))
    # Cut the three actual mounting patterns through each custom support panel.
    for space, ps in panels.items():
        for name, shape in list(ps.items()):
            for record in records.values():
                if record["space"] != space:
                    continue
                for mount in record["mounts"]:
                    a = mount["support_foot_world"]
                    b = mount["substrate_underside_world"]
                    d = cq.Vector(*b) - cq.Vector(*a)
                    aa = cq.Vector(*a) - d.normalized() * 4
                    bb = cq.Vector(*b) + d.normalized() * 4
                    shape = shape.cut(
                        cylinder(aa.toTuple(), bb.toTuple(), mount["diameter_mm"] / 2 + 0.15)
                    )
            ps[name] = shape
        added[space].update(ps)
    checks = {}
    for space in base:
        checks[space] = {
            "added_vs_retained": hits(added[space], base[space]),
            "access_vs_retained": hits(access[space], base[space]),
            "access_vs_added": hits(access[space], added[space]),
            "new_board_cross_collisions": [],
            "supports_vs_boards": [],
        }
        names = [k for k, r in records.items() if r["space"] == space]
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                checks[space]["new_board_cross_collisions"] += hits(boardparts[a], boardparts[b])
        checks[space]["supports_vs_boards"] = hits(
            {
                k: v
                for k, v in added[space].items()
                if k in panels[space] or "STANDOFF" in k or "TIE_POST" in k
            },
            {k: v for name in names for k, v in boardparts[name].items()},
        )
    power_checks, termination_contacts = screen(base["r4"] | added["r4"])
    checks["r4"].update(power_checks)
    power_receipt["intentional_termination_contacts"] = termination_contacts
    (OUT / "rigid-power-installation.json").write_text(json.dumps(power_receipt, indent=2) + "\n")
    gap_pairs = [
        (
            "front_low_roof_to_user_lid",
            added["r4"]["FRONT_SENSOR_LOW_BARRIER"],
            base["r4"]["BASE_BASE_R4_front_rear_lid"],
        ),
        (
            "front_high_roof_to_user_lid",
            added["r4"]["FRONT_SENSOR_TOP_BARRIER"],
            base["r4"]["BASE_BASE_R4_front_rear_lid"],
        ),
        (
            "tank_header_leads_to_tray",
            boardparts["tank"]["tank_J2"],
            panels["r4"]["FRONT_SENSOR_REMOVABLE_TRAY"],
        ),
        ("out_header_leads_to_tray", boardparts["out"]["out_J2"], panels["r4"]["OUT_SENSOR_TRAY"]),
        (
            "catch_mate_to_front_boss",
            access["r4"]["catch_J2_MATE_AND_WIRE_RESERVATION"],
            base["r4"]["GUARD_PEEK_BOSS_116_345"],
        ),
        (
            "catch_mate_to_rear_boss",
            access["r4"]["catch_J2_MATE_AND_WIRE_RESERVATION"],
            base["r4"]["GUARD_PEEK_BOSS_95_406"],
        ),
        (
            "central_regulator_to_panel",
            boardparts["central"]["central_U1"],
            panels["pod"]["SUPERVISOR_REMOVABLE_INSULATING_PANEL"],
        ),
        (
            "contactor_to_central_panel",
            added["pod"]["K1_LC1D18BD_CONSERVATIVE_BODY"],
            panels["pod"]["SUPERVISOR_REMOVABLE_INSULATING_PANEL"],
        ),
    ]
    (OUT / "critical-clearances.json").write_text(
        json.dumps(
            {
                "status": "NOMINAL_GEOMETRY_NOT_INSULATION_OR_TOLERANCE_ACCEPTANCE",
                "pairs": [
                    {
                        "id": name,
                        "nominal_gap_mm": a.distance(b),
                        "combined_adverse_variation_limit": "Must be smaller than nominal gap; production tolerance allocation unassigned.",
                    }
                    for name, a, b in gap_pairs
                ],
            },
            indent=2,
        )
        + "\n"
    )
    (OUT / "integration-checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    if any(rows for space in checks.values() for rows in space.values()):
        raise RuntimeError(
            "Nominal interference remains; inspect integration-checks.json before export"
        )
    exports = {
        k: export(k + "-nine-board-integration-candidate", {**base[k], **added[k]}) for k in base
    }
    (OUT / "integration-checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    (OUT / "installation-coordinates.json").write_text(json.dumps(records, indent=2) + "\n")
    receipt = {
        "status": "DESIGN_CANDIDATE_NOT_RELEASED",
        "power_geometry_status": "RIGID_POWER_CORRECTION_NOMINAL_CHECKS_PASSED",
        "rigid_power_installation_sha256": sha(OUT / "rigid-power-installation.json"),
        "power_transform": {
            k: power_receipt[k]
            for k in [
                "step_rotation_matrix",
                "step_translation_mm",
                "determinant",
                "component_side_normal_world",
            ]
        },
        "sources": {
            k: {"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for k, p in source.items()
        },
        "native_capture_sha256": sha(OUT / "native-capture.json"),
        "removed": removed,
        "floor_drill_pattern_proposal_xy_d_mm": floor_drill_pattern,
        "exports": exports,
        "checks": {k: {n: len(v) for n, v in c.items()} for k, c in checks.items()},
    }
    (OUT / "geometry-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
