#!/usr/bin/env python3
"""Shared helpers for the G02/G03 power-path scripts (stdlib + numpy + scipy + shapely).

Everything is read-only against the repo: the copper dump of record is
native-21/verification/native21s19c-all-copper.json.gz (stage 19c, board SHA-256 3d3a2c69...).
Run any script with `python3 -I <script>`; none of them writes outside this folder's results/ directory.
"""
import gzip
import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
FOLDER = HERE.parent                      # .../11-candidates/g02-g03-power-path
PS = HERE.parents[3]                      # .../zapote/power-stage-120v
RESULTS = FOLDER / "results"
COPPER_19C = PS / "native-21/verification/native21s19c-all-copper.json.gz"
F1C = PS / "validation-results/02-protection-timing/shoot-through-f1/f1_containment.py"

# native-21/stackup.json (mm): copper thickness and centre-to-centre layer spacing
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
CU_T = {"F.Cu": 0.070, "In1.Cu": 0.061, "In2.Cu": 0.061, "B.Cu": 0.070}
DZ = {("F.Cu", "In1.Cu"): 0.4355 / 1 + 0.035 + 0.0305,     # 0.501
      ("In1.Cu", "In2.Cu"): 0.5 + 0.0305 + 0.0305,          # 0.561
      ("In2.Cu", "B.Cu"): 0.4355 + 0.0305 + 0.035}          # 0.501
RHO20 = 1.724e-8                      # ohm m, copper at 20 C (task-04 uses 20 C copper)
MU0 = 4e-7 * math.pi

# DRC clearances measured from the stage-19c dump (see clearances.py): same potential group 0.2 mm,
# different HOT groups 3.2 mm (section.kicad_dru "HOT functional between potential groups").
CLR_LOW = 0.2
CLR_HOT = 3.2


def load_copper(path=COPPER_19C):
    return json.load(gzip.open(path))


def fix(g):
    return g if g.is_valid else g.buffer(0)


def geom(p, via_ring=True):
    k = p["kind"]
    if k == "track":
        return LineString([p["start"], p["end"]]).buffer(p["width_mm"] / 2, cap_style="round")
    if k == "via":
        c = Point(p["centre"])
        g = c.buffer(p["diameter_mm"] / 2)
        return g.difference(c.buffer(p["drill_mm"] / 2)) if via_ring else g
    return fix(Polygon(p["shell"], p.get("holes") or []))


def net_layer_geom(prims, net, layer):
    gs = [geom(p) for p in prims if p["net"] == net and p["layer"] == layer]
    return unary_union(gs) if gs else Polygon()


def pad_centre(p):
    xs = [a for a, b in p["shell"]]
    ys = [b for a, b in p["shell"]]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def drill_d(p):
    d = p.get("drill_mm")
    if isinstance(d, (list, tuple)):
        return max(d) if d else 0.0
    return d or 0.0
