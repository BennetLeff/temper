#!/usr/bin/env python3
"""Every populated-board body (STEP solids + model-less envelopes) against every R4 part.

    python3 board_in_enclosure.py BOXES.json COURTYARDS.json ENVELOPES.json [--pose translate|rot180|mirror-legacy
                                  --x0 X --y0 Y --zb 26]

Board-local boxes (board_boxes.py: x right, y down, KiCad frame) are posed into a right-handed world
(Z up) and checked with fit_gate.box_hits (1 mm gap, sensor corridor +3 mm, R4 roof). Exit 1 on any hit.
  translate:     world = (x0 + x, y0 - y)   (board seen from above as in KiCad; R31 uses x0 -149, y0 236)
  rot180:        world = (x0 - x, y0 + y)
  mirror-legacy: world = (x0 - x, y0 - y)   the R4-R30 pose (x0 141, y0 236). It is a REFLECTION: no real board
                 can be mounted so. Kept only to reproduce stage <= 13 records (DECISIONS 2026-10-09).

Current enclosure (stage 53; s52 footprint/3D review item 23): the chain runs
    --pose translate --x0 -141 --y0 236 --zb 26 --catalog r43-catalog-bboxes.json --lead-trim 2.5
i.e. pose (a) as built in R31+ (world = (x - 141, 236 - y, 26 + z), DECISIONS 2026-10-09) against the frozen R43 solids
(r43_catalog_snapshot.py). With a snapshot catalog the R4 roof, R4 interior and R4 sensor corridor are not used: the R43
glass, sensor and controls are catalog solids, and the interior is the P4 U-wrapper's box less its 1.27 mm wall (the
wrapper's own AABB holds the whole interior, so it cannot be an obstacle). Skipped as obstacles: the harness group (cable
AABBs span the routing volume, not solids), *_ENVELOPE allocations (the board and its components replace them) and the
board slab itself. --lead-trim clips every box below the board bottom to the assembly rule (THT leads trimmed to
<= 2.5 mm, ASSEMBLY.md; DECISIONS 2026-10-09): the STEP carries untrimmed tails to -14.2 mm.
"""
import argparse
import json
import sys

import fit_gate as g

ap = argparse.ArgumentParser()
ap.add_argument("boxes"); ap.add_argument("courtyards"); ap.add_argument("envelopes")
ap.add_argument("--x0", type=float, default=141.0); ap.add_argument("--y0", type=float, default=236.0)
ap.add_argument("--zb", type=float, default=26.0)
ap.add_argument("--pose", choices=("translate", "rot180", "mirror-legacy"), default="mirror-legacy")
ap.add_argument("--catalog", default=None, help="frozen catalog snapshot (r43_catalog_snapshot.py); default the R4 catalog")
ap.add_argument("--lead-trim", type=float, default=None, help="clip boxes below the board bottom to -MM (lead-trim rule)")
a = ap.parse_args()
WALL = 1.27            # R43 P4 U-wrapper, 5052-H32 0.050 in
SHELL = "enclosure_P4_U_wrapper"
boxes = json.load(open(a.boxes))["boxes"]
crt = json.load(open(a.courtyards))
# The STEP board slab is one AABB over the whole L outline; replace it by the real rectangles.
slab = [b for b in boxes if b[5] - b[2] < 2 and (b[3] - b[0]) * (b[4] - b[1]) > 30000]
boxes = [b for b in boxes if b not in slab]
for b in slab:
    boxes += [[0, 0, b[2], 290, 140, b[5]], [0, 140, b[2], 91, 190, b[5]]]   # native-21 L outline
for r, h in json.load(open(a.envelopes)).items():
    boxes.append([*crt[r][:2], 1.6, *crt[r][2:], 1.6 + h])
if a.catalog:
    snap = json.load(open(a.catalog))
    shell = [x["bbox"] for x in snap["items"] if x["name"] == SHELL]
    if len(shell) != 1:
        raise SystemExit(f"{a.catalog}: shell {SHELL} not found once")
    sh = shell[0]
    interior = [sh[0] + WALL, sh[1] + WALL, sh[2] + WALL, sh[3] - WALL, sh[4] - WALL, sh[5] - WALL]
    items = [x for x in snap["items"] if x["group"] != "harness" and not x["name"].endswith("_ENVELOPE")
             and x["name"] not in (SHELL, "electronics_native21_board")]
else:
    items = g.catalog_names(g.R4)
if a.lead_trim is not None:
    boxes = [b if b[2] >= -a.lead_trim else [b[0], b[1], -a.lead_trim, b[3], b[4], max(b[5], -a.lead_trim)]
             for b in boxes]


def snapshot_hits(w):
    gp = g.GAP
    out = [x["name"] for x in items if x["bbox"][0] < w[3] + gp and x["bbox"][3] > w[0] - gp and
           x["bbox"][1] < w[4] + gp and x["bbox"][4] > w[1] - gp and x["bbox"][2] < w[5] + gp and x["bbox"][5] > w[2] - gp]
    if not (interior[0] <= w[0] and w[3] <= interior[3] and interior[1] <= w[1] and w[4] <= interior[4]
            and interior[2] <= w[2] and w[5] <= interior[5]):
        out.append("OUTSIDE_INTERIOR")
    return out


hits = []
for b in boxes:
    if a.pose == "mirror-legacy":
        w = [a.x0 - b[3], a.y0 - b[4], a.zb + b[2], a.x0 - b[0], a.y0 - b[1], a.zb + b[5]]
    elif a.pose == "rot180":
        w = [a.x0 - b[3], a.y0 + b[1], a.zb + b[2], a.x0 - b[0], a.y0 + b[4], a.zb + b[5]]
    else:
        w = [a.x0 + b[0], a.y0 - b[4], a.zb + b[2], a.x0 + b[3], a.y0 - b[1], a.zb + b[5]]
    h = snapshot_hits(w) if a.catalog else g.box_hits(w, items)
    if h:
        hits.append({"local": [round(v, 1) for v in b], "world": [round(v, 1) for v in w], "hits": h[:4]})
print(json.dumps({"bodies": len(boxes), "pose": a.pose, "x0": a.x0, "y0": a.y0, "zb": a.zb,
                  "catalog": (json.load(open(a.catalog))["revision"] if a.catalog else "R4"),
                  "catalog_sha256": (json.load(open(a.catalog))["source_sha256"] if a.catalog else None),
                  "lead_trim_mm": a.lead_trim, "hits": hits}, indent=1))
sys.exit(1 if hits else 0)
