#!/usr/bin/env python3
"""Where native-21 can take an M3 fixing without bridging D5 (no native board has mounting holes).

    python3 native-21/verification/mounting_candidates.py <copper-dump.json>  ->  mounting-candidates.json

A metal screw, washer (Ø 7 mm) or standoff is chassis / PE. D5-BASIS needs ≥ 8.0 mm from every HOT
conductor to PE hardware. Keeping it off SELV copper too (≥ 1 mm) avoids a second
controller-ground–PE bond beyond the single R38 link. Candidates: board points with the washer
circle (r 3.5 mm) inside the outline, ≥ 8.0 mm from HOT copper and ≥ 1 mm from any other copper,
on every layer, and ≥ 1 mm from every component courtyard box (pads.json boxes + 1 mm).
"""
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "layout"))
import rules21  # noqa: E402

R_WASHER = 3.5
d = json.loads(Path(sys.argv[1]).read_text())
cu = [(p["net"], Polygon(p["pts"])) for p in d["pads"] if len(p.get("pts", [])) > 2] + \
     [(t["net"], LineString([t["a"], t["b"]]).buffer(t["w"] / 2)) for t in d["tracks"]] + \
     [(v["net"], Point(v["at"]).buffer(v["d"] / 2)) for v in d["vias"]] + [(z["net"], Polygon(z["pts"])) for z in d["zones"]]
hot = unary_union([g for n, g in cu if n in rules21.GROUP])
other = unary_union([g for n, g in cu if n not in rules21.GROUP])
from geom21 import EDGE  # noqa: E402  native-21's L-shaped outline
outline = Polygon(EDGE)
pads = json.loads((HERE.parent / "layout" / "pads.json").read_text())
parts = unary_union([box(*p["box"]).buffer(1.0) for p in pads])
cands = []
for i in range(0, 290, 2):
    for j in range(0, 190, 2):
        c = Point(i + 1.0, j + 1.0)
        w = c.buffer(R_WASHER)
        if not outline.buffer(-0.5).contains(w):
            continue
        if w.distance(hot) < rules21.BARRIER or w.distance(other) < 1.0 or w.intersects(parts):
            continue
        cands.append([c.x, c.y, round(w.distance(hot), 1)])
(HERE / "mounting-candidates.json").write_text(json.dumps({"rule": __doc__.split("\n\n")[1], "candidates": cands}, indent=0) + "\n")
print(len(cands), "candidate centres (2 mm grid)")
