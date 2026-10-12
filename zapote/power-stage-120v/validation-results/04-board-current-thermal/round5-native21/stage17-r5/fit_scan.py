#!/usr/bin/env python3
"""Stage-17 R5 swap: footprint fit scan around R5 on native-21 (read-only, planning only).

Reads only committed files:
  native-21/verification/native21s16-all-copper.json.gz   (stage-16 copper: pads, tracks, vias)
  validation-plan/enclosure-fit/native21-courtyards.json  (part courtyards, board frame)
It never reads or writes the board, schematic, patches or fab outputs.

For each candidate it builds the footprint outline from the datasheet land-pattern drawing (the
dimensions are listed in CANDS with the datasheet page they were scaled from), places it on R5's centre
(38.5, 12.6) with R5's -90 degree rotation (long axis along board y, Kelvin fingers/pads on the west
side), and reports
  * courtyard conflicts with other parts' courtyards,
  * foreign-net F.Cu copper (tracks, vias, pads) inside the new pad/finger shapes (+ clearance),
  * the smallest translation (0.25 mm grid, within +/-6 mm) that clears all other courtyards.
The translation search is informational: it ignores copper and the HV_RET / LEG_RET plane topology.

usage: python3 fit_scan.py   -> fit.json
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from shapely.affinity import translate
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
CX, CY = 38.5, 12.6          # R5 centre (native-21 placement; section.kicad_pcb: (at 38.5 12.6 -90))
R5_NETS = {"leg_ret", "hv_ret", "ocp_kelvin_p", "ocp_kelvin_n"}
CLEAR = 0.20                 # JLC 2 oz outer-layer copper-to-copper working figure used by the unit DFM gate


def to_board(lx, ly):
    """KiCad rotation -90: board = centre + (-ly, +lx). Local x is the long axis."""
    return CX - ly, CY + lx


def poly_local(xmin, ymin, xmax, ymax):
    pts = [to_board(x, y) for x, y in ((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax))]
    return Polygon(pts)


# Local frame: x = long axis (pad 1 / LEG_RET end at -x, pad 4 / HV_RET end at +x), y = short axis.
# Each entry: pads {name: (xmin, ymin, xmax, ymax, net)}; courtyard (xmin, ymin, xmax, ymax).
CANDS = {
    "WSK25121L000FEA (control, current part)": {
        "pads": {  # native-21 footprint R_Shunt_Vishay_WSK2512_6332Metric_T2.21mm (committed in native-19/20 candidate-libs)
            "1": (-2.48 - 1.65, -0.635 - 1.015, -2.48 + 1.65, -0.635 + 1.015, "leg_ret"),
            "4": (2.48 - 1.65, 0.635 - 1.015, 2.48 + 1.65, 0.635 + 1.015, "hv_ret"),
            "2": (-3.43 - 0.7, 1.27 - 0.38, -3.43 + 0.7, 1.27 + 0.38, "ocp_kelvin_p"),
            "3": (3.43 - 0.7, -1.27 - 0.38, 3.43 + 0.7, -1.27 + 0.38, "ocp_kelvin_n"),
        },
        "courtyard": (-4.425, -1.945, 4.425, 1.945),   # = native21-courtyards.json R5 box
    },
    "CSS2H-2512R-1L00F (Bourns)": {
        # Datasheet p.2 'Recommended Pad Layout' (scaled from the drawing, 55.3 px/mm; only 3.40, 3.40, 1.80 are dimensioned):
        # two L-shaped pads 1.80 x 3.40 with a 3.40 gap, plus two 0.43 mm sense fingers at x = +/-(0.27..0.70) that
        # leave the pad inner lobes and run 3.0 mm in +y (1.5 mm beyond the pad edge).
        "pads": {
            "IA": (-3.50, -1.70, -1.70, 1.70, "leg_ret"),
            "IB": (1.70, -1.70, 3.50, 1.70, "hv_ret"),
            "SA": (-0.70, 0.0, -0.27, 3.20, "ocp_kelvin_p"),
            "SB": (0.27, 0.0, 0.70, 3.20, "ocp_kelvin_n"),
        },
        "courtyard": (-3.75, -1.95, 3.75, 3.45),
    },
    "CSS4J-4026R-1L00F (Bourns, 4-terminal)": {
        # Datasheet p.2: land 10.60 x 7.30 total; solder pads 5.60 tall with 5.50 gap (so 2.55 wide each);
        # sense pads 0.80 tall beyond a 0.90 gap. Pad width derived: (10.60 - 5.50) / 2.
        "pads": {
            "IA": (-5.30, -2.80, -2.75, 2.80, "leg_ret"),
            "IB": (2.75, -2.80, 5.30, 2.80, "hv_ret"),
            "SA": (-5.30, 3.70, -2.75, 4.50, "ocp_kelvin_p"),
            "SB": (2.75, 3.70, 5.30, 4.50, "ocp_kelvin_n"),
        },
        "courtyard": (-5.55, -3.05, 5.55, 4.75),
    },
    "BVS-M-R001-1.0 (Isabellenhuette, 3920)": {
        # Datasheet 24-Jan-2025 p.2 'Solder pad dimensions': overall l = 11, w = 6.2, a = 2.7 (pad length), x = 5.6 gap.
        # Two-terminal part: Kelvin taps are 0.40 mm stubs from the inner pad corners (modelled 0.4 x 1.2 at +y).
        "pads": {
            "IA": (-5.50, -3.10, -2.80, 3.10, "leg_ret"),
            "IB": (2.80, -3.10, 5.50, 3.10, "hv_ret"),
            "SA": (-2.80, 2.50, -2.40, 3.70, "ocp_kelvin_p"),
            "SB": (2.40, 2.50, 2.80, 3.70, "ocp_kelvin_n"),
        },
        "courtyard": (-5.75, -3.35, 5.75, 3.95),
    },
}


def load():
    d = json.load(gzip.open(UNIT / "native-21/verification/native21s16-all-copper.json.gz"))
    cy = json.load(open(UNIT / "validation-plan/enclosure-fit/native21-courtyards.json"))
    return d["primitives"], cy


def foreign_copper(prims, region):
    """F.Cu tracks/pads and any-layer vias of nets outside R5_NETS that intersect `region` (shapely)."""
    hits = []
    for p in prims:
        k = p["kind"]
        if k == "pad":
            if p.get("ref", "").startswith("R5."):
                continue
            if p["layer"] != "F.Cu" and not p.get("drill_mm", [0, 0])[0]:
                continue
            g = Polygon(p["shell"])
        elif k == "track":
            if p["layer"] != "F.Cu":
                continue
            g = LineString([p["start"], p["end"]]).buffer(p["width_mm"] / 2)
        elif k == "via":
            g = Point(p["centre"]).buffer(p["diameter_mm"] / 2)
        else:
            continue
        if p["net"] in R5_NETS:
            continue
        if g.intersects(region):
            hits.append({"kind": k, "net": p["net"], "ref": p.get("ref"), "layer": p.get("layer"),
                         "at": [round(g.centroid.x, 2), round(g.centroid.y, 2)]})
    return hits


def main():
    prims, cyards = load()
    others = {r: box(*b) for r, b in cyards.items() if r != "R5"}
    out = {"centre_mm": [CX, CY], "rotation_deg": -90, "candidates": {}}
    # F.Cu zones near R5 (informational: pours carve clearance automatically)
    for name, c in CANDS.items():
        pads = {n: poly_local(*g[:4]) for n, g in c["pads"].items()}
        ycopper = unary_union(list(pads.values())).buffer(CLEAR)
        cyd = poly_local(*c["courtyard"])
        conflicts = sorted(r for r, g in others.items() if g.intersects(cyd) and g.intersection(cyd).area > 1e-6)
        overlap_mm2 = {r: round(others[r].intersection(cyd).area, 2) for r in conflicts}
        cu = foreign_copper(prims, ycopper)
        # stage-16 R5-net vias (deduplicated) that would sit inside each new current pad / sense shape
        vias = {(p["net"], tuple(p["centre"]), p["diameter_mm"]) for p in prims
                if p["kind"] == "via" and p["net"] in R5_NETS and 33.5 <= p["centre"][0] <= 43.5 and 6.5 <= p["centre"][1] <= 19.5}
        # existing R5-net copper (F.Cu tracks, vias) of ANOTHER R5 net that would touch a new shape (+ clearance)
        cross = []
        for p in prims:
            if p["net"] not in R5_NETS or p["kind"] not in ("track", "via"):
                continue
            if p["kind"] == "track":
                if p["layer"] != "F.Cu":
                    continue
                g0 = LineString([p["start"], p["end"]]).buffer(p["width_mm"] / 2)
            else:
                g0 = Point(p["centre"]).buffer(p["diameter_mm"] / 2)
            for n, g in pads.items():
                if c["pads"][n][4] != p["net"] and g0.distance(g) < CLEAR:
                    cross.append((n, p["net"], p["kind"], round(g0.centroid.x, 2), round(g0.centroid.y, 2)))
        cross = sorted(set(cross))
        in_pad = {n: sum(1 for v in vias if v[0] == c["pads"][n][4] and g.contains(Point(v[1]))) for n, g in pads.items()}
        # smallest translation that clears every other courtyard
        best = None
        step = 0.25
        n = int(6 / step)
        for ix in range(-n, n + 1):
            for iy in range(-n, n + 1):
                dx, dy = ix * step, iy * step
                t = translate(cyd, dx, dy)
                if any(g.intersects(t) and g.intersection(t).area > 1e-6 for g in others.values()):
                    continue
                dist = (dx * dx + dy * dy) ** 0.5
                if best is None or dist < best[0]:
                    best = (dist, dx, dy)
        minx, miny, maxx, maxy = cyd.bounds
        out["candidates"][name] = {
            "courtyard_board_bbox_mm": [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)],
            "courtyard_size_mm": [round(maxx - minx, 2), round(maxy - miny, 2)],
            "pad_area_mm2": {n: round(g.area, 2) for n, g in pads.items()},
            "stage16_vias_inside_new_pads": in_pad,
            "other_r5_net_copper_within_0p2_of_new_shapes": cross,
            "in_place_courtyard_conflicts": overlap_mm2,
            "in_place_foreign_fcu_copper_in_pads_plus_0p2": cu,
            "foreign_fcu_copper_nets": sorted({h["net"] for h in cu}),
            "min_translation_clearing_all_courtyards_mm": (
                None if best is None else {"dx": best[1], "dy": best[2], "dist": round(best[0], 2)}),
        }
    (HERE / "fit.json").write_text(json.dumps(out, indent=1) + "\n")
    for name, r in out["candidates"].items():
        print(name)
        print("  courtyard", r["courtyard_size_mm"], "bbox", r["courtyard_board_bbox_mm"])
        print("  conflicts", r["in_place_courtyard_conflicts"])
        print("  stage-16 R5-net vias inside new pads", r["stage16_vias_inside_new_pads"])
        print("  other-R5-net copper within 0.2 mm of new shapes:", r["other_r5_net_copper_within_0p2_of_new_shapes"])
        print("  foreign F.Cu in pads:", len(r["in_place_foreign_fcu_copper_in_pads_plus_0p2"]), r["foreign_fcu_copper_nets"])
        print("  min translation", r["min_translation_clearing_all_courtyards_mm"])


if __name__ == "__main__":
    main()
