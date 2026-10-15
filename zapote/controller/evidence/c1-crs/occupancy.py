#!/usr/bin/env python3
"""Print the placed parts inside a world rectangle (review aid for floorplan edits).

    python3 evidence/c1-crs/occupancy.py X0 Y0 X1 Y1 [placement.json] [netlist]
Uses pcb/placement.json (designator -> world X, Y, rot) and the netlist for instance paths.
"""
import json
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(UNIT / "tools"))
from netlist import read_netlist  # noqa: E402

x0, y0, x1, y1 = map(float, sys.argv[1:5])
place = json.loads(Path(sys.argv[5] if len(sys.argv) > 5 else UNIT / "pcb/placement.json").read_text())
nl = read_netlist(Path(sys.argv[6]) if len(sys.argv) > 6 else UNIT / "frozen/default.net")
for ref, (x, y, r) in sorted(place.items(), key=lambda kv: (round(kv[1][1]), kv[1][0])):
    if x0 <= x <= x1 and y0 <= y <= y1:
        print(f"{ref:5s} {x:8.2f} {y:7.2f} {r:6.0f}  {nl.refs.get(ref, '?')}")
