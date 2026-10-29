"""Dump footprint-local pad and courtyard geometry for the KiCad-free pre-DRC (cad/tools/predrc.py).

Run with KiCad's bundled Python:  <kicad-python> cad/tools/pad_library.py [board] [OUT.json]
Read-only. Keys are footprint names (LCR:<name>); every footprint of that name has the same pads.
Pad offsets and orientations are in the footprint frame (rotation 0), so any placement can be
re-derived with KiCad's rotation convention: board = at + (x cos t + y sin t, -x sin t + y cos t).
"""
import json
import math
import sys
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
board = k.LoadBoard(str(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'temper-lcr.kicad_pcb'))
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name('pad_library.json')
MM = 1e-6
SHAPE = {k.PAD_SHAPE_RECT: 'rect', k.PAD_SHAPE_ROUNDRECT: 'roundrect', k.PAD_SHAPE_CIRCLE: 'circle',
         k.PAD_SHAPE_OVAL: 'oval', k.PAD_SHAPE_CUSTOM: 'custom'}
ATTR = {k.PAD_ATTRIB_SMD: 'smd', k.PAD_ATTRIB_PTH: 'pth', k.PAD_ATTRIB_NPTH: 'npth', k.PAD_ATTRIB_CONN: 'conn'}


def unrot(x, y, t):
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return x * c - y * s, x * s + y * c


lib = {}
for f in board.GetFootprints():
    name = f.GetFPID().GetLibItemName().wx_str()
    if name in lib:
        continue
    fx, fy, ft = f.GetPosition().x * MM, f.GetPosition().y * MM, f.GetOrientationDegrees()
    pads = []
    for p in f.Pads():
        lx, ly = p.GetFPRelativePosition().x * MM, p.GetFPRelativePosition().y * MM
        layers = [board.GetLayerName(l) for l in p.GetLayerSet().CuStack()]
        shape = SHAPE.get(p.GetShape(k.F_Cu), 'other')
        poly = None
        if shape == 'custom':
            ps = k.SHAPE_POLY_SET()
            p.TransformShapeToPolygon(ps, k.F_Cu, 0, 1000, k.ERROR_INSIDE)
            o = ps.Outline(0)
            poly = [list(unrot(o.CPoint(i).x * MM - fx, o.CPoint(i).y * MM - fy, ft)) for i in range(o.PointCount())]
        pads.append({'num': p.GetNumber(), 'at': [round(lx, 4), round(ly, 4)],
                     'rot': round((p.GetOrientationDegrees() - ft) % 360, 3),
                     'size': [round(p.GetSize(k.F_Cu).x * MM, 4), round(p.GetSize(k.F_Cu).y * MM, 4)],
                     'shape': shape, 'rr': round(p.GetRoundRectRadiusRatio(k.F_Cu), 4),
                     'drill': [round(p.GetDrillSize().x * MM, 4), round(p.GetDrillSize().y * MM, 4)],
                     'attr': ATTR.get(p.GetAttribute(), 'other'),
                     'copper': 'all' if len(layers) > 2 else [l for l in layers if l.endswith('.Cu')],
                     'poly': poly})
    cy = f.GetCourtyard(k.F_CrtYd)
    court = []
    for i in range(cy.OutlineCount()):
        o = cy.Outline(i)
        court.append([[round(v, 4) for v in unrot(o.CPoint(j).x * MM - fx, o.CPoint(j).y * MM - fy, ft)]
                      for j in range(o.PointCount())])
    lib[name] = {'pads': pads, 'courtyard': court}
out.write_text(json.dumps(lib, indent=0, sort_keys=True) + '\n')
print(f'{len(lib)} footprints -> {out}')
