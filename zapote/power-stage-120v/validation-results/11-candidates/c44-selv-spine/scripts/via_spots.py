#!/usr/bin/env python3
"""Legal spots for a signal via (0.6 / 0.3) near a point, with the plane references return_path19 would see (study aid).

    python3 via_spots.py COPPER_DUMP.json NET X,Y [--radius MM] [--layers F.Cu,B.Cu] [--ignore-net N ...]
                         [--ignore-via X,Y ...] [--cap X,Y,ANG ...] [--top N]

A spot is legal when the via disk keeps rules21.clearance (+0.02 mm) to every other-net track, via and pad on all four
layers (vias are through; pours are refilled round it), its plan-view distance to HOT copper is >= 8.0 mm (barrier21),
and it does not sit on a pad. For each spot it prints the reference on each of --layers (majority of the pour net on a
ring 0.5 mm outside the via, nearest adjacent layer first: return_path19.transitions) and the distance to the nearest
v3v3-selv_gnd capacitor pad (existing two-pad caps, plus --cap poses of new 0603s: pad 1 v3v3 as xfer_spots.py).
The s43 pour fill is used as is (a moved via's old antipad stays cut), so refs near pour edges are approximate.
"""
import argparse, json, math, sys
from collections import Counter
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

L = Path(__file__).resolve().parents[4] / "native-21/layout"
sys.path.insert(0, str(L))
import rules21, layers21  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("dump"); ap.add_argument("net"); ap.add_argument("at")
ap.add_argument("--radius", type=float, default=2.0); ap.add_argument("--step", type=float, default=0.1)
ap.add_argument("--layers", default="F.Cu,B.Cu")
ap.add_argument("--ignore-net", action="append", default=[]); ap.add_argument("--ignore-via", action="append", default=[])
ap.add_argument("--cap", action="append", default=[]); ap.add_argument("--hot", type=float, default=8.1); ap.add_argument("--top", type=int, default=12)
a = ap.parse_args()
d = json.load(open(a.dump))
x0, y0 = map(float, a.at.split(","))
R = 0.3
ign_v = [tuple(map(float, s.split(","))) for s in a.ignore_via]
items = []   # (geom, net, layers)
for t in d["tracks"]:
    g = LineString([t["a"], t["b"]]).buffer(t["w"] / 2) if t["a"] != t["b"] else Point(t["a"]).buffer(t["w"] / 2)
    items.append((g, t["net"], {t["layer"]}))
for v in d["vias"]:
    if any(math.dist(v["at"], q) < 0.01 for q in ign_v):
        continue
    items.append((Point(v["at"]).buffer(v["d"] / 2), v["net"], set(layers21.CU)))
pads = []
for p in d["pads"]:
    g = Polygon(p["pts"]).buffer(0)
    lays = set(layers21.CU) if p.get("tht") else set(p.get("layers", ["F.Cu"]))
    items.append((g, p["net"] or "", lays)); pads.append(g)
near = Point(x0, y0).buffer(a.radius + 9)
items = [i for i in items if i[0].intersects(near)]
tree = STRtree([i[0] for i in items])
hot = [i[0] for i in items if rules21.domain(i[1]) == "HOT"]
hot += [Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0) for z in d["zones"]
        if rules21.domain(z["net"]) == "HOT" and len(z["pts"]) > 2 and Polygon(z["pts"]).buffer(0).intersects(near)]
zones = {}
for z in d["zones"]:
    if len(z["pts"]) > 2:
        zones.setdefault(z["layer"], []).append((Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0), z["net"]))

def pour(lay, pt):
    for p, n in zones.get(lay, []):
        if p.contains(pt):
            return n
    return None

def ref(lay, pt):
    for l2 in layers21.ADJ[lay]:
        n = pour(l2, pt)
        if n:
            return l2, n
    return None, None

caps = []
cp = {}
for p in d["pads"]:
    if p["ref"].startswith("C"):
        cp.setdefault(p["ref"], []).append(p)
for r, ps in cp.items():
    if len(ps) == 2 and {ps[0]["net"], ps[1]["net"]} == {"v3v3", "selv_gnd"}:
        caps += [(r, Polygon(q["pts"]).centroid.coords[0]) for q in ps]
for i, c in enumerate(a.cap):
    x, y, ang = map(float, c.split(","))
    off = {0: (-0.775, 0), 90: (0, 0.775), 180: (0.775, 0), 270: (0, -0.775)}[int(ang)]
    caps += [(f"new{i}", (x + off[0], y + off[1])), (f"new{i}", (x - off[0], y - off[1]))]
lays = a.layers.split(",")
out = []
n = int(a.radius / a.step)
for i in range(-n, n + 1):
    for j in range(-n, n + 1):
        x, y = round(x0 + i * a.step, 3), round(y0 + j * a.step, 3)
        if math.hypot(x - x0, y - y0) > a.radius:
            continue
        c = Point(x, y); disk = c.buffer(R)
        bad = False
        for k in tree.query(disk.buffer(8.1)):
            g, net, ls = items[k]
            if net == a.net or net in a.ignore_net:
                continue
            need = rules21.clearance(a.net, net) if net else 0.2
            if g.distance(disk) < need + 0.02:
                bad = True; break
        if bad:
            continue
        hd = min((g.distance(disk) for g in hot), default=99)
        if hd < a.hot:
            continue
        refs = {}
        for lay in lays:
            votes = Counter(ref(lay, Point(x + (R + 0.5) * math.cos(2 * math.pi * k / 16), y + (R + 0.5) * math.sin(2 * math.pi * k / 16)))[1] for k in range(16))
            refs[lay] = votes.most_common(1)[0]
        cd = min(((math.dist((x, y), q), r) for r, q in caps), default=(99, None))
        out.append((round(cd[0], 2), cd[1], x, y, {k: f"{v[0]}:{v[1]}" for k, v in refs.items()}, round(hd, 2)))
out.sort(key=lambda r: (r[0], math.hypot(r[2] - x0, r[3] - y0)))
print(f"{a.net} near ({x0}, {y0}): {len(out)} legal via spots")
for r in out[:a.top]:
    print(f"  ({r[2]}, {r[3]}) cap {r[1]} {r[0]} mm  refs {r[4]}  hot {r[5]} mm  move {math.hypot(r[2]-x0, r[3]-y0):.2f}")
