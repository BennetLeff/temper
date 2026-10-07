#!/usr/bin/env python3
"""Part-to-part 3D body collision gate for a populated board.

    KICAD_PY body_collisions.py --dump-courtyards BOARD.kicad_pcb OUT.json   (KiCad python)
    python3  body_collisions.py BOXES.json COURTYARDS.json                   (host python)

BOXES.json comes from board_boxes.py (one AABB per STEP solid). Each solid is
attributed to the smallest footprint courtyard containing its XY centre, then
every pair of solids from DIFFERENT parts is checked for 3D AABB overlap
(> 0.05 mm on all three axes). AABBs are conservative: any real body collision
is reported, and so may some near-misses of round parts. Exit 1 on any overlap
or unattributed solid.
"""
import json
import sys

if len(sys.argv) == 4 and sys.argv[1] == "--dump-courtyards":
    import pcbnew
    b = pcbnew.LoadBoard(sys.argv[2])
    out = {}
    for f in b.GetFootprints():
        c = f.GetCourtyard(pcbnew.F_CrtYd)
        bb = c.BBox() if c.OutlineCount() else f.GetBoundingBox(False, False)
        out[f.GetReference()] = [bb.GetX() / 1e6, bb.GetY() / 1e6, (bb.GetX() + bb.GetWidth()) / 1e6, (bb.GetY() + bb.GetHeight()) / 1e6]
    json.dump(out, open(sys.argv[3], "w"))
    sys.exit(0)

import numpy as np

boxes = np.array(json.load(open(sys.argv[1]))["boxes"])
crt = json.load(open(sys.argv[2]))
area = (boxes[:, 3] - boxes[:, 0]) * (boxes[:, 4] - boxes[:, 1])
boxes = boxes[~((boxes[:, 5] - boxes[:, 2] < 2) & (area > 30000))]   # the board slab


def owner(s):
    cx, cy = (s[0] + s[3]) / 2, (s[1] + s[4]) / 2
    best = None
    for r, (x0, y0, x1, y1) in crt.items():
        if x0 - 0.5 <= cx <= x1 + 0.5 and y0 - 0.5 <= cy <= y1 + 0.5:
            a = (x1 - x0) * (y1 - y0)
            if best is None or a < best[1]:
                best = (r, a)
    return best[0] if best else None


own = [owner(s) for s in boxes]
hits = []
for i in range(len(boxes)):
    for j in range(i + 1, len(boxes)):
        if own[i] == own[j]:
            continue
        o = np.minimum(boxes[i, 3:], boxes[j, 3:]) - np.maximum(boxes[i, :3], boxes[j, :3])
        if (o > 0.05).all():
            hits.append({"parts": [own[i], own[j]], "overlap_mm": np.round(o, 2).tolist()})
res = {"solids": len(boxes), "unattributed": sum(o is None for o in own), "part_overlaps": hits}
print(json.dumps(res, indent=1))
sys.exit(1 if hits or res["unattributed"] else 0)
