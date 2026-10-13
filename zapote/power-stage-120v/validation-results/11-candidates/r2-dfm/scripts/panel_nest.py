#!/usr/bin/env python3
"""Does the L-shaped 290 x 190 outline nest 2-up (second copy rotated 180 deg) into a smaller panel bounding box?

    python3 -I panel_nest.py  ->  results/panel_nest.json
Spacing 2.0 mm (JLC mouse-bite panel spacing 1.6 or 2 mm). Rails not included. Geometry only: whether JLC bills a
panel by its bounding box, and whether a >250 x 250 mm panel is acceptable, are questions for JLC (PROPOSALS 4).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shapely import affinity
from shapely.geometry import Polygon
from shapely.prepared import prep

from common import R2, copper

d = copper()
a = Polygon(d["outline"]["shell"])
x0, y0, x1, y1 = a.bounds
a = affinity.translate(a, -x0, -y0)
W, H = x1 - x0, y1 - y0
b0 = affinity.rotate(a, 180, origin=(W / 2, H / 2))
pa = prep(a.buffer(1.0))
best = None
for dx in range(-int(W), int(W) + 1, 2):
    for dy in range(-int(H), int(H) + 1, 2):
        b = affinity.translate(b0, dx, dy)
        if pa.intersects(b.buffer(1.0)) and a.buffer(1.0).intersection(b.buffer(1.0)).area > 1e-6:
            continue
        ux0 = min(0, b.bounds[0]); ux1 = max(W, b.bounds[2]); uy0 = min(0, b.bounds[1]); uy1 = max(H, b.bounds[3])
        area = (ux1 - ux0) * (uy1 - uy0)
        if best is None or area < best[0]:
            best = (area, dx, dy, ux1 - ux0, uy1 - uy0)
res = {"single_bbox_mm": [round(W, 1), round(H, 1)], "single_bbox_cm2": round(W * H / 100, 1),
       "outline_cm2": round(a.area / 100, 1),
       "two_up_best": {"panel_bbox_mm": [round(best[3], 1), round(best[4], 1)], "panel_cm2": round(best[0] / 100, 1),
                       "dx": best[1], "dy": best[2]},
       "panel_cm2_per_board": round(best[0] / 200, 1),
       "bbox_saving_pct_vs_two_singles": round(100 * (1 - best[0] / (2 * W * H)), 1)}
json.dump(res, open(R2 / "results/panel_nest.json", "w"), indent=1)
print(json.dumps(res, indent=1))
