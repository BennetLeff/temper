"""Dump what the KiCad-free silk reference placement needs (craft.place_refs, called by rev_f.py).

Run with KiCad's bundled Python:  <kicad-python> cad/tools/silk_library.py [board] [OUT.json]
Read-only.  Writes cad/tools/silk_library.json:
  footprints  {name: [polygon, ...]}  each footprint's own F.SilkS graphics (outlines, pin-1 marks, text) as
              polygons with their stroke width, in the footprint frame (rotation 0), like pad_library.json
  text        {"<string>|<height>|<stroke>": {"0": [x0, y0, x1, y1], "90": [...]}}  KiCad's stroke-font ink
              box relative to the text position, at 0 and 90 degrees, for every reference designator (at
              design.board.ref_size) and every board silk label in design.json
Rerun it when a footprint, a reference or a label changes; rev_f.py stops on a missing entry.
"""
import json
import math
import sys
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
board = k.LoadBoard(str(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'temper-lcr.kicad_pcb'))
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name('silk_library.json')
design = json.loads((ROOT / 'design.json').read_text())
MM = 1e-6


def unrot(x, y, t):
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return x * c - y * s, x * s + y * c


def outlines(ps, fx=0.0, fy=0.0, ft=0.0):
    res = []
    for i in range(ps.OutlineCount()):
        o = ps.Outline(i)
        res.append([[round(v, 4) for v in unrot(o.CPoint(j).x * MM - fx, o.CPoint(j).y * MM - fy, ft)]
                    for j in range(o.PointCount())])
    return res


fps = {}
for f in board.GetFootprints():
    name = f.GetFPID().GetLibItemName().wx_str()
    if name in fps:
        continue
    fx, fy, ft = f.GetPosition().x * MM, f.GetPosition().y * MM, f.GetOrientationDegrees()
    ps = k.SHAPE_POLY_SET()
    for it in f.GraphicalItems():
        if it.GetLayer() == k.F_SilkS and not isinstance(it, k.PCB_FIELD):
            it.TransformShapeToPolygon(ps, k.F_SilkS, 0, 5000, k.ERROR_OUTSIDE)
    ps.Simplify()
    fps[name] = outlines(ps, fx, fy, ft)


def ink(s, h, w, angle):
    t = k.PCB_TEXT(board)
    t.SetText(s)
    t.SetTextSize(k.VECTOR2I(k.FromMM(h), k.FromMM(h)))
    t.SetTextThickness(k.FromMM(w))
    t.SetPosition(k.VECTOR2I(0, 0))
    t.SetTextAngleDegrees(angle)
    t.SetLayer(k.F_SilkS)
    ps = k.SHAPE_POLY_SET()
    t.TransformShapeToPolygon(ps, k.F_SilkS, 0, 5000, k.ERROR_OUTSIDE)
    b = ps.BBox()
    return [round(b.GetLeft() * MM, 4), round(b.GetTop() * MM, 4), round(b.GetRight() * MM, 4), round(b.GetBottom() * MM, 4)]


h, w = design.get('board', {}).get('ref_size', [0.8, 0.12])
strings = {(p['ref'], h, w) for p in design['parts']}
strings |= {(s, size, 0.15) for s, _, _, size in design.get('board', {}).get('silk', [])}
text = {f'{s}|{hh}|{ww}': {'0': ink(s, hh, ww, 0), '90': ink(s, hh, ww, 90)} for s, hh, ww in sorted(strings)}
out.write_text(json.dumps({'footprints': fps, 'text': text}, indent=0, sort_keys=True) + '\n')
print(f'{len(fps)} footprints, {len(text)} strings -> {out}')
