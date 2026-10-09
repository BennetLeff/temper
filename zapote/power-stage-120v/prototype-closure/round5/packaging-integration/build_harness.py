"""Nominal guarded sense-wire route candidate using native pickoff coordinates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/packaging-integration"
sys.path.insert(0, str(HERE.parents[1] / "round3/packaging"))
from build_integration import cylinder, export, sha  # noqa: E402
from build_proposal import bounds, box, hits, read_parts  # noqa: E402
from build_supports import bolt  # noqa: E402

sys.path.insert(0, str(HERE.parents[1] / "round4/catch"))
from build_carrier import rounded_route  # noqa: E402

ROUTES = {
    "BUS_P": {
        "pickoff": ["C5", "1", "bus_p", [13, 43.95]],
        "points": [[116.5, 205.95, 27], [174, 205.95, 27], [174, 48, 27], [126, 48, 27]],
        "sensor_pad": [122, 48, 17.51],
    },
    "HV_RET": {
        "pickoff": ["C5", "3", "hv_ret", [50.5, 43.95]],
        "points": [[79, 205.95, 21], [174, 205.95, 21], [174, 73, 21], [126, 73, 21]],
        "sensor_pad": [122, 73, 17.51],
    },
    "RES_A": {
        "pickoff": ["C21", "1", "res_a", [234.25, 97]],
        "points": [[-104.75, 259, 27], [-170, 259, 27], [-170, 79, 27], [-76, 79, 27]],
        "sensor_pad": [-72, 79, 17.51],
    },
    "SW_B": {
        "pickoff": ["C21", "2", "sw_b", [191.75, 97]],
        "points": [[-62.25, 259, 20.5], [-176, 259, 20.5], [-176, 34, 20.5], [-76, 34, 20.5]],
        "sensor_pad": [-72, 32, 17.51],
    },
}


def sweep(path, plane, r):
    return (
        cq.Workplane(plane).circle(r).sweep(cq.Workplane().newObject([path]), isFrenet=True).val()
    )


def main():
    (OUT / "harness-receipt.json").write_text('{"status":"INCOMPLETE"}\n')
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    source = (args.source or OUT / "r4-supported-integration-candidate.step").resolve()
    if not source.exists():
        source = OUT / "r4-nine-board-integration-candidate.step"
    pickoffs = json.loads((OUT / "native-pickoffs.json").read_text())
    assert sha(ROOT / pickoffs["source"]) == pickoffs["sha256"], "Native pickoff source drift"
    coordinates = json.loads((OUT / "installation-coordinates.json").read_text())
    for name, route in ROUTES.items():
        ref, pin, net, xy = route["pickoff"]
        rows = [p for p in pickoffs["pickoffs"] if (p["ref"], p["pin"]) == (ref, pin)]
        assert len(rows) == 1 and rows[0]["net"] == net and rows[0]["native_xy_mm"] == xy, name
        key = "bus" if name in ("BUS_P", "HV_RET") else "tank"
        pads = [
            p
            for c in coordinates[key]["connectors"]
            if c["ref"] == "J1"
            for p in c["pads"]
            if p["net"] == name
        ]
        assert len(pads) == 1 and pads[0]["world_mm"] == route["sensor_pad"], name
    base = read_parts(source)
    if "FRONT_GUARD_INSULATING_TIE_POST_-86_79" in base:
        base["FRONT_GUARD_INSULATING_TIE_POST_-86_70"] = base.pop(
            "FRONT_GUARD_INSULATING_TIE_POST_-86_79"
        ).translate((0, -9, 0))
    wire = {}
    guides = {}
    cuts = {}
    receipt = {}
    bores = {}
    flanges = {}
    for name, d in ROUTES.items():
        path, plane, margins = rounded_route(d["points"], 32)
        wire[name + "_WIRE_MAX_OD"] = sweep(path, plane, 2.8956 / 2)
        outer = sweep(path, plane, 2.5)
        inner = sweep(path, plane, 1.65)
        guides[name + "_SPLIT_GUIDE"] = outer.cut(inner)
        cuts[name] = sweep(path, plane, 3.25)
        bores[name] = sweep(path, plane, 2.6)
        flanges[name] = sweep(path, plane, 4.0)
        receipt[name] = {
            **d,
            "length_mm": path.Length(),
            "centerline_radius_mm": 32,
            "minimum_inside_wire_radius_mm": 32 - 2.8956 / 2,
            "required_manufacturer_10D_mm": 28.956,
            "tangent_margins_mm": margins,
            "bounds_mm": bounds(outer),
            "centerline_401_samples": [
                list(path.positionAt(i / 400).toTuple()) for i in range(401)
            ],
        }
    ports = {}
    liners = {}
    fixings = {}
    changes = {}
    # Wall-specific shaped grommets follow the actual sheet faces. The flange retains
    # the insert in its groove; final elastomer material and retention test remain open.
    for part in [
        "BASE_PROPOSAL_LEFT_WALL",
        "BASE_PROPOSAL_RIGHT_WALL",
        "BASE_BASE_R2_LEFT_DUCT",
        "BASE_BASE_R2_RIGHT_DUCT",
    ]:
        old = base[part]
        allcuts = cq.Compound.makeCompound(list(cuts.values()))
        intr = old.intersect(allcuts)
        ports[part] = [bounds(s) for s in intr.Solids()]
        removed = old
        for tool in cuts.values():
            removed = removed.cut(tool)
        base[part] = removed
        # A local 0.7 mm extension of the actual wall face on each side gives two
        # captured flanges. For duct bends, X/Y offsets jointly envelope the sheet.
        thick = old.fuse(old.translate((0.7, 0, 0))).fuse(old.translate((-0.7, 0, 0)))
        if "DUCT" in part:
            thick = thick.fuse(old.translate((0, 0.7, 0))).fuse(old.translate((0, -0.7, 0)))
        liner = None
        for name in ROUTES:
            piece = thick.intersect(flanges[name])
            if piece.Volume() > 1e-6:
                liner = piece if liner is None else liner.fuse(piece)
        # Original metal outside the machined aperture must remain unobstructed.
        liner = liner.cut(removed)
        for bore in bores.values():
            liner = liner.cut(bore)
        liners[part + "_CAPTURED_GROMMET_CANDIDATE"] = liner
        changes[part] = {
            "source_bounds_mm": bounds(old),
            "removed_volume_mm3": old.Volume() - removed.Volume(),
            "aperture_centerline_cut_radius_mm": 3.25,
            "grommet_flange_radius_mm": 4,
            "tube_clear_bore_radius_mm": 2.6,
            "retention": "Custom molded one-piece grooved elastomer insert; thread tube before wire termination. Shape follows the actual wall. Material, insertion and pull-through qualification required.",
        }
    # Four bolted retaining blocks. Bores are cut from the exact tube paths; the
    # nominal bore is a sliding fit, so axial strain relief requires qualified liners.
    floor = "BASE_BASE_R4_two_bend_bottom_and_sides"
    for name, lo, sz, hole, joins in [
        ("BUS_SIDE", [164, 124, 13], [12.6, 12, 18], [167, 130], [[167, 126], [167, 134]]),
        ("BUS_FRONT", [137, 43, 10], [14, 17, 21], [144, 57], [[140, 57], [148, 57]]),
        ("TANK_HIGH", [-106, 69, 10], [12, 13, 20], [-100, 72], [[-104, 72], [-96, 72]]),
        ("TANK_LOW", [-178.6, 64, 10], [12.6, 12, 18], [-169, 70], [[-169, 66], [-169, 74]]),
    ]:
        block = box(lo, sz)
        for bore in bores.values():
            block = block.cut(bore)
        x, y = hole
        top = lo[2] + sz[2]
        length = 10 if name == "BUS_SIDE" else 8
        block = block.cut(cylinder((x, y, 9), (x, y, 8 + length + 0.5), 1.5))
        for j, (jx, jy) in enumerate(joins):
            block = block.cut(cylinder((jx, jy, top - 8.5), (jx, jy, top + 1), 1))
            fixings[name + f"_M2x8_JOIN_{j}"] = bolt((jx, jy, top), (0, 0, -1), 8, 2, 3.8, 1.5)
        if name == "BUS_SIDE":
            base["BASE_BASE_R2_RIGHT_DUCT"] = base["BASE_BASE_R2_RIGHT_DUCT"].cut(
                cylinder((x, y, 11), (x, y, 14), 1.7)
            )
            fixings[name + "_FLOOR_TO_DUCT_SPACER"] = cylinder((x, y, 10), (x, y, 12.2), 3).cut(
                cylinder((x, y, 9), (x, y, 14), 1.7)
            )
        # M3 blind floor screw. An individually removable complete block can be
        # threaded over tubing before soldering; no unsupported snap clamp is claimed.
        base[floor] = base[floor].cut(cylinder((x, y, 7), (x, y, 11), 1.7))
        fixings[name + "_GUIDE_BLOCK_LOWER"] = block.intersect(
            box([lo[0] - 1, lo[1] - 1, lo[2] - 1], [sz[0] + 2, sz[1] + 2, sz[2] - 3])
        )
        fixings[name + "_GUIDE_BLOCK_UPPER"] = block.intersect(
            box([lo[0] - 1, lo[1] - 1, top - 4], [sz[0] + 2, sz[1] + 2, 5])
        )
        fixings[name + f"_M3x{length}"] = bolt((x, y, 8), (0, 0, 1), length, 3, 5.5, 2)
        changes[name] = {
            "block_origin_mm": lo,
            "block_size_mm": sz,
            "floor_hole_xy_d_mm": [x, y, 3.4],
            "joining_holes_xy_mm": joins,
            "split_plane_z_mm": top - 4,
            "assembly": "Machine channels in two halves; two M2×8 joining screws engage 4 mm in lower half. Floor screw engages 5 or6 mm. BUS_SIDE has a 2.2 mm spacer and drilled duct floor. Grip force, material and pull test remain required.",
        }
    checks = {
        "wire_vs_retained": hits(wire, base),
        "guide_vs_retained": hits(guides, base),
        "liner_vs_retained": hits(liners, base),
        "fixings_vs_retained": hits(fixings, base),
        "fixings_vs_wire": hits(fixings, wire),
        "fixings_vs_guides": hits(fixings, guides),
        "wire_pair": [],
        "guide_pair": [],
    }
    checks["fixings_cross"] = []
    fnames = list(fixings)
    for i, a in enumerate(fnames):
        for b in fnames[i + 1 :]:
            checks["fixings_cross"] += hits({a: fixings[a]}, {b: fixings[b]})
    checks["liners_vs_fixings"] = hits(liners, fixings)
    names = list(ROUTES)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            checks["wire_pair"] += hits(
                {a: wire[a + "_WIRE_MAX_OD"]}, {b: wire[b + "_WIRE_MAX_OD"]}
            )
            checks["guide_pair"] += hits(
                {a: guides[a + "_SPLIT_GUIDE"]}, {b: guides[b + "_SPLIT_GUIDE"]}
            )
    margins = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            margins.append(
                {
                    "guide": a,
                    "context": b,
                    "distance_mm": guides[a + "_SPLIT_GUIDE"].distance(guides[b + "_SPLIT_GUIDE"]),
                }
            )
    for a, shape in guides.items():
        bb = bounds(shape)
        for b, other in base.items():
            ob = bounds(other)
            lower = sum(max(0, bb[i] - ob[i + 3], ob[i] - bb[i + 3]) ** 2 for i in range(3)) ** 0.5
            # Conservative centerline-sample broad phase avoids expensive OCC
            # distances to every component inside a route's huge overall box.
            samples = receipt[a.removesuffix("_SPLIT_GUIDE")]["centerline_401_samples"]
            sample_gap = min(
                sum(max(0, ob[i] - p[i], p[i] - ob[i + 3]) ** 2 for i in range(3)) ** 0.5
                for p in samples
            )
            sample_bound = 4.5 + receipt[a.removesuffix("_SPLIT_GUIDE")]["length_mm"] / 400
            if lower < 2 and sample_gap < sample_bound:
                distance = shape.distance(other)
                if distance < 2:
                    margins.append({"guide": a, "context": b, "distance_mm": distance})
    (OUT / "harness-mechanical-margins.json").write_text(
        json.dumps(
            {
                "status": "NOMINAL_MECHANICAL_DISTANCE_NOT_INSULATION_ACCEPTANCE",
                "pairs": sorted(margins, key=lambda r: r["distance_mm"]),
            },
            indent=2,
        )
        + "\n"
    )
    (OUT / "harness-checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    (OUT / "harness-probe.json").write_text(
        json.dumps(
            {"routes": receipt, "checks": checks, "ports": ports, "candidate_changes": changes},
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(checks, indent=2))
    if any(checks.values()):
        raise RuntimeError("Harness interference; no export")
    result = export(
        "r4-supported-routed-candidate", {**base, **wire, **guides, **liners, **fixings}
    )
    floor_result = export("candidate-drilled-floor", {floor: base[floor]})
    (OUT / "harness-receipt.json").write_text(
        json.dumps(
            {
                "status": "NOMINAL_ROUTE_CANDIDATE_NOT_ELECTRICAL_ACCEPTANCE",
                "power_geometry_status": "RIGID_POWER_CORRECTION_NOMINAL_CHECKS_PASSED",
                "input_sha256": sha(source),
                "input": str(source.relative_to(ROOT)),
                "export": result,
                "floor_export": floor_result,
                "native_pickoffs_sha256": sha(OUT / "native-pickoffs.json"),
                "wire": "Alpha 392240 22AWG, maximum OD2.8956 mm; custom 5×3.3 mm PTFE guide-tube candidate",
                "unmodeled": "Underside solder-joint formations and sensor solder terminations are drawing-defined but require physical fit. Guide blocks need a qualified axial strain-relief insert; geometry alone is not a restraint load test.",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
