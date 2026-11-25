"""Placement margin: re-run the C60 floorplan with a larger courtyard-to-courtyard gap for auto-placed parts.

C49's rule is 0.9 mm (C/layout/build_board.py:40: "room for a fan-out via and a track"). A larger gap that
still places every part means spare room for routing channels between passives.

    python3 -I scripts/gap_sweep.py -> results/gap-sweep.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import floorplan_c60 as f  # noqa: E402

rows = []
for g in (0.9, 1.2, 1.5, 1.8, 2.0, 2.5):
    o = f.build("acut", g, verbose=False, write=False)
    c = o["checks"]
    rows.append({"gap_mm": g, "status": o["status"], "placed": c["all_placed"]["placed"],
                 "unplaced": [u["ref"] + " " + str(u["path"]) for u in c["all_placed"]["unplaced"]],
                 "l2_to_rtd_mm": c["partition"]["separations_mm"]["L2/U2 (blower buck) -> RTD front end"]["mm"],
                 "decoupling_worst_mm": c["decoupling"]["worst_mm"]})
    print(rows[-1]["gap_mm"], rows[-1]["status"], rows[-1]["placed"], rows[-1]["unplaced"][:6])
(HERE.parent / "results" / "gap-sweep.json").write_text(json.dumps({"schema": "temper.controller-shrink-c60.gap-sweep.v1",
                                                                     "outline": "acut", "rows": rows}, indent=1))
