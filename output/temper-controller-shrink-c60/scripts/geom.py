"""Footprint geometry in the appliance world frame, from results/c49-board.json (extract_c49.py).

World frame (C/layout/world.py:17-38): X right, Y rear; KiCad kx = X + 58, ky = 110 - Y.
A footprint at world (X0, Y0) with KiCad orientation t maps a local point (lx, ly) (KiCad footprint
coordinates, y down) to
    X = X0 + lx*cos(t) + ly*sin(t),   Y = Y0 + lx*sin(t) - ly*cos(t)
(kicad_courtyard.to_board() followed by the world transform).

`rect()` is the placement rectangle build_board.py uses (C/layout/build_board.py:205-216): the courtyard
bounding box united with every pad's box. Standard library only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

RES = Path(__file__).resolve().parent.parent / "results"


def load_parts():
    d = json.loads((RES / "c49-board.json").read_text())
    return {p["ref"]: p for p in d["parts"]}, d


def l2w(X0, Y0, t_deg, lx, ly):
    t = math.radians(t_deg)
    return X0 + lx * math.cos(t) + ly * math.sin(t), Y0 + lx * math.sin(t) - ly * math.cos(t)


def local_box(p):
    """Courtyard + pads bounding box in the footprint's local frame (x0, y0, x1, y1)."""
    xs, ys = [], []
    for loop in p["crtyd_local"]:
        for x, y in loop:
            xs.append(x)
            ys.append(y)
    for q in p["pads_local"]:
        xs += [q["x"] - q["w"] / 2, q["x"] + q["w"] / 2]
        ys += [q["y"] - q["h"] / 2, q["y"] + q["h"] / 2]
    return min(xs), min(ys), max(xs), max(ys)


def rect(p, X0, Y0, t):
    """World axis-aligned placement rectangle (X0, Y0, X1, Y1) at pose (X0, Y0, t); t multiple of 90."""
    x0, y0, x1, y1 = local_box(p)
    pts = [l2w(X0, Y0, t, x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    xs, ys = [a for a, _ in pts], [b for _, b in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def crtyd_world(p, X0, Y0, t):
    return [[l2w(X0, Y0, t, x, y) for x, y in loop] for loop in p["crtyd_local"]]


def pads_world(p, X0, Y0, t):
    out = []
    for q in p["pads_local"]:
        cx, cy = l2w(X0, Y0, t, q["x"], q["y"])
        w, h = (q["w"], q["h"]) if round(t) % 180 == 0 else (q["h"], q["w"])
        out.append({"num": q["num"], "net": q["net"], "x": cx, "y": cy, "w": w, "h": h, "kind": q["kind"]})
    return out


def origin_for_centre(p, cx, cy, t):
    """Footprint origin that puts the placement rectangle's centre at (cx, cy) for rotation t."""
    r = rect(p, 0.0, 0.0, t)
    return cx - (r[0] + r[2]) / 2, cy - (r[1] + r[3]) / 2


def overlap(a, b, gap=0.0):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def rect_gap(a, b):
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)
