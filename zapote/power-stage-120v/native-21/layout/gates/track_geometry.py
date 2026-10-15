#!/usr/bin/env python3
"""Track-geometry hygiene of a built board, from its all-copper export (tools/export_power_copper.py).

    python3 -I native-21/layout/gates/track_geometry.py BOARD-all-copper.json.gz [--json OUT]

Counted per (net, layer), at every vertex where exactly two track segments of that net meet (T-junctions and pad
ends are not corners):
  right_angle_corners  interior angle 90 deg (+/-0.5): conventional practice mitres these to 2 x 135 deg;
  acute_corners        interior angle < 89.5 deg, including 0 deg fold-backs (a track that doubles back on itself is
                       redundant copper); acute copper corners are the classic etch-trap DFM flag;
  fold_backs           the 0 deg subset of acute_corners;
  any_angle_mm         total length of segments not on a 45 deg multiple (+/-0.5 deg).
Lower is better for all four (scorecard.py, DECISIONS 43). Coordinates are rounded to 1 um to find shared vertices.
"""
import argparse
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path


def measure(prims):
    tracks = [p for p in prims if p["kind"] == "track"]
    vert = defaultdict(list)
    any_mm = 0.0
    for t in tracks:
        (x0, y0), (x1, y1) = t["start"], t["end"]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        a = math.degrees(math.atan2(dy, dx)) % 45.0
        if 0.5 <= a <= 44.5:
            any_mm += length
        a0, a1 = (round(x0, 3), round(y0, 3)), (round(x1, 3), round(y1, 3))
        vert[(t["net"], t["layer"], a0)].append(a1)
        vert[(t["net"], t["layer"], a1)].append(a0)
    right = acute = fold = 0
    for (_, _, v), ends in vert.items():
        if len(ends) != 2:
            continue
        (ax, ay), (bx, by) = ends
        u, w = (ax - v[0], ay - v[1]), (bx - v[0], by - v[1])
        nu, nw = math.hypot(*u), math.hypot(*w)
        if nu < 1e-6 or nw < 1e-6:
            continue
        ang = math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * w[0] + u[1] * w[1]) / (nu * nw)))))
        if abs(ang - 90.0) < 0.5:
            right += 1
        elif ang < 89.5:
            acute += 1
            fold += ang < 0.5
    return {"right_angle_corners": right, "acute_corners": acute, "fold_backs": fold, "any_angle_mm": round(any_mm, 1)}


def load(path):
    p = Path(path)
    return json.loads((gzip.open(p) if p.suffix == ".gz" else p.open()).read())["primitives"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("export")
    ap.add_argument("--json")
    a = ap.parse_args()
    res = measure(load(a.export))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res))


if __name__ == "__main__":
    main()
