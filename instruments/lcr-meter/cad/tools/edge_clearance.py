"""Copper-to-edge distances per board edge, for the edge-rail (V-cut) decision.

Run with KiCad's bundled Python on a filled board (cad/rebuild.sh fills the zones):
    <kicad-python> cad/tools/edge_clearance.py [OUT.json]
Read-only. For each straight edge of the rectangular outline it reports the nearest copper on any layer
(pads, tracks, vias, filled zones), the nearest track or via, the nearest land, and every SMT land of
an assembled part within 2.0 mm of the edge.  Distances are from the copper outline, in mm.
"""
import hashlib
import json
import sys
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / 'validation' / 'edge-clearance-rev-f.json'
MM = 1e-6
board = k.LoadBoard(str(ROOT / 'temper-lcr.kicad_pcb'))
# outline from the Edge.Cuts centre lines (the bounding box would include half the 0.05 mm line width)
ends = [(pt.x * MM, pt.y * MM) for d in board.GetDrawings() if d.GetLayer() == k.Edge_Cuts
        for pt in (d.GetStart(), d.GetEnd())]
X0, Y0 = min(p[0] for p in ends), min(p[1] for p in ends)
X1, Y1 = max(p[0] for p in ends), max(p[1] for p in ends)
EDGES = {'front_y_min': lambda b: b[1] - Y0, 'back_y_max': lambda b: Y1 - b[3],
         'left_x_min': lambda b: b[0] - X0, 'right_x_max': lambda b: X1 - b[2]}
CU = [k.F_Cu, k.In1_Cu, k.In2_Cu, k.B_Cu]


def bbox(ps):
    pts = [(o.CPoint(j).x * MM, o.CPoint(j).y * MM) for i in range(ps.OutlineCount())
           for o in [ps.Outline(i)] for j in range(o.PointCount())]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def shape(item, layer):
    ps = k.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(ps, layer, 0, 1000, k.ERROR_OUTSIDE)
    return bbox(ps)


items = []          # (kind, who, layer, bbox)
for f in board.GetFootprints():
    assembled = not (f.GetAttributes() & (k.FP_BOARD_ONLY | k.FP_EXCLUDE_FROM_POS_FILES)) and not f.IsDNP()
    for p in f.Pads():
        for l in CU:
            if p.IsOnLayer(l):
                smt = assembled and p.GetAttribute() == k.PAD_ATTRIB_SMD and l == k.F_Cu
                items.append(('smt_land' if smt else 'land', f'{f.GetReference()}.{p.GetNumber()}',
                              board.GetLayerName(l), shape(p, l)))
for t in board.GetTracks():
    for l in CU:
        if t.IsOnLayer(l):
            items.append(('via' if isinstance(t, k.PCB_VIA) else 'track', t.GetNetname(), board.GetLayerName(l),
                          shape(t, l)))
for z in board.Zones():
    if z.GetIsRuleArea():
        continue
    for l in CU:
        if z.IsOnLayer(l) and z.GetFilledPolysList(l).OutlineCount():
            items.append(('zone_fill', z.GetNetname(), board.GetLayerName(l), bbox(z.GetFilledPolysList(l))))
if not any(i[0] == 'zone_fill' for i in items):
    sys.exit('no filled zones: run cad/rebuild.sh (or cad/fill_zones.py) first')


def nearest(fn, kinds):
    d, kind, who, layer = min((fn(b), kind, who, layer) for kind, who, layer, b in items if kind in kinds)
    return {'mm': round(d, 3), 'item': kind, 'who': who, 'layer': layer}


out = {'board': str((ROOT / 'temper-lcr.kicad_pcb').relative_to(ROOT.parent)),
       'board_sha256': hashlib.sha256((ROOT / 'temper-lcr.kicad_pcb').read_bytes()).hexdigest(),
       'outline_mm': [round(v, 3) for v in (X0, Y0, X1, Y1)], 'edges': {}}
for name, fn in EDGES.items():
    smt = {}
    for kind, who, _, b in items:
        ref = who.split('.')[0]
        if kind == 'smt_land' and fn(b) <= 2.0:
            smt[ref] = min(smt.get(ref, 9.0), round(fn(b), 3))
    out['edges'][name] = {
        'nearest_copper': nearest(fn, {'smt_land', 'land', 'track', 'via', 'zone_fill'}),
        'nearest_track_or_via': nearest(fn, {'track', 'via'}),
        'nearest_land': nearest(fn, {'smt_land', 'land'}),
        'smt_parts_within_2mm': [{'ref': r, 'mm': d} for r, d in sorted(smt.items(), key=lambda kv: kv[1])],
    }
OUT.write_text(json.dumps(out, indent=1) + '\n')
for name, v in out['edges'].items():
    print(f"{name:12s} copper {v['nearest_copper']['mm']:.3f} ({v['nearest_copper']['item']} {v['nearest_copper']['who']}), "
          f"track/via {v['nearest_track_or_via']['mm']:.3f}, land {v['nearest_land']['mm']:.3f} "
          f"({v['nearest_land']['who']}); SMT <= 2 mm: "
          + ', '.join(f"{p['ref']} {p['mm']:.2f}" for p in v['smt_parts_within_2mm']))
print('->', OUT)
