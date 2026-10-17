#!/usr/bin/env python3
"""Every populated-board body (STEP solids + model-less envelopes) against every R4 part.

    python3 board_in_enclosure.py BOXES.json COURTYARDS.json ENVELOPES.json [--x0 141 --y0 236 --zb 26 --rot 180]

Board-local boxes (board_boxes.py) are posed into the R4 frame (rot 180: world =
(x0 - x, y0 - y); board bottom at zb) and checked with fit_gate.box_hits
(1 mm gap, sensor corridor +3 mm, R4 roof). Exit 1 on any hit.
"""
import argparse
import json
import sys

import fit_gate as g

ap = argparse.ArgumentParser()
ap.add_argument("boxes"); ap.add_argument("courtyards"); ap.add_argument("envelopes")
ap.add_argument("--x0", type=float, default=141.0); ap.add_argument("--y0", type=float, default=236.0)
ap.add_argument("--zb", type=float, default=26.0); ap.add_argument("--rot", type=int, default=180)
a = ap.parse_args()
boxes = json.load(open(a.boxes))["boxes"]
crt = json.load(open(a.courtyards))
# The STEP board slab is one AABB over the whole L outline; replace it by the real rectangles.
slab = [b for b in boxes if b[5] - b[2] < 2 and (b[3] - b[0]) * (b[4] - b[1]) > 30000]
boxes = [b for b in boxes if b not in slab]
for b in slab:
    boxes += [[0, 0, b[2], 290, 140, b[5]], [0, 140, b[2], 91, 190, b[5]]]   # native-21 L outline
for r, h in json.load(open(a.envelopes)).items():
    boxes.append([*crt[r][:2], 1.6, *crt[r][2:], 1.6 + h])
items = g.catalog_names(g.R4)
hits = []
for b in boxes:
    if a.rot == 180:
        w = [a.x0 - b[3], a.y0 - b[4], a.zb + b[2], a.x0 - b[0], a.y0 - b[1], a.zb + b[5]]
    else:
        w = [a.x0 + b[0], a.y0 + b[1], a.zb + b[2], a.x0 + b[3], a.y0 + b[4], a.zb + b[5]]
    h = g.box_hits(w, items)
    if h:
        hits.append({"local": [round(v, 1) for v in b], "world": [round(v, 1) for v in w], "hits": h[:4]})
print(json.dumps({"bodies": len(boxes), "hits": hits}, indent=1))
sys.exit(1 if hits else 0)
