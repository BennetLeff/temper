#!/usr/bin/env python3
"""KiCad Python: print courtyards (world mm) of every footprint touching a world rectangle, and
the pads of the named footprints. Review aid for floorplan edits.

    KICAD_PY evidence/c1-crs/dump_region.py BOARD X0 Y0 X1 Y1 [REF ...]
"""
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "layout"))
import world  # noqa: E402

b = pcbnew.LoadBoard(sys.argv[1])
x0, y0, x1, y1 = map(float, sys.argv[2:6])
want = set(sys.argv[6:])
mm = pcbnew.ToMM
for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if not fp.GetCourtyard(pcbnew.F_CrtYd).IsEmpty() else fp.GetBoundingBox()
    X0, Y1 = world.to_w(mm(bb.GetLeft()), mm(bb.GetTop()))
    X1, Y0 = world.to_w(mm(bb.GetRight()), mm(bb.GetBottom()))
    if X1 < x0 or X0 > x1 or Y1 < y0 or Y0 > y1:
        continue
    path = fp.GetFieldText("atopile_address") if fp.HasField("atopile_address") else ""
    print(f"{fp.GetReference():5s} crtyd X {X0:7.2f}..{X1:7.2f}  Y {Y0:6.2f}..{Y1:6.2f}  {fp.GetValue()[:18]:18s} {path}")
    if fp.GetReference() in want:
        for p in fp.Pads():
            px, py = world.to_w(mm(p.GetPosition().x), mm(p.GetPosition().y))
            print(f"      pad {p.GetNumber():>3s} ({px:7.2f}, {py:6.2f}) {p.GetNetname()}")
