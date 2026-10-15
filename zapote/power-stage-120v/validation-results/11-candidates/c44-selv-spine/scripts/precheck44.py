#!/usr/bin/env python3
"""Pre-build check of the stage-44 copper (patches21.S44_*) against a base build's copper dump (study aid; KiCad DRC on
the build stays the authority).

    python3 precheck44.py BASE_COPPER_DUMP.json

New items: the C169-C175 pads (0603: 0.95 x 0.90 mm, F.Cu), their plane vias and 0.3 mm stubs, the moved bus_fault via
and escape, the bias_good In2 extension. Each must keep rules21.clearance + 0.02 mm from other-net copper of the base
(less the removed bus_fault / bias_good items) and from the other new items on a shared layer, and >= 8.1 mm plan view
from HOT copper. Prints every shortfall and the distances that matter for return_path19 (via -> nearer cap pad).
"""
import json, math, sys
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
L = Path(__file__).resolve().parents[4] / "native-21/layout"
sys.path.insert(0, str(L))
import rules21, layers21, patches21 as P  # noqa: E402

d = json.load(open(sys.argv[1]))
CU = set(layers21.CU)
removed_v = [P.S44_BUS_FAULT_VIA[0], P.S44_BIAS_GOOD_VIA]
def seg(a, b, w):
    return LineString([a, b]).buffer(w / 2) if a != b else Point(a).buffer(w / 2)
base = []
for t in d["tracks"]:
    if t["net"] == "bus_fault" and t["layer"] == "B.Cu" and min(math.dist(t["a"], q) + math.dist(t["b"], q) for q in [(34.0, 131.0)]) < 3.5 and max(t["a"][1], t["b"][1]) < 132.7:
        continue   # the removed stub / trunk tail under U13
    base.append((seg(t["a"], t["b"], t["w"]), t["net"], {t["layer"]}, "track"))
for v in d["vias"]:
    if any(math.dist(v["at"], q) < 0.01 for q in removed_v):
        continue
    base.append((Point(v["at"]).buffer(v["d"] / 2), v["net"], CU, f"via {v['at']}"))
for p in d["pads"]:
    base.append((Polygon(p["pts"]).buffer(0), p["net"] or "", CU if p.get("tht") else set(p.get("layers", ["F.Cu"])), f"pad {p['ref']}"))
hot = unary_union([g for g, n, _, _ in base if rules21.domain(n) == "HOT"] +
                  [Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0) for z in d["zones"] if rules21.domain(z["net"]) == "HOT" and len(z["pts"]) > 2])
new = []
for ref, (path, cx, cy, ang, v1, v2) in P.S44_CAPS.items():
    for (q, net, via) in zip(P.s44_pads(ref), ("v3v3", "selv_gnd"), (v1, v2)):
        w, h = (0.95, 0.90) if int(ang) in (0, 180) else (0.90, 0.95)
        new.append((box(q[0] - w / 2, q[1] - h / 2, q[0] + w / 2, q[1] + h / 2), net, {"F.Cu"}, f"{ref} pad {net}"))
        if via not in P.S44_EXISTING_VIAS:
            new.append((Point(via).buffer(0.3), net, CU, f"{ref} via {net} {via}"))
        new.append((seg(q, via, 0.3), net, {"F.Cu"}, f"{ref} stub {net}"))
nv = P.S44_BUS_FAULT_VIA[1]
new.append((Point(nv).buffer(0.3), "bus_fault", CU, "bus_fault via"))
for a, b in [((33.9725, 130.695), (34.843, 131.565)), ((34.843, 131.565), (34.843, 132.366)), ((34.843, 132.366), nv)]:
    new.append((seg(a, b, 0.25), "bus_fault", {"F.Cu"}, "bus_fault escape"))
cp = json.load(open(L / "copper.json"))
trunk = next(t for t in cp["tracks"] if t["net"] == "bias_good" and t["layer"] == "B.Cu" and t["points"][0] == [74.0, 123.4])
stair = trunk["points"][:[tuple(q) for q in trunk["points"]].index(P.S44_BIAS_GOOD_VIA) + 1]
for a, b in zip(stair, stair[1:]):
    new.append((seg(a, b, 0.25), "bias_good", {"In2.Cu"}, "bias_good In2 ext"))
bad = 0
for i, (g, n, ls, what) in enumerate(new):
    for h, m, ls2, w2 in base + new[:i]:
        if m == n or not (ls & ls2):
            continue
        need = (rules21.clearance(n, m) if m else 0.2) + 0.02
        dd = g.distance(h)
        if dd < need:
            print(f"SHORT {what} vs {m} {w2}: {dd:.3f} < {need:.2f}"); bad += 1
    hd = g.distance(hot)
    if hd < 8.1:
        print(f"HOT {what}: {hd:.3f} mm"); bad += 1
targets = {"C169": (33.2, 120.2), "C170": nv, "C171": (74.0, 123.4), "C172": (70.0, 127.8), "C173": (76.825, 125.875),
           "C174": (36.5, 178.6), "C175": (33.2, 70.4)}
for ref, t in targets.items():
    print(ref, "via", t, "-> nearer pad", round(min(math.dist(t, q) for q in P.s44_pads(ref)), 2), "mm")
print("PRECHECK", "PASS" if not bad else f"FAIL ({bad})")
