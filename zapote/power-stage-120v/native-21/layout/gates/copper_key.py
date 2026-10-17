#!/usr/bin/env python3
"""Fill-independent fingerprint of a built board's copper inputs, for the chain's task-04 and B3 caches.

    KICAD_PY copper_key.py BOARD.kicad_pcb   ->  prints a SHA-256

KiCad's zone refill is not bit-reproducible: the same authored copper refilled in another build gives fill polygons
with other start vertices, tessellation (0.01-0.05 mm2 per polygon) and zero-area slivers, and footprint order and UUIDs
change every build. A key over the filled copper therefore never hits across rebuilds (stage 22 warm rerun: B3 peak
162.04008064 vs 162.04008119 C, task 04 identical to the printed precision). This key covers what the fill is computed
from instead: tracks, arcs, vias, pads, zone outlines and fill settings, Edge.Cuts, the board's rules files (.kicad_dru
and .kicad_pro beside the board) and the KiCad version - all sorted, no UUIDs. Any authored change misses the cache;
a refill of the same inputs hits.
"""
import hashlib
import json
import sys
from pathlib import Path

import pcbnew

board_path = Path(sys.argv[1])
b = pcbnew.LoadBoard(str(board_path))


def pt(p):
    return [p.x, p.y]          # internal units (nm): exact integers


def layers(ls):
    return sorted(b.GetLayerName(l) for l in ls.Seq())


rows = []
for t in b.GetTracks():
    c = t.GetClass()
    r = {"k": c, "net": t.GetNetname(), "s": pt(t.GetStart()), "e": pt(t.GetEnd()), "w": t.GetWidth()}
    if c == "PCB_VIA":
        r.update(drill=t.GetDrillValue(), layers=layers(t.GetLayerSet()), type=int(t.GetViaType()))
    else:
        r["layer"] = b.GetLayerName(t.GetLayer())
        if c == "PCB_ARC":
            r["m"] = pt(t.GetMid())
    rows.append(r)
for f in b.GetFootprints():
    for p in f.Pads():
        rows.append({"k": "pad", "ref": f.GetReference(), "num": p.GetNumber(), "net": p.GetNetname(),
                     "pos": pt(p.GetPosition()), "size": pt(p.GetSize(pcbnew.F_Cu)), "shape": int(p.GetShape(pcbnew.F_Cu)),
                     "rot": round(p.GetOrientationDegrees(), 4), "drill": pt(p.GetDrillSize()), "attr": int(p.GetAttribute()),
                     "layers": layers(p.GetLayerSet()), "zc": int(p.GetLocalZoneConnection()),
                     "poly": str(p.GetEffectivePolygon(pcbnew.F_Cu).Format()) if p.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CUSTOM else ""})
for z in b.Zones():
    o = z.Outline()
    outline = []
    for i in range(o.OutlineCount()):
        outline.append([pt(o.COutline(i).CPoint(j)) for j in range(o.COutline(i).PointCount())])
        for h in range(o.HoleCount(i)):
            outline.append(["hole"] + [pt(o.CHole(i, h).CPoint(j)) for j in range(o.CHole(i, h).PointCount())])
    rows.append({"k": "zone", "net": z.GetNetname(), "layers": layers(z.GetLayerSet()), "prio": z.GetAssignedPriority(),
                 "rule_area": z.GetIsRuleArea(), "outline": outline, "clear": z.GetLocalClearance() or 0,
                 "minw": z.GetMinThickness(), "conn": int(z.GetPadConnection()), "tgap": z.GetThermalReliefGap(),
                 "spoke": z.GetThermalReliefSpokeWidth(), "islands": int(z.GetIslandRemovalMode()),
                 "fillmode": int(z.GetFillMode()),
                 "keepout": [z.GetDoNotAllowTracks(), z.GetDoNotAllowVias(), z.GetDoNotAllowPads(),
                             z.GetDoNotAllowZoneFills(), z.GetDoNotAllowFootprints()] if z.GetIsRuleArea() else []})
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        rows.append({"k": "edge", "shape": int(d.GetShape()), "s": pt(d.GetStart()), "e": pt(d.GetEnd()),
                     "c": pt(d.GetCenter()) if d.GetShape() in (pcbnew.SHAPE_T_ARC, pcbnew.SHAPE_T_CIRCLE) else []})

h = hashlib.sha256()
for line in sorted(json.dumps(r, sort_keys=True) for r in rows):
    h.update(line.encode())
for f in (board_path.with_suffix(".kicad_dru"), board_path.with_suffix(".kicad_pro")):
    h.update(f.read_bytes() if f.exists() else b"-")
h.update(pcbnew.GetBuildVersion().encode())
print(h.hexdigest())
