#!/usr/bin/env python3
"""Legal poses for a two-pad SMD resistor beside its targets (study aid for stage 48, not a gate).

    python3 res_spots.py COPPER_DUMP.json COURTYARDS.json NET1 NET2 X1,Y1 X2,Y2 [--fp 0603|1206] [--radius MM]
                         [--placed X,Y,ANG,FP ...] [--ignore-ref REF ...] [--ignore-track NET ...] [--top N]

Pad 1 carries NET1 and should land near X1,Y1, pad 2 NET2 near X2,Y2. A pose is legal when:
- its courtyard (0603 3.05 x 1.55, 1206 4.65 x 2.35) keeps 0.1 mm from every other courtyard (the s47 courtyards file
  plus --placed parts of this stage);
- each F.Cu pad keeps rules21.clearance(net, other) + 0.05 mm from other-net F.Cu copper (tracks, pads, vias), and
  plan view >= 8.1 mm from copper of the other side of the reinforced barrier on any layer (the s47 D5 floor 8.047);
- a pad may sit on (touch) copper of its own net.
Ranked by the sum of pad-to-target distances (a short route). Coordinates and pad offsets follow patches21.s44_pads:
at angle 0 pad 1 is west, 90 south, 180 east, 270 north (KiCad frame, y down).
"""
import argparse, json, math, sys
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon, box
from shapely.strtree import STRtree

L = Path(__file__).resolve().parents[4] / "native-21/layout"
sys.path.insert(0, str(L))
import rules21  # noqa: E402

FP = {"0603": (0.825, 0.8, 0.95, 3.05, 1.55), "1206": (1.4625, 1.125, 1.75, 4.65, 2.35)}
ap = argparse.ArgumentParser()
ap.add_argument("dump"); ap.add_argument("courtyards"); ap.add_argument("net1"); ap.add_argument("net2")
ap.add_argument("t1"); ap.add_argument("t2")
ap.add_argument("--fp", default="0603"); ap.add_argument("--radius", type=float, default=4.0)
ap.add_argument("--placed", action="append", default=[]); ap.add_argument("--ignore-ref", action="append", default=[])
ap.add_argument("--ignore-track", action="append", default=[], help="NET or NET@X0,Y0,X1,Y1: other-net copper to be removed")
ap.add_argument("--top", type=int, default=10); ap.add_argument("--step", type=float, default=0.1)
a = ap.parse_args()
t1 = tuple(map(float, a.t1.split(","))); t2 = tuple(map(float, a.t2.split(",")))
c0 = ((t1[0] + t2[0]) / 2, (t1[1] + t2[1]) / 2)
d = json.load(open(a.dump))
R = a.radius + math.dist(t1, t2) / 2
near = box(c0[0] - R - 12, c0[1] - R - 12, c0[0] + R + 12, c0[1] + R + 12)
ign = []
for s in a.ignore_track:
    net, _, bx = s.partition("@")
    ign.append((net, box(*map(float, bx.split(","))) if bx else None))


def ignored(net, g):
    return any(net == n and (b is None or b.contains(g)) for n, b in ign)


items = []
for t in d["tracks"]:
    g = LineString([t["a"], t["b"]]).buffer(t["w"] / 2) if t["a"] != t["b"] else Point(t["a"]).buffer(t["w"] / 2)
    if not ignored(t["net"], g):
        items.append((g, t["net"], t["layer"]))
for v in d["vias"]:
    g = Point(v["at"]).buffer(v["d"] / 2)
    if not ignored(v["net"], g):
        items.append((g, v["net"], "*"))
for p in d["pads"]:
    if p["ref"] in a.ignore_ref:
        continue
    items.append((Polygon(p["pts"]).buffer(0), p["net"] or "", "*" if p.get("tht") else (p.get("layers") or ["F.Cu"])[0]))
for z in d["zones"]:
    if len(z["pts"]) > 2:
        items.append((Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0), z["net"], z["layer"] + "#zone"))
items = [i for i in items if i[0].intersects(near)]
tree = STRtree([i[0] for i in items])
cys = [tuple(v) for k, v in json.load(open(a.courtyards)).items() if k not in a.ignore_ref]
for p in a.placed:
    x, y, ang, fp = p.split(",")
    x, y, ang = float(x), float(y), float(ang)
    _, _, _, cw, ch = FP[fp]
    w, h = (cw, ch) if ang in (0, 180) else (ch, cw)
    cys.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
cys = [c for c in cys if box(*c).intersects(near)]
dom = rules21.domain(a.net1)


def pad_ok(g, net):
    for k in tree.query(g.buffer(8.5)):
        h, n, lay = items[k]
        if n == net:
            continue
        if rules21.barrier(net, n) and h.distance(g) < 8.1:
            return False
        if lay.endswith("#zone"):
            if lay.startswith("F.Cu") and h.distance(g) < rules21.clearance(net, n) + 0.05:
                return False
            continue
        if lay not in ("F.Cu", "*"):
            continue
        if h.distance(g) < (rules21.clearance(net, n) if n else 0.2) + 0.05:
            return False
    return True


off, pw, ph, cw, ch = FP[a.fp]
out = []
n = int(R / a.step)
for i in range(-n, n + 1):
    for j in range(-n, n + 1):
        cx, cy = round(c0[0] + i * a.step, 3), round(c0[1] + j * a.step, 3)
        if math.hypot(cx - c0[0], cy - c0[1]) > R:
            continue
        for ang in (0, 90, 180, 270):
            w, h = (cw, ch) if ang in (0, 180) else (ch, cw)
            cyb = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if any(cyb[0] < k[2] + 0.1 and k[0] - 0.1 < cyb[2] and cyb[1] < k[3] + 0.1 and k[1] - 0.1 < cyb[3] for k in cys):
                continue
            dx, dy = {0: (-off, 0), 90: (0, off), 180: (off, 0), 270: (0, -off)}[ang]
            p1, p2 = (cx + dx, cy + dy), (cx - dx, cy - dy)
            score = math.dist(p1, t1) + math.dist(p2, t2)
            if out and len(out) > 300 and score > sorted(o[0] for o in out)[min(len(out) - 1, a.top * 4)]:
                continue
            qw, qh = (pw, ph) if ang in (0, 180) else (ph, pw)
            ok = all(pad_ok(box(q[0] - qw / 2, q[1] - qh / 2, q[0] + qw / 2, q[1] + qh / 2), net)
                     for q, net in ((p1, a.net1), (p2, a.net2)))
            if ok:
                out.append((round(score, 2), cx, cy, ang, p1, p2))
out.sort()
print(f"{a.net1} {t1} / {a.net2} {t2} ({a.fp}): {len(out)} legal poses")
seen = []
for o in out:
    if any(math.dist(s, o[1:3]) < 0.4 for s in seen):
        continue
    seen.append(o[1:3])
    print(f"  centre ({o[1]}, {o[2]}) angle {o[3]}: pad-target sum {o[0]} mm; pad1 ({o[4][0]:.3f}, {o[4][1]:.3f}) pad2 ({o[5][0]:.3f}, {o[5][1]:.3f})")
    if len(seen) >= a.top:
        break
