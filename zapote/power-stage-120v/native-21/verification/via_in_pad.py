#!/usr/bin/env python3
"""Count 0.3 mm-drill vias whose drill sits fully inside, or overlaps the edge of, an SMD pad.

    KiCad python3 via_in_pad.py BOARD.kicad_pcb   ->  {"vias": {size: n}, "inside": n, "edge": n}

The drill circle is sampled at its centre and four extreme points against each nearby SMD pad's
effective polygon on its own copper layer. Used for FAB-NOTE's POFV via-in-pad census.
"""
import collections
import json
import sys

import pcbnew

mm = pcbnew.ToMM
b = pcbnew.LoadBoard(sys.argv[1])
vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
sizes = collections.Counter(f"{mm(v.GetWidth(pcbnew.F_Cu)):g}/{mm(v.GetDrillValue()):g}" for v in vias)
pads = [p for p in b.GetPads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
inside = edge = 0
for v in vias:
    if abs(mm(v.GetDrillValue()) - 0.3) > 1e-6:
        continue
    r = mm(v.GetDrillValue()) / 2
    x, y = mm(v.GetPosition().x), mm(v.GetPosition().y)
    hit = None
    for p in pads:
        bb = p.GetBoundingBox()
        if not (mm(bb.GetX()) - 1 < x < mm(bb.GetRight()) + 1 and mm(bb.GetY()) - 1 < y < mm(bb.GetBottom()) + 1):
            continue
        poly = p.GetEffectivePolygon(p.GetPrincipalLayer())
        pts = [pcbnew.VECTOR2I(pcbnew.FromMM(x + dx * r), pcbnew.FromMM(y + dy * r))
               for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (0, 0))]
        inn = [poly.Contains(q) for q in pts]
        if all(inn):
            hit = "in"
            break
        if any(inn):
            hit = "edge"
    inside += hit == "in"
    edge += hit == "edge"
print(json.dumps({"vias": dict(sizes), "inside": inside, "edge": edge}))
