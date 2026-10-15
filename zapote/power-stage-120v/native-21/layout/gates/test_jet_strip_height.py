#!/usr/bin/env python3
"""Tests for jet_strip_height.py: synthetic boxes, then the committed board's boxes.

    python3 native-21/layout/gates/test_jet_strip_height.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import jet_strip_height as j  # noqa: E402

fails = 0


def ok(cond, msg):
    global fails
    print(("ok   " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1


BOARD = [-5, -5, 0.0, 300, 200, 1.6]
COURT = {"LOW": [10, 10, 14, 14], "TALL": [40, 15, 46, 21], "OUT": [100, 10, 110, 20], "EDGE": [88, 22, 95, 30]}

r = j.check([BOARD, [11, 11, 0, 13, 13, 2.6]], COURT)
ok(r["pass"] and r["worst_ref"] == "LOW" and abs(r["max_height_mm"] - 1.0) < 1e-9, "a 1 mm part in the strip passes")
r = j.check([BOARD, [41, 16, 0, 45, 20, 6.0]], COURT)
ok(not r["pass"] and r["over_limit"] == ["TALL"], "a 4.4 mm part in the strip fails")
r = j.check([BOARD, [41, 16, 0, 45, 20, 5.6]], COURT)
ok(r["pass"], "exactly 4.0 mm passes (limit inclusive)")
r = j.check([BOARD, [101, 11, 0, 109, 19, 12.0]], COURT)
ok(r["pass"] and not r["parts"], "a tall part outside the strip is ignored")
r = j.check([BOARD, [89, 23, 0, 94, 29, 9.0]], COURT)
ok(not r["pass"] and r["over_limit"] == ["EDGE"], "a tall part whose body only overlaps the strip edge fails (AABB rule)")
r = j.check([BOARD, [30, 30, 0, 31, 31, 9.0], [30, 12, 0, 31, 13, 9.0]], COURT)
ok(not r["pass"] and r["over_limit"] == ["UNATTRIBUTED"], "an unattributed tall solid in the strip fails")

boxes = UNIT / "validation-plan/enclosure-fit/native21-boxes.json"
court = UNIT / "validation-plan/enclosure-fit/native21-courtyards.json"
if boxes.exists() and court.exists():
    r = j.check(json.loads(boxes.read_text())["boxes"], json.loads(court.read_text()))
    ok(r["pass"] and r["max_height_mm"] < 2.0, f"committed board passes, max {r['max_height_mm']} mm ({r['worst_ref']})")

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
