#!/usr/bin/env python3
"""v3v3-selv_gnd transfer-cap poses with their own plane vias, beside one or more layer changes (study aid, stage 44).

    python3 cap_spots.py COPPER_DUMP.json COURTYARDS.json X,Y [X,Y ...] [--radius MM] [--ignore-net N ...]
                         [--ignore-ref REF ...] [--ignore-via X,Y ...] [--avoid X,Y,R ...] [--top N]

Extends gates/xfer_spots.py: the pads need not lie over both planes. Instead each pad must reach its own plane through
a via (0.6 / 0.3) within 1.6 mm of the pad centre (return_path19's C153-C156 rule) that is legal on all four layers
(rules21 clearance + 0.02 mm to every other-net track / via / pad, not on a pad, >= 8 mm plan view from HOT copper)
and lies 0.3 mm inside its net's pour on its plane layer (v3v3 In1, selv_gnd In2); the straight 0.3 mm F.Cu stub
pad -> via must keep 0.2 mm from other-net F.Cu copper. The pads keep >= --hot mm (default 8.1: above the s43 D5 floor 8.047, so no new copper sets it) from HOT copper. --avoid X,Y,R
keeps vias and pads off circles (copper to be added elsewhere in the same stage). Ranked like xfer_spots.py: worst
target to nearer pad centre.
"""
import argparse, json, math, sys
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

L = Path(__file__).resolve().parents[4] / "native-21/layout"
sys.path.insert(0, str(L))
import rules21, layers21  # noqa: E402

PAD_W, PAD_H, PITCH, CY_W, CY_H, VR, VMAX = 0.95, 0.90, 1.55, 3.05, 1.55, 0.3, 1.6
ap = argparse.ArgumentParser()
ap.add_argument("dump"); ap.add_argument("courtyards"); ap.add_argument("targets", nargs="+")
ap.add_argument("--radius", type=float, default=4.0); ap.add_argument("--top", type=int, default=8)
ap.add_argument("--ignore-net", action="append", default=[]); ap.add_argument("--ignore-ref", action="append", default=[])
ap.add_argument("--ignore-via", action="append", default=[]); ap.add_argument("--avoid", action="append", default=[])
ap.add_argument("--placed", action="append", default=[]); ap.add_argument("--hot", type=float, default=8.1); ap.add_argument("--min-via", type=float, default=0.85)
a = ap.parse_args()
tg = [tuple(map(float, t.split(","))) for t in a.targets]
c0 = tg[0]
d = json.load(open(a.dump))
near = box(c0[0] - a.radius - 10, c0[1] - a.radius - 10, c0[0] + a.radius + 10, c0[1] + a.radius + 10)
ign_v = [tuple(map(float, s.split(","))) for s in a.ignore_via]
avoid = [Point(*map(float, s.split(",")[:2])).buffer(float(s.split(",")[2])) for s in a.avoid]
items = []
for t in d["tracks"]:
    g = LineString([t["a"], t["b"]]).buffer(t["w"] / 2) if t["a"] != t["b"] else Point(t["a"]).buffer(t["w"] / 2)
    items.append((g, t["net"], {t["layer"]}))
for v in d["vias"]:
    if not any(math.dist(v["at"], q) < 0.01 for q in ign_v):
        items.append((Point(v["at"]).buffer(v["d"] / 2), v["net"], set(layers21.CU)))
for p in d["pads"]:
    lays = set(layers21.CU) if p.get("tht") else set(p.get("layers", ["F.Cu"]))
    items.append((Polygon(p["pts"]).buffer(0), p["net"] or "", lays))
items = [i for i in items if i[0].intersects(near) and i[1] not in a.ignore_net]
hot = [i[0] for i in items if rules21.domain(i[1]) == "HOT"]
hot += [Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0) for z in d["zones"]
        if rules21.domain(z["net"]) == "HOT" and len(z["pts"]) > 2 and Polygon(z["pts"]).buffer(0).intersects(near)]
hot_u = unary_union(hot) if hot else Point(1e6, 1e6)
tree = STRtree([i[0] for i in items])
fcu = [(g, n) for g, n, ls in items if "F.Cu" in ls]
ftree = STRtree([g for g, _ in fcu])
plane = {}
for net in ("v3v3", "selv_gnd"):
    lay = layers21.PLANE_ROLE[net]
    plane[net] = unary_union([Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0) for z in d["zones"]
                              if z["layer"] == lay and z["net"] == net and len(z["pts"]) > 2]).buffer(-0.3)
cys = [tuple(v) for k, v in json.load(open(a.courtyards)).items() if k not in a.ignore_ref]
for p in a.placed:
    x, y, ang = map(float, p.split(","))
    w, h = (CY_W, CY_H) if ang in (0, 180) else (CY_H, CY_W)
    cys.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
cys = [c for c in cys if box(*c).intersects(near)]


def clear(g, net, lays=None, extra=0.02):
    for k in tree.query(g.buffer(0.5)):
        h, n, ls = items[k]
        if n == net or (lays is not None and not (ls & lays)):
            continue
        if h.distance(g) < (rules21.clearance(net, n) if n else 0.2) + extra:
            return False
    return not any(av.intersects(g) for av in avoid)


vcache = {}


def via_for(q, net, other):
    """other = the pad box of the cap's other pad: the via and stub must clear it too."""
    best = None
    for i in range(-16, 17):
        for j in range(-16, 17):
            x, y = round(q[0] + i * 0.1, 2), round(q[1] + j * 0.1, 2)
            dd = math.hypot(x - q[0], y - q[1])
            if dd > VMAX or dd < a.min_via or (best and dd >= best[0]):
                continue
            key = (x, y, net)
            if key not in vcache:
                c = Point(x, y)
                ok = plane[net].contains(c) and clear(c.buffer(VR), net) and hot_u.distance(c.buffer(VR)) >= a.hot
                vcache[key] = ok
            if not vcache[key] or Point(x, y).buffer(VR).distance(other) < 0.22:
                continue
            stub = LineString([q, (x, y)]).buffer(0.15) if dd > 0.01 else Point(q).buffer(0.15)
            if dd > 0.3 and (not clear(stub, net, {"F.Cu"}) or stub.distance(other) < 0.2):
                continue
            best = (dd, x, y)
    return best


out = []
n = int(a.radius / 0.1)
for i in range(-n, n + 1):
    for j in range(-n, n + 1):
        cx, cy = round(c0[0] + i * 0.1, 2), round(c0[1] + j * 0.1, 2)
        if math.hypot(cx - c0[0], cy - c0[1]) > a.radius:
            continue
        for ang in (0, 90, 180, 270):
            w, h = (CY_W, CY_H) if ang in (0, 180) else (CY_H, CY_W)
            cyb = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if any(cyb[0] < k[2] + 0.1 and k[0] - 0.1 < cyb[2] and cyb[1] < k[3] + 0.1 and k[1] - 0.1 < cyb[3] for k in cys):
                continue
            off = {0: (-PITCH / 2, 0), 90: (0, PITCH / 2), 180: (PITCH / 2, 0), 270: (0, -PITCH / 2)}[ang]
            p1, p2 = (cx + off[0], cy + off[1]), (cx - off[0], cy - off[1])
            worst = max(min(math.dist(p1, t), math.dist(p2, t)) for t in tg)
            if out and len(out) > 400 and worst > sorted(o[0] for o in out)[a.top * 4]:
                continue
            pw, ph = (PAD_W, PAD_H) if ang in (0, 180) else (PAD_H, PAD_W)
            ok, vias = True, []
            pbs = {n: box(q[0] - pw / 2, q[1] - ph / 2, q[0] + pw / 2, q[1] + ph / 2) for q, n in ((p1, "v3v3"), (p2, "selv_gnd"))}
            for q, net in ((p1, "v3v3"), (p2, "selv_gnd")):
                pb = pbs[net]
                if not clear(pb, net, {"F.Cu"}, 0.13) or hot_u.distance(pb) < a.hot:
                    ok = False; break
                v = via_for(q, net, pbs["selv_gnd" if net == "v3v3" else "v3v3"])
                if not v:
                    ok = False; break
                vias.append(v)
            if ok and math.dist(vias[0][1:], vias[1][1:]) < 0.6 + 0.25:
                ok = False
            if ok:
                out.append((round(worst, 2), cx, cy, ang, vias))
out.sort()
print(f"targets {tg}: {len(out)} poses with plane vias")
seen = []
for o in out:
    if any(math.dist(s, o[1:3]) < 0.3 for s in seen):
        continue
    seen.append(o[1:3])
    print(f"  centre ({o[1]}, {o[2]}) angle {o[3]}: worst {o[0]} mm; v3v3 via ({o[4][0][1]}, {o[4][0][2]}) {o[4][0][0]:.2f} mm, "
          f"selv_gnd via ({o[4][1][1]}, {o[4][1][2]}) {o[4][1][0]:.2f} mm")
    if len(seen) >= a.top:
        break
