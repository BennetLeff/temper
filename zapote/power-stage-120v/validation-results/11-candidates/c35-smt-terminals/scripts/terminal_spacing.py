#!/usr/bin/env python3
"""Spacing at the coil terminals J2 / J5, per copper layer, from a build's copper dump (plot_copper.py --dump).

    python3 -I scripts/terminal_spacing.py LABEL BUILD/copper-dump.json [--json OUT.json]

For the copper of res_a and coil_feed within R mm of the terminals (pads, pours, tracks, vias), the nearest copper of
(a) the other terminal's net (the 5.0 mm tank rule between J2 and J5), (b) any other HOT net (tank rule 5.0 mm), and
(c) SELV / PE (12.6 mm RES_A creepage on F / B, 8.0 mm barrier inside, rules21), on each layer and in plan view.
The same script on the s32 build (THR) and the s35 build (SMT) shows what the terminal change moved.
"""
import argparse
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

UNIT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(UNIT / "native-21/layout"))
import rules21  # noqa: E402
from layers21 import CU  # noqa: E402  (native-21/stackup.json)

CENTRES = {"J5": (132.0, 70.5), "J2": (132.0, 85.5)}
NETS = {"J5": "res_a", "J2": "coil_feed"}
R = 9.0          # mm round each centre: the stud land (6.5 mm corner) plus the via ring and a margin
REACH = 16.0     # mm: other-net copper considered (beyond the 12.6 mm RES_A rule)


def geoms(d):
    out = []
    for z in d["zones"]:
        if len(z["pts"]) > 2:
            out.append((z["net"], z["layer"], Polygon(z["pts"], [h for h in z.get("holes", []) if len(h) > 2]).buffer(0)))
    for p in d["pads"]:
        if len(p["pts"]) > 2:
            g = Polygon(p["pts"]).buffer(0)
            for lay in (CU if "*.Cu" in p["layers"] else [x for x in p["layers"] if x in CU]):
                out.append((p["net"] or "<npth>", lay, g))
    for t in d["tracks"]:
        out.append((t["net"], t["layer"], LineString([t["a"], t["b"]]).buffer(t["w"] / 2)))
    for v in d["vias"]:
        for lay in CU:
            out.append((v["net"], lay, Point(v["at"]).buffer(v["d"] / 2)))
    return out


ap = argparse.ArgumentParser()
ap.add_argument("label"); ap.add_argument("dump"); ap.add_argument("--json")
a = ap.parse_args()
d = json.loads(Path(a.dump).read_text())
G = geoms(d)
layers = list(CU)
res = {"label": a.label, "radius_mm": R, "terminals": {}}
for ref, c in CENTRES.items():
    net = NETS[ref]
    other = NETS["J2" if ref == "J5" else "J5"]
    zone = Point(c).buffer(R)
    row = {}
    plan_mine, plan_selv = [], []
    for lay in layers + ["PLAN"]:
        lays = layers if lay == "PLAN" else [lay]
        mine = unary_union([g.intersection(zone) for n, l, g in G if n == net and l in lays and g.intersects(zone)])
        if mine.is_empty:
            row[lay] = None
            continue
        near = Point(c).buffer(R + REACH)
        best = {"other_terminal": (None, None), "other_hot": (None, None), "selv_pe": (None, None)}
        for n, l, g in G:
            if l not in lays or n == net or n == "<npth>" or not g.intersects(near):
                continue
            dom = rules21.domain(n)
            k = "other_terminal" if n == other else ("selv_pe" if dom in ("SELV", "PE") else "other_hot")
            if lay == "PLAN" and k != "selv_pe":
                continue
            dist = mine.distance(g)
            if best[k][0] is None or dist < best[k][0]:
                best[k] = (round(dist, 3), n)
        row[lay] = {k: {"mm": v[0], "net": v[1]} for k, v in best.items()}
    res["terminals"][ref] = {"net": net, "layers": row}
for ref, t in res["terminals"].items():
    for lay, v in t["layers"].items():
        if v:
            print(f"{a.label} {ref} {t['net']} {lay}: " + ", ".join(f"{k} {x['mm']} ({x['net']})" for k, x in v.items() if x["mm"] is not None))
if a.json:
    Path(a.json).write_text(json.dumps(res, indent=1) + "\n")
