#!/usr/bin/env python3
"""Plan-view D5 barrier check of a routed native-21 board (all copper layers together).

    python3 barrier21.py copper-dump.json [--floor 8.0]
Reads the dump written by plot_copper.py --dump (filled pours, tracks, vias, pads) and reports
every SELV/PE - HOT pair of copper items closer than the floor in plan view, regardless of
layer. Pads of one footprint that straddles the barrier (isolators, opto, PS1, T1, Y caps) are
judged by their component rating and skipped against each other.
"""
import json
import sys

from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

import rules21

floor = float(sys.argv[sys.argv.index("--floor") + 1]) if "--floor" in sys.argv else rules21.BARRIER
d = json.load(open(sys.argv[1]))
items = []
for z in d["zones"]:
    items.append((Polygon(z["pts"], z["holes"]).buffer(0), z["net"], None))
for t in d["tracks"]:
    items.append((LineString([t["a"], t["b"]]).buffer(t["w"] / 2), t["net"], None))
for v in d["vias"]:
    items.append((Point(*v["at"]).buffer(v["d"] / 2), v["net"], None))
for p in d["pads"]:
    if p["net"]:
        items.append((Polygon(p["pts"]).buffer(0), p["net"], p["ref"]))
items = [i for i in items if rules21.domain(i[1]) in ("SELV", "PE", "HOT")]
tree = STRtree([g for g, _, _ in items])
bad = []
for k, (g, n, ref) in enumerate(items):
    if rules21.domain(n) == "HOT":
        continue
    for j in tree.query(g.buffer(floor)):
        h, m, ref2 = items[j]
        if not rules21.barrier(n, m) or (ref and ref == ref2):
            continue
        dist = g.distance(h)
        if dist < floor - 0.01:
            bad.append((round(dist, 3), n, m, [round(c, 1) for c in g.centroid.coords[0]],
                        [round(c, 1) for c in h.centroid.coords[0]], ref, ref2))
bad.sort()
print(f"barrier (plan view, {floor} mm): {len(bad)} violations")
for b in bad[:25]:
    print("  ", b)
sys.exit(1 if bad else 0)
