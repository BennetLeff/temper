"""Export native KiCad copper geometry for parasitic extraction (read-only).

Run with KiCad's bundled Python (pcbnew).  Writes geometry.json next to this
file.  Nothing in the board is modified: the zone refill check runs on an
in-memory copy and is only compared, never saved.

Usage:  <kicad-python> export_geometry.py [board.kicad_pcb]
"""
from pathlib import Path
import hashlib
import json
import os
import sys

import pcbnew as k

HERE = Path(__file__).resolve().parent
board_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else \
    (HERE / '../../cad/temper-lcr.kicad_pcb').resolve()
board = k.LoadBoard(str(board_path))
NM = 1e-6  # KiCad internal units (nm) -> mm
CU = [k.F_Cu, k.In1_Cu, k.In2_Cu, k.B_Cu]


def polyset_to_list(ps):
    """SHAPE_POLY_SET -> list of polygons, each [outline, hole, hole...] in mm."""
    out = []
    for i in range(ps.OutlineCount()):
        rings = []
        o = ps.Outline(i)
        rings.append([[o.CPoint(j).x * NM, o.CPoint(j).y * NM] for j in range(o.PointCount())])
        for h in range(ps.HoleCount(i)):
            hh = ps.Hole(i, h)
            rings.append([[hh.CPoint(j).x * NM, hh.CPoint(j).y * NM] for j in range(hh.PointCount())])
        out.append(rings)
    return out


items = []
for t in board.GetTracks():
    if isinstance(t, k.PCB_VIA):
        p = t.GetPosition()
        items.append({'kind': 'via', 'net': t.GetNetname(), 'x': p.x * NM, 'y': p.y * NM,
                      'dia': t.GetWidth(k.F_Cu) * NM, 'drill': t.GetDrillValue() * NM,
                      'layers': [board.GetLayerName(l) for l in CU
                                 if t.IsOnLayer(l)]})
    elif isinstance(t, k.PCB_ARC):
        raise SystemExit('arcs present: extend exporter')
    else:
        a, e = t.GetStart(), t.GetEnd()
        items.append({'kind': 'track', 'net': t.GetNetname(), 'layer': board.GetLayerName(t.GetLayer()),
                      'x1': a.x * NM, 'y1': a.y * NM, 'x2': e.x * NM, 'y2': e.y * NM,
                      'w': t.GetWidth() * NM})

for fp in board.GetFootprints():
    for pad in fp.Pads():
        polys = {}
        for l in CU:
            if not pad.IsOnLayer(l):
                continue
            ps = k.SHAPE_POLY_SET()
            pad.TransformShapeToPolygon(ps, l, 0, 1000, k.ERROR_INSIDE)
            polys[board.GetLayerName(l)] = polyset_to_list(ps)
        if not polys:
            continue
        p = pad.GetPosition()
        items.append({'kind': 'pad', 'ref': fp.GetReference(), 'pad': pad.GetNumber(),
                      'net': pad.GetNetname(), 'x': p.x * NM, 'y': p.y * NM,
                      'pth': pad.GetAttribute() == k.PAD_ATTRIB_PTH,
                      'drill': pad.GetDrillSize().x * NM, 'polys': polys})

zones = []
refill_check = []
for z in board.Zones():
    if z.GetIsRuleArea():
        continue
    for l in CU:
        if not z.IsOnLayer(l):
            continue
        fl = z.GetFilledPolysList(l)
        zones.append({'net': z.GetNetname(), 'layer': board.GetLayerName(l),
                      'filled': polyset_to_list(fl), 'area_mm2': fl.Area() * NM * NM})

# Confirm the stored fill is current: refill an in-memory copy and compare areas.
filler = k.ZONE_FILLER(board)
stored = [z['area_mm2'] for z in zones]          # same zone/layer order as the export loop
filler.Fill(board.Zones())
n = 0
for z in board.Zones():
    if z.GetIsRuleArea():
        continue
    for l in CU:
        if z.IsOnLayer(l):
            a = z.GetFilledPolysList(l).Area() * NM * NM
            s = stored[n]
            n += 1
            if s == 0:
                continue
            refill_check.append({'net': z.GetNetname(), 'layer': board.GetLayerName(l),
                                 'stored_mm2': round(s, 4), 'refilled_mm2': round(a, 4),
                                 'rel_diff': abs(a - s) / s})

rule_areas = []
for z in board.Zones():
    if z.GetIsRuleArea():
        rule_areas.append({'name': z.GetZoneName(),
                           'layers': [board.GetLayerName(l) for l in CU if z.IsOnLayer(l)],
                           'outline': polyset_to_list(z.Outline())})

out = {'board': str(board_path.name),
       'board_sha256': hashlib.sha256(board_path.read_bytes()).hexdigest(),
       'kicad_version': k.Version(),
       'items': items, 'zones': zones, 'zone_refill_check': refill_check,
       'rule_areas': rule_areas}
(HERE / os.environ.get('LP_GEOMETRY', 'geometry.json')).write_text(json.dumps(out, separators=(',', ':')))
print('items', len(items), 'zones', len(zones), 'refill', refill_check)
