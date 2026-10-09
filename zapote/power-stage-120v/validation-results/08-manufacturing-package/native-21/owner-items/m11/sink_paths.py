"""M11: HOT -> PE distances at the native-21 sink, as built (R25 sink) and for the proposed stack.

  PYTHONDONTWRITEBYTECODE=1 python3 -B sink_paths.py <copper-dump.json> <board-sink-geometry.json> <out.json>

Inputs (read-only):
  copper-dump.json: native-21 stage 11 (board SHA-256 e85a4c82..., same rebuild as D5-AUDIT).
  board-sink-geometry.json: from board_sink_geometry.py (KiCad pcbnew on the same board).
  Net domains: native-21/layout/rules21.py (PE = {'pe'}, SELV, HOT = rules21.GROUP).

Coordinates: board mm, y = 0 is the rear edge, y < 0 is beyond it, z = 0 is the board top (F.Cu),
z = -1.6 the bottom. Enclosure pose (R25 src/electronics_r17.py): world = (141 - x, 236 - y, 26 + z),
so board top = world Z 27.6.

PE solids as modelled in R25 (all bonded to the chassis/PE sink):
  sink envelope  X32..149 Y236..284 Z15.5..83  -> x [-8, 109],  y [-48, 0],  z [-10.5, 57]
  plenum end cap X31 wall forward to Y236 (R21) -> x [109, 110], y [-136, 0], z [-15, 60]
  inlet hood front wall (149,236)->(181,201)    -> line (-8, 0)->(-40, 35), z [-15, 60]
Every one of them spans the board's thickness, so plan-view distance is the clearance and a lower
bound on creepage.

Package data (datasheets, read from validation-results/03-loss-thermal-budget/round3/sources/):
  Infineon IPW65R018CFD7 Rev 2.0 p.12 (PG-TO247-3, Z8B00003327 rev 06):
    A 4.70-5.30, A1 2.20-2.60, c 0.38-0.89, D 20.70-21.50, D1 13.08-17.65, D2 0.51-1.35,
    E 15.50-16.30, E1 12.38-14.15, L1 3.85-4.50, b1 1.60-2.41, b2 2.57-3.43.
  Diodes GBJ2510 DS21221 Rev 11-2 p.1: case dielectric strength 2500 Vrms; p.4 outline.
"""
import json
import math
import sys

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

sys.dont_write_bytecode = True
sys.path.insert(0, "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/native-21/layout")
import rules21  # noqa: E402

TO247 = dict(A=(4.70, 5.30), A1=(2.20, 2.60), c=(0.38, 0.89), D=(20.70, 21.50), D1=(13.08, 17.65),
             D2=(0.51, 1.35), E=(15.50, 16.30), E1=(12.38, 14.15), L1=(3.85, 4.50))
FLOOR = 8.0            # D5-BASIS provisional HOT<->PE floor (reinforced objective)


def dom(net):
    if net in rules21.PE:
        return "PE"
    if net in rules21.SELV:
        return "SELV"
    return "HOT" if net in rules21.GROUP else None


def geoms(d):
    out = []
    for p in d["pads"]:
        if len(p.get("pts", [])) > 2:
            out.append(("pad", p["net"], p.get("ref"), "F+B" if p.get("tht") else "pad", Polygon(p["pts"])))
    for t in d["tracks"]:
        out.append(("track", t["net"], None, t["layer"], LineString([t["a"], t["b"]]).buffer(t["w"] / 2)))
    for v in d["vias"]:
        out.append(("via", v["net"], None, "all", Point(v["at"]).buffer(v["d"] / 2)))
    for z in d["zones"]:
        out.append(("zone", z["net"], None, z["layer"], Polygon(z["pts"], z.get("holes") or [])))
    return [g for g in out if g[1] and dom(g[1]) == "HOT"]


def pe_as_built():
    return {
        "sink (R25 envelope, base face = board edge)": box(-8.0, -48.0, 109.0, 0.0),
        "plenum end cap (R21 X31 wall)": box(109.0, -136.0, 110.0, 0.0),
        "inlet hood front wall (R21)": LineString([(-8.0, 0.0), (-40.0, 35.0)]).buffer(0.5),
    }


def survey(hot, pe):
    rows = []
    for name, solid in pe.items():
        best = {}
        for kind, net, ref, layer, g in hot:
            dd = g.distance(solid)
            if dd > 12:
                continue
            key = (net, layer if kind != "pad" else f"pad {ref}")
            if key not in best or dd < best[key][0]:
                p = g.centroid
                best[key] = (dd, kind, [round(p.x, 2), round(p.y, 2)])
        for (net, layer), (dd, kind, at) in sorted(best.items(), key=lambda kv: kv[1][0]):
            rows.append({"pe_solid": name, "net": net, "layer_or_pad": layer, "kind": kind,
                         "min_mm": round(dd, 3), "at_centroid": at, "pass_8mm": dd >= FLOOR})
    return rows


def proposed(geo, z_s, g, t_ins, o_lat, o_top, edge_cu_y=0.6, bcu_extra=1.6):
    """Path lengths for the proposed stack.

    z_s   : height of the pedestal's lowest PE edge above the board top (mm)
    g     : set-back of the main sink base face behind the board edge (mm), y = -g
    t_ins : insulator thickness (mm); its inner face is the tab plane y = tab_y
    o_lat : insulator overhang beyond the outermost tab-metal edge, along the row (mm)
    o_top : insulator overhang above the tab-metal top edge (mm)
    """
    fets = {r: p for r, p in geo["parts"].items() if r.startswith("Q")}
    tab_y = min(p["fab_bbox_mm"][1] for p in fets.values())
    pad_y = min(q["pad_edge_to_y0_mm"] for p in fets.values() for q in p["pads"])
    ped_face_y = tab_y - t_ins            # pedestal contact face
    res = {"inputs": dict(z_s=z_s, g=g, t_ins=t_ins, o_lat=o_lat, o_top=o_top, tab_y=tab_y,
                          pedestal_face_y=round(ped_face_y, 3), edge_copper_y=edge_cu_y, lead_pad_edge_y=pad_y)}
    paths = {}
    # 1. F.Cu pour at the edge -> along the board top under/past the insulator foot -> up the
    #    insulator's outer face -> pedestal lower edge. If the pedestal face is over the board
    #    (ped_face_y > edge_cu_y) the path is straight up through air.
    # The insulator foot rests on the board; its outer face is at ped_face_y. A path from copper under
    # the foot runs along the (uncemented) joint to the outer face, then up it. Joint paths are taken
    # as both creepage and clearance (the foot blocks the straight line).
    def foot_path(cu_y, extra=0.0):
        if ped_face_y >= cu_y:                       # copper outside the foot: straight line through air
            return math.hypot(ped_face_y - cu_y, z_s) + extra
        return (cu_y - ped_face_y) + z_s + extra
    paths["F.Cu edge pour (y 0.6) -> pedestal lower edge"] = round(foot_path(edge_cu_y), 3)
    # 2. B.Cu edge pour -> round the board edge -> pedestal (creepage), and -> main base face (clearance)
    paths["B.Cu edge pour -> round the board edge -> pedestal lower edge"] = round(edge_cu_y + bcu_extra + max(0.0, -ped_face_y) + z_s, 3)
    paths["B.Cu/In1/In2 edge copper -> set-back sink base face (plan view)"] = round(edge_cu_y + g, 3)
    # 3. Lead pad (F.Cu, y = pad_y) under the insulator foot -> joint -> outer face -> pedestal.
    paths["FET lead pad (y 1.965) -> pedestal lower edge"] = round(foot_path(pad_y), 3)
    # 4. Tab metal edge -> along the insulator face -> round its edge -> pedestal face
    lat_margin_min = (TO247["E"][0] - TO247["E1"][1]) / 2      # plastic beside the metal, smallest case
    paths["tab metal end edge -> insulator end -> pedestal (creepage)"] = round(o_lat + t_ins, 3)
    paths["tab metal top edge -> insulator top -> pedestal (creepage)"] = round(o_top + t_ins, 3)
    # 5. Leads: they stand behind the insulator (y > tab_y); air path must go round the insulator's
    #    end or top. Lower bound: overhang + thickness, as in 4.
    # Package height map (seated on the lead shoulders, L1).
    hb = TO247["L1"]
    metal_bottom = (hb[0] + TO247["D"][0] - TO247["D2"][1] - TO247["D1"][1],
                    hb[1] + TO247["D"][1] - TO247["D2"][0] - TO247["D1"][0])
    metal_top = (hb[0] + TO247["D"][0] - TO247["D2"][1], hb[1] + TO247["D"][1] - TO247["D2"][0])
    res["package_heights_above_board_mm"] = {"body_bottom": hb, "tab_metal_bottom": [round(v, 2) for v in metal_bottom],
                                             "tab_metal_top": [round(v, 2) for v in metal_top],
                                             "body_top": (round(hb[0] + TO247["D"][0], 2), round(hb[1] + TO247["D"][1], 2)),
                                             "lateral_plastic_margin_min": round(lat_margin_min, 3)}
    res["paths_mm"] = paths
    res["pass_8mm"] = {k: v >= FLOOR for k, v in paths.items()}
    return res


def main():
    d = json.load(open(sys.argv[1]))
    geo = json.load(open(sys.argv[2]))
    hot = geoms(d)
    out = {"floor_mm": FLOOR, "as_built_R25": survey(hot, pe_as_built())}
    worst = min(out["as_built_R25"], key=lambda r: r["min_mm"])
    out["as_built_worst"] = worst
    # Proposed: 2.0 mm AlN, pedestal lower edge 8.0 mm above board top, sink set back 8.0 mm,
    # end/top overhang 6.0 mm beyond tab metal.
    out["proposed"] = proposed(geo, z_s=8.0, g=8.0, t_ins=2.0, o_lat=6.0, o_top=6.0)
    # Sensitivity: the minimum z_s and g that meet 8.0 mm with the copper as routed.
    out["minimum_z_s_for_8mm_with_0p6mm_edge_pour"] = round(FLOOR - 0.6, 2)
    out["minimum_g_for_8mm_with_0p6mm_edge_copper"] = round(FLOOR - 0.6, 2)
    json.dump(out, open(sys.argv[3], "w"), indent=1)
    print("as built worst:", worst)
    n_fail = sum(1 for r in out["as_built_R25"] if not r["pass_8mm"])
    print("as built rows < 8 mm:", n_fail, "of", len(out["as_built_R25"]))
    for r in out["as_built_R25"]:
        if r["min_mm"] < 8:
            print("  ", r["pe_solid"][:22], r["net"], r["layer_or_pad"], r["min_mm"])
    print(json.dumps(out["proposed"], indent=1))


if __name__ == "__main__":
    main()
