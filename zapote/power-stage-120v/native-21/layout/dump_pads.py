#!/usr/bin/env python3
"""Dump pad geometry of the placed native-21 board for authoring (route21.py).

    KICAD_PY dump_pads.py BOARD.kicad_pcb OUT.json
Each pad: ref, pad number, net, centre, bounding box, through-hole flag, footprint centre.
"""
import json
import sys

import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
mm = pcbnew.ToMM
out = []
for f in b.GetFootprints():
    fc = f.GetPosition()
    for p in f.Pads():
        bb = p.GetBoundingBox()
        out.append({"ref": f.GetReference(), "pad": p.GetNumber(), "net": p.GetNetname(),
                    "x": round(mm(p.GetPosition().x), 4), "y": round(mm(p.GetPosition().y), 4),
                    "box": [round(mm(v), 4) for v in (bb.GetX(), bb.GetY(), bb.GetRight(), bb.GetBottom())],
                    "tht": p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH),
                    "npth": p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH,
                    "fc": [round(mm(fc.x), 3), round(mm(fc.y), 3)]})
json.dump(out, open(sys.argv[2], "w"))
