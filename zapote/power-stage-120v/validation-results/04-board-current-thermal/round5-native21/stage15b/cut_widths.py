#!/usr/bin/env python3
"""Vertical cross-section widths of the tank copper beside the FETs, from an all-copper export.

    python3 cut_widths.py <all-copper.json.gz> [...]  -> stdout + out/cut_widths.json (appends by file)
SW_A B.Cu link cut at x over y 0-16 (Q3.3 55.5, Q2.2 68.05 necks); SW_B B.Cu lane cut over y 12-30;
SW_A F.Cu cut over x 72-84 at y (the Q2.3 neck / BR1 corner).
"""
import gzip
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

res = {}
for f in sys.argv[1:]:
    d = json.load(gzip.open(f, "rt"))
    def cu(net, layer):
        return unary_union([Polygon(q["shell"], q["holes"]) for q in d["primitives"]
                            if q["kind"] in ("zone", "pad") and q["net"] == net and q["layer"] == layer])
    a_b, b_b, a_f = cu("sw_a", "B.Cu"), cu("sw_b", "B.Cu"), cu("sw_a", "F.Cu")
    r = {}
    for x in (52.0, 55.5, 58.0, 61.0, 64.0, 68.05, 70.0):
        r[f"sw_a B.Cu link at x {x}"] = round(a_b.intersection(LineString([(x, 0), (x, 16)])).length, 2)
        r[f"sw_b B.Cu lane at x {x}"] = round(b_b.intersection(LineString([(x, 12), (x, 30)])).length, 2)
    for y in (7.0, 8.0, 9.0, 9.5):
        r[f"sw_a F.Cu right of Q2.3 at y {y}"] = round(a_f.intersection(LineString([(74.75, y), (84, y)])).length, 2)
    res[f] = r
    print(Path(f).parent.name, r)
Path("out/cut_widths.json").write_text(json.dumps(res, indent=1) + "\n")
