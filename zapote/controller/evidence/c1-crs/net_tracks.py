#!/usr/bin/env python3
"""KiCad Python: list the tracks and vias of one net (KiCad mm), optionally only those with x >= XMIN.

    KICAD_PY evidence/c1-crs/net_tracks.py BOARD NET [XMIN]
"""
import sys

import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
net = sys.argv[2]
xmin = float(sys.argv[3]) if len(sys.argv) > 3 else -1e9
mm = pcbnew.ToMM
for t in b.GetTracks():
    if t.GetNetname() != net:
        continue
    s, e = t.GetStart(), t.GetEnd()
    if max(mm(s.x), mm(e.x)) < xmin:
        continue
    print(t.GetClass(), t.GetLayerName(), round(mm(s.x), 3), round(mm(s.y), 3), "->", round(mm(e.x), 3),
          round(mm(e.y), 3), "w", round(mm(t.GetWidth()), 3))
