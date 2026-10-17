#!/usr/bin/env python3
"""Candidate spots for a v3v3-selv_gnd reference-transfer 0603 beside one or more signal layer changes (stage 19c).

    python3 xfer_spots.py COPPER_DUMP.json COURTYARDS.json X,Y [X,Y ...] [--top N] [--radius MM] [--clear MM]
                          [--pads-json PADS.json] [--placed X,Y,ANG ...]

COPPER_DUMP is a build's `copper-dump.json` (`plot_copper.py --dump`); COURTYARDS is the enclosure-fit courtyard
dump (`validation-plan/enclosure-fit/native21-courtyards.json`, ref -> bbox). Scans F.Cu poses of a C_0603
(courtyard 3.05 x 1.55 mm, pad centres 1.55 mm apart, pads 0.95 x 0.9 mm) in 0.1 mm steps, four rotations, within
--radius of the first target. A pose is legal when (a) its courtyard keeps 0.1 mm from every other courtyard
(bbox, both sides: conservative), (b) each pad keeps --clear (default 0.35 mm) from every other-net F.Cu pad,
track and via, and (c) both pads lie inside the In1 v3v3 pour AND the In2 selv_gnd pour (shrunk 0.5 mm, so each
pad's own plane via lands in its plane). Poses are ranked by the worst distance from any target to the nearer
pad centre (the metric `return_path19.py` asserts, limit 3.0 mm). `--placed` adds courtyards for caps chosen
earlier in the same run. Pad 1 is v3v3 (In1 is the nearer plane under F.Cu), pad 2 selv_gnd, as for C153-C156.
"""
import argparse
import json
import math
import sys
from pathlib import Path

from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layers21  # noqa: E402  (native-21/stackup.json: the v3v3 / selv_gnd plane layers)

PAD_W, PAD_H, PITCH = 0.95, 0.90, 1.55
CY_W, CY_H = 3.05, 1.55


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("courtyards")
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--radius", type=float, default=4.0)
    ap.add_argument("--clear", type=float, default=0.35)
    ap.add_argument("--placed", action="append", default=[])
    ap.add_argument("--ignore-net", action="append", default=[], help="nets whose copper here will be re-routed")
    ap.add_argument("--ignore-ref", action="append", default=[], help="parts that will move (their courtyard is ignored)")
    ap.add_argument("--no-planes", action="store_true", help="skip the both-planes-under-the-pads condition")
    a = ap.parse_args()
    tg = [tuple(map(float, t.split(","))) for t in a.targets]
    d = json.load(open(a.dump))
    plane = {}
    for lay, net in ((layers21.PLANE_ROLE["v3v3"], "v3v3"), (layers21.PLANE_ROLE["selv_gnd"], "selv_gnd")):
        ps = [Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0)
              for z in d["zones"] if z["layer"] == lay and z["net"] == net and len(z["pts"]) > 2]
        plane[net] = unary_union(ps).buffer(-0.5)
    cys = [tuple(v) for k, v in json.load(open(a.courtyards)).items() if k not in a.ignore_ref]
    for p in a.placed:
        x, y, ang = map(float, p.split(","))
        w, h = (CY_W, CY_H) if ang in (0, 180) else (CY_H, CY_W)
        cys.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
    lim = a.radius + 4.0
    c0 = tg[0]
    near = box(c0[0] - lim, c0[1] - lim, c0[0] + lim, c0[1] + lim)
    cu = []   # (net, geometry) on F.Cu
    for p in d["pads"]:
        if "F.Cu" in p.get("layers", ["F.Cu"]) or p.get("tht"):
            g = Polygon(p["pts"])
            if g.intersects(near):
                cu.append((p["net"], g))
    for t in d["tracks"]:
        if t["layer"] == "F.Cu":
            from shapely.geometry import LineString
            g = (LineString([t["a"], t["b"]]) if t["a"] != t["b"] else Point(t["a"])).buffer(t["w"] / 2)
            if g.intersects(near):
                cu.append((t["net"], g))
    for v in d["vias"]:
        g = Point(v["at"]).buffer(v["d"] / 2)
        if g.intersects(near):
            cu.append((v["net"], g))
    cys = [c for c in cys if box(*c).intersects(near)]
    out = []
    n = int(a.radius / 0.1)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            cx, cy = c0[0] + i * 0.1, c0[1] + j * 0.1
            if math.hypot(cx - c0[0], cy - c0[1]) > a.radius:
                continue
            for ang in (0, 90, 180, 270):
                horiz = ang in (0, 180)
                w, h = (CY_W, CY_H) if horiz else (CY_H, CY_W)
                cyb = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
                if any(cyb[0] < k[2] + 0.1 and k[0] - 0.1 < cyb[2] and cyb[1] < k[3] + 0.1 and k[1] - 0.1 < cyb[3]
                       for k in cys):
                    continue
                off = {0: (-PITCH / 2, 0), 90: (0, PITCH / 2), 180: (PITCH / 2, 0), 270: (0, -PITCH / 2)}[ang]
                p1, p2 = (cx + off[0], cy + off[1]), (cx - off[0], cy - off[1])
                pw, ph = (PAD_W, PAD_H) if horiz else (PAD_H, PAD_W)
                ok = True
                for q, net in ((p1, "v3v3"), (p2, "selv_gnd")):
                    pb = box(q[0] - pw / 2, q[1] - ph / 2, q[0] + pw / 2, q[1] + ph / 2)
                    if not a.no_planes and not (plane["v3v3"].contains(pb) and plane["selv_gnd"].contains(pb)):
                        ok = False
                        break
                    if any(gn != net and gn not in a.ignore_net and g.distance(pb) < a.clear for gn, g in cu):
                        ok = False
                        break
                if not ok:
                    continue
                worst = max(min(math.dist(p1, t), math.dist(p2, t)) for t in tg)
                out.append((worst, round(cx, 2), round(cy, 2), ang))
    out.sort()
    print(f"targets {tg}: {len(out)} legal poses")
    shown, last = 0, []
    for worst, x, y, ang in out:
        if any(math.dist(l, (x, y)) < 0.3 for l in last):
            continue
        last.append((x, y))
        print(f"  centre ({x}, {y}) angle {ang}: worst target to nearer pad {worst:.2f} mm")
        shown += 1
        if shown >= a.top:
            break


main()
