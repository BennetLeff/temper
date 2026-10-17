#!/usr/bin/env python3
"""Clearance pre-check for hand-laid stage-48 copper and part moves (study aid, not a gate; KiCad DRC is the gate).

    python3 fit_check.py COPPER_DUMP.json COURTYARDS.json SPEC.json

SPEC.json:
  "group": {"net": "LOW", ...}            nets new since the dump, for rules21.clearance (its GROUP comes from the stale board)
  "ignore_refs": ["U3", ...]              parts that move or go: their dump pads and courtyards are dropped
  "pad_nets": [[ref, x, y, net], ...]     dump pads whose net changes (matched by pad centre within 0.05 mm)
  "remove_tracks": [[net, layer|"*", x0, y0, x1, y1], ...]   dump track segments with both ends inside the box go
  "remove_vias": [[net, x, y], ...]
  "parts": [[ref, fp, cx, cy, angle, [net per pad]], ...]   fp: 0603 / 1206 / SOT23-5 / SOT23-6 (KiCad frame, y down;
                                          angle as patches21.s44_pads: 0603 pad 1 west at 0, south at 90)
  "tracks": [[net, layer, width, [[x, y], ...]], ...]
  "vias": [[net, x, y], ...]              0.6 / 0.3 mm
Checks every new pad / track / via against the remaining dump copper and the other new items with rules21.clearance
(+0.01 mm), pours of nets whose clearance exceeds the 0.2 mm floor (they are not expected to pull back), the In1
Kelvin pour against new tracks of other nets (vias may pass, as incr21 protects it), and new courtyards (0.1 mm gap).
"""
import json
import math
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.strtree import STRtree

L = Path(__file__).resolve().parents[4] / "native-21/layout"
sys.path.insert(0, str(L))
import rules21  # noqa: E402

dump, cyf, specf = sys.argv[1:4]
d = json.load(open(dump))
S = json.load(open(specf))
rules21.GROUP.update(S.get("group", {}))
LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
# pad templates: list of (dx, dy, w, h) at angle 0
SOT = lambda n: [(-1.1375, -0.95), (-1.1375, 0.0), (-1.1375, 0.95), (1.1375, 0.95), (1.1375, 0.0), (1.1375, -0.95)] if n == 6 \
    else [(-1.1375, -0.95), (-1.1375, 0.0), (-1.1375, 0.95), (1.1375, 0.95), (1.1375, -0.95)]
FP = {"0603": ([(-0.825, 0.0), (0.825, 0.0)], (0.8, 0.95), (3.05, 1.55)),
      "1206": ([(-1.4625, 0.0), (1.4625, 0.0)], (1.125, 1.75), (4.65, 2.35)),
      "SOT23-5": (SOT(5), (1.325, 0.6), (4.19, 3.49)),
      "SOT23-6": (SOT(6), (1.325, 0.6), (4.19, 3.49))}


def rot(dx, dy, ang):
    a = math.radians(ang)
    return dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)


def part_pads(fp, cx, cy, ang):
    offs, (pw, ph), _ = FP[fp]
    out = []
    for dx, dy in offs:
        x, y = rot(dx, dy, ang)
        w, h = (pw, ph) if int(ang) % 180 == 0 else (ph, pw)
        out.append(box(cx + x - w / 2, cy + y - h / 2, cx + x + w / 2, cy + y + h / 2))
    return out


def part_court(fp, cx, cy, ang):
    w, h = FP[fp][2]
    if int(ang) % 180:
        w, h = h, w
    return box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def inside(p, b):
    return b[0] - 1e-6 <= p[0] <= b[2] + 1e-6 and b[1] - 1e-6 <= p[1] <= b[3] + 1e-6


ign = set(S.get("ignore_refs", []))
old = []      # (geom, net, layers, label)
for t in d["tracks"]:
    if any(t["net"] == n and lay in ("*", t["layer"]) and inside(t["a"], (x0, y0, x1, y1)) and inside(t["b"], (x0, y0, x1, y1))
           for n, lay, x0, y0, x1, y1 in S.get("remove_tracks", [])):
        continue
    g = LineString([t["a"], t["b"]]).buffer(t["w"] / 2) if t["a"] != t["b"] else Point(t["a"]).buffer(t["w"] / 2)
    old.append((g, t["net"], {t["layer"]}, f"track {t['net']} {t['layer']} {t['a']}-{t['b']}"))
for v in d["vias"]:
    if any(v["net"] == n and math.dist(v["at"], (x, y)) < 0.02 for n, x, y in S.get("remove_vias", [])):
        continue
    old.append((Point(v["at"]).buffer(v["d"] / 2), v["net"], set(LAYERS), f"via {v['net']} {v['at']}"))
pn = S.get("pad_nets", [])
for p in d["pads"]:
    if p["ref"] in ign:
        continue
    g = Polygon(p["pts"]).buffer(0)
    net = p["net"] or ""
    for ref, x, y, n in pn:
        if ref == p["ref"] and g.centroid.distance(Point(x, y)) < 0.05:
            net = n
    lays = set(LAYERS) if p["tht"] else {(p.get("layers") or ["F.Cu"])[0]}
    old.append((g, net, lays, f"pad {p['ref']} {net} ({g.centroid.x:.3f},{g.centroid.y:.3f})"))
zones = []
for z in d["zones"]:
    if len(z["pts"]) > 2:
        zones.append((Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0), z["net"], z["layer"]))

new = []
for ref, fp, cx, cy, ang, nets in S.get("parts", []):
    for k, (g, net) in enumerate(zip(part_pads(fp, cx, cy, ang), nets), 1):
        new.append((g, net, {"F.Cu"}, f"pad {ref}.{k} {net}", "pad"))
for net, lay, w, pts in S.get("tracks", []):
    for a, b in zip(pts, pts[1:]):
        new.append((LineString([a, b]).buffer(w / 2), net, {lay}, f"track {net} {lay} {a}-{b}", "track"))
for net, x, y in S.get("vias", []):
    new.append((Point(x, y).buffer(0.3), net, set(LAYERS), f"via {net} ({x},{y})", "via"))

tree = STRtree([o[0] for o in old])
bad = 0


def need(a, b):
    return (rules21.clearance(a, b) if a and b else 0.2) + 0.01


for i, (g, net, lays, lab, kind) in enumerate(new):
    for k in tree.query(g.buffer(6.0)):
        h, n2, l2, lab2 = old[k]
        if n2 == net or not (lays & l2):
            continue
        dd = h.distance(g)
        if dd < need(net, n2):
            bad += 1
            print(f"CLEAR {lab}  vs  {lab2}: {dd:.3f} < {need(net, n2) - 0.01:.2f}")
    for h, n2, l2, lab2, _ in new[i + 1:]:
        if n2 != net and (lays & l2) and h.distance(g) < need(net, n2):
            bad += 1
            print(f"CLEAR {lab}  vs  {lab2}: {h.distance(g):.3f} < {need(net, n2) - 0.01:.2f}")
    for h, n2, zl in zones:
        if zl not in lays or n2 == net:
            continue
        c = rules21.clearance(net, n2)
        if c > 0.2 + 1e-9 and h.distance(g) < c + 0.01:
            bad += 1
            print(f"ZONE  {lab}  vs  {n2} pour {zl}: {h.distance(g):.3f} < {c:.2f}")
        if n2 in ("ocp_kelvin_p", "ocp_kelvin_n") and kind == "track" and h.intersects(g):
            print(f"note  {lab} cuts the {n2} {zl} pour (incr21 protects it from routed tracks)")
cys = {k: box(*v) for k, v in json.load(open(cyf)).items() if k not in ign}
for ref, fp, cx, cy, ang, nets in S.get("parts", []):
    c = part_court(fp, cx, cy, ang)
    for k, o in cys.items():
        if o.buffer(0.1).intersects(c) and k != ref:
            bad += 1
            print(f"COURT {ref} {[round(v, 3) for v in c.bounds]} vs {k} {[round(v, 3) for v in o.bounds]}")
    cys[ref] = c
print(f"{bad} problems")
sys.exit(1 if bad else 0)
