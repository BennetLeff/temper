#!/usr/bin/env python3
"""Board mounting holes against the R43 standoffs (item 4 of the order checklist). Read-only.

    python3 -I validation-results/11-candidates/c53-astra-results/local/bosses/bosses_vs_r43.py

Board hole centres: native-21/layout/board_only21.json (`mounting_holes`, KiCad mm). Standoff centres: the bbox centres of
`electronics_native21_standoff_H*` in validation-plan/enclosure-fit/r43-catalog-bboxes.json (R43 world frame). The fit gate's
pose maps board to world as world = (x - 141, 236 - y) (board_in_r43.py). R43's standoff numbers are offset from the board's
hole numbers, so each hole is matched to the NEAREST standoff, not by name.
"""
import json, math
from pathlib import Path
U = Path(__file__).resolve().parents[5]
holes = json.loads((U / "native-21/layout/board_only21.json").read_text())["mounting_holes"]
items = json.loads((U / "validation-plan/enclosure-fit/r43-catalog-bboxes.json").read_text())["items"]
so = {i["name"].rsplit("_", 1)[-1]: ((i["bbox"][0] + i["bbox"][3]) / 2, (i["bbox"][1] + i["bbox"][4]) / 2)
      for i in items if i["name"].startswith("electronics_native21_standoff_")}
print("board hole | kind  | world (x, y)      | nearest R43 standoff | planar offset")
unsupported = []
for h in holes:
    x, y = h["at"]
    w = (x - 141, 236 - y)
    n, p = min(so.items(), key=lambda kv: math.dist(w, kv[1]))
    d = math.dist(w, p)
    if d > 0.5:
        unsupported.append(h["ref"])
    print(f"{h['ref']:10} | {h['kind']:5} | ({w[0]:7.1f},{w[1]:6.1f}) | {n:20} | {d:7.2f} mm" + ("  NO STANDOFF" if d > 0.5 else ""))
print(f"{len(holes)} board holes, {len(so)} R43 standoffs; holes with no standoff within 0.5 mm: {unsupported}")
