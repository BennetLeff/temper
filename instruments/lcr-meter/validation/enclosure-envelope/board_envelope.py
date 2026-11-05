"""The board's mechanical envelope, for any enclosure (read-only).

~/.local/share/temper/cadenv/bin/python validation/enclosure-envelope/board_envelope.py
  -> board-envelope.json, and a summary on stdout.

The enclosure is being redesigned, so this does not check a box. It reports what any box must accommodate:
part heights above and below the board, everything that reaches past the board edge (BNC barrels, USB-C,
the side-looking status LED), the mounting-hole pattern and what sits near each hole, the user-access parts
(BOOTSEL/RESET, debug LEDs), and the BNC front-panel numbers.

Method: KiCad's Python dumps every footprint (position, rotation, side, pads, 3D model path); OCP reads each
STEP model's bounding box (KiCad models are in mm, z = 0 on the board's top face, offsets and rotations
are all zero on this board, asserted below); the box is rotated and placed like the footprint. A bounding
box is conservative for heights and overhangs.
"""
import json
import math
import os
import pathlib
import subprocess
import sys
import tempfile

from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KPY = '/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3'
MODEL_DIR = '/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels'
BOARD_T = 1.6

# Datasheet numbers used below (SAMZO BNC-KYWE-295-W4-N drawing BNCKYWE-P03900, sources/rev-f/BNC-KYWE-295-W4-N.txt).
BNC = {'axis_above_board': 13.55 / 2, 'flange_dia': 13.55, 'flange_proud_of_edge': 0.1, 'barrel_past_flange': 18.4,
       'thread_len': 6.6, 'nut_af': 13.95, 'washer_dia': 15.5}
M3 = {'clear_radius': 3.5}  # M3 pan/cheese head 5.5-6 mm, washer 7 mm, standoff 5.5 A/F (6.35 across corners)
# Copper under a metal standoff or screw head is separated from it by solder mask only, which is not an insulator
# to rely on: rev-f-plan.md (2026-10-29, chassis grounding) wants the mounting holes to make no bond.

DUMP = r'''
import json, sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
mm = pcbnew.ToMM
bb = b.GetBoardEdgesBoundingBox()
out = {'outline': [mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())], 'fps': []}
for fp in b.GetFootprints():
    pads = [{'x': mm(p.GetPosition().x), 'y': mm(p.GetPosition().y), 'attr': int(p.GetAttribute()),
             'drill': mm(p.GetDrillSize().x)} for p in fp.Pads()]
    fab = [it.GetBoundingBox() for it in fp.GraphicalItems() if it.GetLayer() == pcbnew.F_Fab
           and it.GetClass() == 'PCB_SHAPE']
    fab_bb = [min(mm(f.GetX()) for f in fab), min(mm(f.GetY()) for f in fab),
              max(mm(f.GetRight()) for f in fab), max(mm(f.GetBottom()) for f in fab)] if fab else None
    out['fps'].append({'ref': fp.GetReference(), 'value': fp.GetValue(), 'lib': str(fp.GetFPID().GetLibItemName()),
        'x': mm(fp.GetPosition().x), 'y': mm(fp.GetPosition().y), 'rot': fp.GetOrientationDegrees(),
        'back': fp.IsFlipped(), 'dnp': bool(fp.IsDNP()), 'pads': pads, 'fab': fab_bb,
        'models': [{'file': m.m_Filename, 'offset': [m.m_Offset.x, m.m_Offset.y, m.m_Offset.z],
                    'rotation': [m.m_Rotation.x, m.m_Rotation.y, m.m_Rotation.z],
                    'scale': [m.m_Scale.x, m.m_Scale.y, m.m_Scale.z], 'show': m.m_Show} for m in fp.Models()]})
import math
out['hole_copper'] = {}
for fp in b.GetFootprints():
    if 'MountingHole' not in str(fp.GetFPID().GetLibItemName()):
        continue
    c = pcbnew.VECTOR2I(fp.GetPosition().x, fp.GetPosition().y)
    for L in (pcbnew.F_Cu, pcbnew.B_Cu):
        best = (1e9, None)
        for z in b.Zones():
            if z.IsOnLayer(L) and z.GetFilledPolysList(L).OutlineCount():
                d = mm(math.sqrt(z.GetFilledPolysList(L).SquaredDistance(c)))
                best = min(best, (d, 'zone ' + z.GetNetname()))
        for t in b.GetTracks():
            if t.IsOnLayer(L):
                best = min(best, (mm(t.GetEffectiveShape(L).Distance(c)), 'track/via ' + t.GetNetname()))
        for f in b.GetFootprints():
            for p in f.Pads():
                if p.IsOnLayer(L) and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                    best = min(best, (mm(p.GetEffectiveShape(L).Distance(c)), f'pad {f.GetReference()} {p.GetNetname()}'))
        out['hole_copper'].setdefault(fp.GetReference(), {})[b.GetLayerName(L)] = [round(best[0], 2), best[1]]
print(json.dumps(out))
'''


def dump():
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
        f.write(DUMP)
    r = subprocess.run([KPY, f.name, str(ROOT / 'cad/temper-lcr.kicad_pcb')], capture_output=True, text=True)
    os.unlink(f.name)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith('{')]
    if not line:
        sys.exit(r.stdout + r.stderr)
    return json.loads(line[-1])


_cache = {}


def step_bbox(path):
    if path not in _cache:
        rd = STEPControl_Reader()
        if rd.ReadFile(path) != IFSelect_RetDone:
            raise RuntimeError(f'cannot read {path}')
        rd.TransferRoots()
        box = Bnd_Box()
        BRepBndLib.Add_s(rd.OneShape(), box)
        _cache[path] = box.Get()  # xmin, ymin, zmin, xmax, ymax, zmax
    return _cache[path]


def place(fp, bb):
    """Model box -> board coordinates. Model y is up; the board's y is down; KiCad rotates counter-clockwise."""
    x0, y0, z0, x1, y1, z1 = bb
    th = math.radians(fp['rot'])
    xs, ys = [], []
    for mx in (x0, x1):
        for my in (y0, y1):
            lx, ly = mx, -my
            xs.append(fp['x'] + lx * math.cos(th) + ly * math.sin(th))
            ys.append(fp['y'] - lx * math.sin(th) + ly * math.cos(th))
    return [min(xs), min(ys), max(xs), max(ys)], [z0, z1]


def dist_point_box(px, py, b):
    dx = max(b[0] - px, 0, px - b[2])
    dy = max(b[1] - py, 0, py - b[3])
    return math.hypot(dx, dy)


def main():
    d = dump()
    ox0, oy0, ox1, oy1 = d['outline']
    parts = []
    for fp in d['fps']:
        assert not fp['back'], f"{fp['ref']} is on the back; this script assumes a top-only board"
        for m in fp['models']:
            assert m['offset'] == [0, 0, 0] and m['rotation'] == [0, 0, 0] and m['scale'] == [1, 1, 1], fp['ref']
        files = [m['file'].replace('${KICAD10_3DMODEL_DIR}', MODEL_DIR).replace('${KIPRJMOD}', str(ROOT / 'cad'))
                 for m in fp['models'] if m['show']]
        if not files:
            continue
        bb = step_bbox(files[0])
        xy, z = place(fp, bb)
        tht = any(p['attr'] == 0 for p in fp['pads'])  # pcbnew.PAD_ATTRIB_PTH == 0 in KiCad 10 (SMD 1, NPTH 3)
        parts.append({'ref': fp['ref'], 'value': fp['value'], 'lib': fp['lib'], 'dnp': fp['dnp'], 'tht': tht,
                      'xy': [round(v, 2) for v in xy], 'z': [round(z[0], 2), round(z[1], 2)], 'fab': fp['fab'],
                      'model': os.path.basename(files[0])})

    # A 3D model whose footprint-plane box is off-centre from the footprint's own F.Fab body outline by more than
    # 0.3 mm. Gull-wing leads make a model wider than the body outline on both sides equally; that is not a shift.
    model_vs_fab = []
    for p in parts:
        if not p['fab']:
            continue
        dev = [round(a - b, 2) for a, b in zip(p['xy'], p['fab'])]
        shift = [round((dev[0] + dev[2]) / 2, 2), round((dev[1] + dev[3]) / 2, 2)]
        if max(map(abs, shift)) > 0.3:
            model_vs_fab.append({'ref': p['ref'], 'value': p['value'], 'model_xy': p['xy'],
                                 'fab_xy': [round(v, 2) for v in p['fab']], 'model_minus_fab': dev,
                                 'centre_shift_xy_mm': shift})
    tall = sorted(parts, key=lambda p: -p['z'][1])
    below = sorted([p for p in parts if p['z'][0] < -BOARD_T + 1e-3], key=lambda p: p['z'][0])
    edges = []
    for p in parts:
        x0, y0, x1, y1 = p['xy']
        for edge, past in (('front (y min)', oy0 - y0), ('back (y max)', y1 - oy1),
                           ('left (x min)', ox0 - x0), ('right (x max)', x1 - ox1)):
            if past > -0.5:
                edges.append({'ref': p['ref'], 'value': p['value'], 'edge': edge, 'past_edge_mm': round(past, 2),
                              'span_mm': [round(x0, 2), round(x1, 2)] if 'y' in edge else [round(y0, 2), round(y1, 2)],
                              'z_mm': p['z']})
    holes = []
    for fp in d['fps']:
        if 'MountingHole' not in fp['lib']:
            continue
        near = sorted(((round(dist_point_box(fp['x'], fp['y'], q['xy']), 2), q['ref'], q['z'][1]) for q in parts
                       if q['ref'] != fp['ref']))[:3]
        cu = d['hole_copper'][fp['ref']]
        holes.append({'ref': fp['ref'], 'x': fp['x'], 'y': fp['y'], 'drill': fp['pads'][0]['drill'] if fp['pads'] else None,
                      'nearest_parts_mm': near, 'parts_clear_of_m3_hardware': near[0][0] >= M3['clear_radius'],
                      'nearest_copper_mm': cu,
                      'outer_copper_clear_of_m3_hardware': min(v[0] for v in cu.values()) >= M3['clear_radius']})
    hx = sorted({h['x'] for h in holes})
    hy = sorted({h['y'] for h in holes})

    bnc = sorted([p for p in parts if p['lib'].startswith('BNC')], key=lambda p: p['xy'][0])
    centres = [(p['xy'][0] + p['xy'][2]) / 2 for p in bnc]
    pitch = [round(b - a, 2) for a, b in zip(centres, centres[1:])]
    nut_corners = BNC['nut_af'] / math.cos(math.radians(30))
    switches = [p for p in parts if p['ref'].startswith('SW')]
    leds = [p for p in parts if p['ref'].startswith('D') and 'LED' in p['lib']]

    out = {
        'generated_by': 'validation/enclosure-envelope/board_envelope.py',
        'board': {'outline_mm': d['outline'], 'size_mm': [round(ox1 - ox0, 3), round(oy1 - oy0, 3)],
                  'thickness_mm': BOARD_T, 'front_edge': 'y min (BNC side)'},
        'tallest_top': [{'ref': p['ref'], 'value': p['value'], 'height_mm': p['z'][1], 'model': p['model']}
                        for p in tall[:12]],
        'below_board': [{'ref': p['ref'], 'value': p['value'], 'tht': p['tht'], 'dnp': p['dnp'],
                         'below_bottom_face_mm': round(-BOARD_T - p['z'][0], 2)} for p in below],
        'past_or_within_0p5_of_edge': edges,
        'mounting_holes': {'holes': holes, 'pattern_mm': [round(hx[-1] - hx[0], 3), round(hy[-1] - hy[0], 3)],
                           'clear_radius_assumed_mm': M3['clear_radius']},
        'bnc_panel': {'centres_x_mm': centres, 'pitch_mm': pitch, 'axis_above_board_top_mm': BNC['axis_above_board'],
                      'nut_across_corners_mm': round(nut_corners, 2),
                      'gap_between_nut_corners_mm': round(min(pitch) - nut_corners, 2),
                      'barrel_past_flange_mm': BNC['barrel_past_flange'], 'thread_len_mm': BNC['thread_len'],
                      'drawing': 'SAMZO BNCKYWE-P03900 (sources/rev-f/BNC-KYWE-295-W4-N.txt)'},
        'user_access': {'switches': [{'ref': p['ref'], 'value': p['value'], 'xy': p['xy'], 'top_mm': p['z'][1],
                                      'to_back_edge_mm': round(oy1 - p['xy'][3], 2)} for p in switches],
                        'leds': [{'ref': p['ref'], 'value': p['value'], 'xy': p['xy'], 'top_mm': p['z'][1]} for p in leds]},
        'model_off_centre_from_fab_over_0p3mm': model_vs_fab,
        'parts_modelled': len(parts),
    }
    (HERE / 'board-envelope.json').write_text(json.dumps(out, indent=1) + '\n')
    print('board', out['board']['size_mm'], 'parts with models', len(parts))
    print('tallest:', [(t['ref'], t['height_mm']) for t in out['tallest_top'][:8]])
    print('below bottom face:', [(b['ref'], b['below_bottom_face_mm'], 'DNP' if b['dnp'] else '') for b in out['below_board']])
    for e in edges:
        print('edge:', e)
    for h in holes:
        print('hole:', h)
    print('bnc:', out['bnc_panel'])
    print('access:', out['user_access']['switches'])
    for m in model_vs_fab:
        print('model vs fab:', m)


if __name__ == '__main__':
    main()
