#!/usr/bin/env python3
"""Populated-board part boxes from a KiCad STEP export (CadQuery).

    python board_boxes.py BOARD.step OUT.json

Writes one axis-aligned box per solid in BOARD-LOCAL coordinates: x right
(KiCad x), y down (KiCad y; the STEP's y is negated), z up from the board's
bottom face. Boxes are conservative for fit (AABB >= solid).
"""
import hashlib
import json
import sys

import cadquery as cq

step, out = sys.argv[1], sys.argv[2]
shape = cq.importers.importStep(step).val()
boxes = []
for s in shape.Solids():
    b = s.BoundingBox()
    boxes.append([round(b.xmin, 3), round(-b.ymax, 3), round(b.zmin, 3),
                  round(b.xmax, 3), round(-b.ymin, 3), round(b.zmax, 3)])
json.dump({"step_sha256": hashlib.sha256(open(step, "rb").read()).hexdigest(),
           "frame": "board-local: x right, y down (KiCad), z up from board bottom; mm",
           "boxes": boxes}, open(out, "w"), indent=0)
print(len(boxes), "boxes")
