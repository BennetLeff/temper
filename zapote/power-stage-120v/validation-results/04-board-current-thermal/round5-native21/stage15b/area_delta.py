#!/usr/bin/env python3
"""Copper area change per net/layer between two all-copper exports (zones + pads + tracks), FET-row window.

    python3 area_delta.py <base.json.gz> <cand.json.gz>  -> stdout
"""
import gzip
import json
import sys
from collections import defaultdict

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

WIN = box(0, 0, 110, 35)


def areas(f):
    d = json.load(gzip.open(f, "rt"))
    g = defaultdict(list)
    for q in d["primitives"]:
        if q["kind"] in ("zone", "pad"):
            s = Polygon(q["shell"], q["holes"])
        elif q["kind"] == "track":
            s = LineString([q["start"], q["end"]]).buffer(q["width_mm"] / 2)
        elif q["kind"] == "via":
            s = Point(q["centre"]).buffer(q["diameter_mm"] / 2)
        else:
            continue
        g[(q["net"], q["layer"])].append(s)
    return {k: unary_union(v).intersection(WIN).area for k, v in g.items()}


a, b = areas(sys.argv[1]), areas(sys.argv[2])
for k in sorted(set(a) | set(b)):
    dv = b.get(k, 0) - a.get(k, 0)
    if abs(dv) > 0.05:
        print(k, round(a.get(k, 0), 2), "->", round(b.get(k, 0), 2), f"({dv:+.2f} mm2)")
