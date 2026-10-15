#!/usr/bin/env python3
"""Clearance probe for a planned track or via on a native-21 copper dump (layout aid).

    python3 -I probe.py DUMP.json NET LAYER|via WIDTH x0,y0 x1,y1 ... [--ignore REF,REF] [--ignore-net a,b]

Lists every item of another net closer than rules21.clearance_on (pours included: they would refill, flagged
'pour'), and SELV / PE copper inside the 8 mm plan-view barrier on any layer.
"""
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon

PS = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PS / "native-21/layout"))
import rules21  # noqa: E402

a = sys.argv[1:]
ign = set(); ignn = set()
for flag in ("--ignore", "--ignore-net"):
    if flag in a:
        i = a.index(flag); (ign if flag == "--ignore" else ignn).update(a[i + 1].split(",")); del a[i:i + 2]
dump, net, layer, width = a[0], a[1], a[2], float(a[3])
pts = [tuple(map(float, p.split(","))) for p in a[4:]]
d = json.loads(Path(dump).read_text())
geo = Point(pts[0]).buffer(width / 2) if len(pts) == 1 else LineString(pts).buffer(width / 2)
lays = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu") if layer == "via" else (layer,)
out = []
for z in d["zones"]:
    if z["net"] == net or z["net"] in ignn:
        continue
    p = Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0)
    dd = p.distance(geo)
    if z["layer"] in lays and dd < rules21.clearance_on(net, z["net"], z["layer"]):
        out.append((round(dd, 2), "pour", z["net"], z["layer"]))
    if rules21.barrier(net, z["net"]) and dd < rules21.BARRIER:
        out.append((round(dd, 2), "BARRIER pour", z["net"], z["layer"]))
for t in d["tracks"]:
    if t["net"] == net or t["net"] in ignn:
        continue
    g = LineString([t["a"], t["b"]]).buffer(t["w"] / 2) if t["a"] != t["b"] else Point(t["a"]).buffer(t["w"] / 2)
    dd = g.distance(geo)
    if t["layer"] in lays and dd < rules21.clearance_on(net, t["net"], t["layer"]):
        out.append((round(dd, 2), "track", t["net"], t["layer"], t["a"], t["b"]))
    if rules21.barrier(net, t["net"]) and dd < rules21.BARRIER:
        out.append((round(dd, 2), "BARRIER track", t["net"], t["layer"]))
for v in d["vias"]:
    if v["net"] == net or v["net"] in ignn:
        continue
    dd = Point(v["at"]).buffer(v["d"] / 2).distance(geo)
    if dd < max(rules21.clearance_on(net, v["net"], l) for l in lays):
        out.append((round(dd, 2), "via", v["net"], v["at"]))
    if rules21.barrier(net, v["net"]) and dd < rules21.BARRIER:
        out.append((round(dd, 2), "BARRIER via", v["net"], v["at"]))
for p in d["pads"]:
    if p["net"] == net or p["ref"] in ign or p["net"] in ignn:
        continue
    g = Polygon(p["pts"]).buffer(0)
    dd = g.distance(geo)
    on = p["tht"] or any(l in lays for l in p["layers"])
    if on and dd < (0.3 if not p["net"] else max(rules21.clearance_on(net, p["net"], l) for l in lays)):
        out.append((round(dd, 2), "pad", p["ref"], p["net"]))
    if p["net"] and rules21.barrier(net, p["net"]) and dd < rules21.BARRIER:
        out.append((round(dd, 2), "BARRIER pad", p["ref"], p["net"]))
for o in sorted(out, key=lambda o: o[0]):
    print(*o)
print(f"{len(out)} conflicts")
