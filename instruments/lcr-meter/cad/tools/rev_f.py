"""Rev F: the Rev E circuit re-laid on 100 x 100 mm, as explicit edits of the Rev E sources.

python3 cad/tools/rev_f.py [--check] [--render BLOCK,...|all] [--no-write]

Reads Rev E cad/design.json and cad/routing.json from git (48b012771), writes cad/design.json and
cad/routing.json.  Netlist and BOM are unchanged; placement, copper, outline, holes and silk change.
Plan and decisions: docs/rev-f-plan.md.

Method (hand routing in script form, as Rev E; no autorouter, no path search anywhere):
  * Rigid groups: Rev E sub-layouts moved as one body (translation, optionally a quarter turn about
    a pivot part).  Their intra-group Rev E copper is copied through the same transform.
  * Every other part is placed at the coordinates in PLACE below.
  * cad/tools/rev_f_routes.py adds every other segment and via by coordinates.  Helpers:
      P('U6.3', dx, dy)        board-frame pad centre after placement (+ offset)
      B('codec', x, y)         a Rev E coordinate taken through a rigid group's transform
      T(net, layer, *pts)      a polyline;  T45(net, layer, a, b, first) one orthogonal leg plus a
                               45-degree leg between two chosen points (pure geometry)
      V(net, x, y)             a via (0.3 mm drill, 0.45 mm or larger ring)
  * --check runs the KiCad-free pre-DRC (cad/tools/predrc.py) on the result: clearance, keepouts,
    edge, holes, via-on-land, connectivity; violations quote the rev_f_routes.py line.  --render
    writes build/rev-f-<block>.png with the violations and unrouted pads overlaid.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

CAD = Path(__file__).resolve().parents[1]
ROOT = CAD.parent
REV_E = '48b012771'
sys.path.insert(0, str(CAD / 'tools'))
import predrc  # noqa: E402


def git_json(name):
    out = subprocess.run(['git', 'show', f'{REV_E}:./{name}'], cwd=CAD, check=True,
                         capture_output=True, text=True).stdout
    return json.loads(out)


design = git_json('design.json')
rev_e_routing = git_json('routing.json')
parts = {p['ref']: p for p in design['parts']}
E_POSE = {r: tuple(p['pcb']) for r, p in parts.items()}       # Rev E (x, y, rot)
LIB = predrc.LIB


def rot(dx, dy, t):
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return dx * c + dy * s, -dx * s + dy * c


def unrot(dx, dy, t):
    return rot(dx, dy, -t)


def r3(v):
    return round(v + 0.0, 4)


def fp(ref):
    return LIB[parts[ref]['footprint'].split(':', 1)[1]]


def pad_local(ref, num):
    for p in fp(ref)['pads']:
        if p['num'] == num:
            return p['at']
    raise KeyError(f'{ref}.{num}')


def pad_at(ref, num, pose):
    lx, ly = pad_local(ref, num)
    bx, by = rot(lx, ly, pose[2])
    return (r3(pose[0] + bx), r3(pose[1] + by))


# ------------------------------------------------------------------ board
OUTLINE = [50, 45, 150, 145]
design['board'] = {
    'origin': [50, 45], 'size': [100, 100], 'outline': OUTLINE,
    'holes': [[54, 54], [146, 54], [54, 141], [146, 141]],
    'ref_text': {},
    'silk': [],          # filled at the end of this file once placement is known
}

# ------------------------------------------------------------------ rigid groups
# name: (pivot, to (x, y), quarter turn deg, members).  Positions from validation/rev-f-floorplan.
GROUPS = {
    'rp2040_core': ('U1', (74.0, 124.0), 0,
                    'U1 U2 Y1 C1 C2 C3 C4 C5 C6 C7 C8 C9 C10 C11 C12 C13 C14 R3 R4 R7 R8 R9 R10 R13'),
    # codec core plus the four input legs (shunts, 560 pF, 1 uF, clamps, 470R); the series
    # resistors R60/R61/R66/R67 move to their op-amp outputs instead (short buffer/TIA nodes).
    'codec': ('U14', (64.0, 88.5), 0,
              'U14 U15 C60 C61 C62 C63 C64 C65 C66 C67 C68 R72 R73 '
              'R62 R63 R64 R65 C69 C70 C72 C73 C74 C75 C76 C77 D11 D12 D13 D14 R68 R69 R70 R71'),
    'source': ('U5', (70.5, 65.5), 0, 'U5 R30 R31 R32 R33 C34 C35 C114 C115 C37 C38 C39 C40'),
    'ldo_pair': ('U11', (130.0, 100.0), 0,
                 'U11 U12 C93 C94 C95 C96 C97 C98 C99 C100 C101 C102 R85 R86 R87 R88 R89 R112 R95'),
    'switcher': ('U13', (137.5, 135.0), 90,
                 'U13 L1 L2 D2 D3 C81 C82 C83 C84 C85 C86 C87 C88 C89 C90 C91 C92 R80 R81 R82 R83 R84 R111'),
    'drivers': ('Q3', (89.0, 111.6), 0, 'Q2 Q3 Q4 Q5 R74 R75 R76 R77 R78 R79 R102 R103 D5 D6 D7 D8'),
}
GROUP_OF = {}
for name, (pivot, to, turn, refs) in GROUPS.items():
    GROUPS[name] = {'pivot': E_POSE[pivot][:2], 'to': to, 'turn': turn, 'refs': refs.split()}
    for r in GROUPS[name]['refs']:
        GROUP_OF[r] = name


def B(group, x, y):
    """A Rev E board coordinate taken through a rigid group's transform."""
    g = GROUPS[group]
    dx, dy = rot(x - g['pivot'][0], y - g['pivot'][1], g['turn'])
    return (r3(g['to'][0] + dx), r3(g['to'][1] + dy))


def norm_rot(t):
    t = (t + 180) % 360 - 180
    return 180 if t == -180 else t


for name, g in GROUPS.items():
    for r in g['refs']:
        x, y, t = E_POSE[r]
        parts[r]['pcb'] = [*B(name, x, y), norm_rot(t + g['turn'])]

# ------------------------------------------------------------------ placed parts (x, y, rot)
PLACE = {
    # front band: four BNCs on 22 mm pitch, mounting holes in the corners
    'J3': (67.0, 51.0, 0), 'J7': (89.0, 51.0, 0), 'J8': (111.0, 51.0, 0), 'J9': (133.0, 51.0, 0),
    # range relays, a column between the source buffer (west) and the TIA (east); K4 east
    'K1': (100.0, 65.0, 270), 'K2': (100.0, 80.0, 270), 'K3': (100.0, 95.0, 270),
    'K4': (138.0, 66.0, 90),
    # U6 high-side buffer and source follower
    'U6': (88.0, 66.0, 90),
    'C50': (85.3, 63.9, 90), 'C42': (83.7, 63.9, 90), 'C44': (81.9, 63.9, 90),
    'C51': (90.7, 68.1, 270), 'C43': (90.7, 70.4, 270), 'C45': (92.0, 74.6, 90),
    'R104': (86.2, 71.3, 270), 'R60': (86.4, 61.4, 180), 'R105': (90.9, 59.6, 180),
    'R40': (91.6, 67.54, 180), 'R41': (91.6, 82.54, 180), 'R42': (91.6, 97.54, 180),
    # U7 TIA and low-side buffer
    'U7': (114.5, 70.0, 90),
    'C104': (111.9, 73.3, 90), 'R43': (109.2, 73.4, 180), 'R45': (109.2, 75.1, 180),
    'R44': (109.2, 76.8, 180), 'R94': (113.9, 76.2, 180), 'C78': (117.0, 77.6, 90),
    'R67': (110.9, 69.4, 90), 'R61': (114.0, 63.0, 180), 'R66': (114.0, 64.6, 180),
    'C52': (112.0, 66.4, 90), 'C46': (110.4, 65.4, 90), 'C48': (108.6, 62.0, 90),
    'C53': (117.2, 72.5, 270), 'C47': (118.8, 72.5, 270), 'C49': (120.6, 72.5, 270),
    'R106': (118.6, 60.2, 90),
    # K4 reference relay driver and the DUT_LO reference resistor
    'R107': (131.0, 62.0, 90), 'Q6': (144.5, 78.0, 0), 'R108': (140.2, 77.0, 0), 'R109': (140.2, 78.8, 180),
    'D9': (146.5, 72.0, 90),
    # relay supply filter, at the relay column foot
    'R101': (100.0, 104.6, 0), 'C112': (103.4, 104.6, 0), 'FB1': (110.0, 120.0, 0), 'C103': (110.0, 123.0, 0),
    # power entry and digital extras
    'J1': (54.0, 122.0, -90), 'U16': (62.0, 114.0, 0), 'U3': (61.0, 140.0, 0),
    'R110': (63.6, 116.6, 180), 'C113': (60.86, 110.4, 90), 'C16': (66.0, 140.0, 90),
    'C80': (122.0, 132.0, 90), 'C17': (58.0, 136.0, 90), 'C18': (64.5, 136.0, 0),
    'D1': (60.0, 128.5, 0), 'C15': (58.0, 112.0, 0), 'R1': (58.0, 117.0, 0), 'R2': (58.0, 127.0, 0),
    'R5': (66.0, 108.0, 0), 'R6': (66.0, 110.0, 0),
    'D4': (59.5, 102.5, 0), 'R12': (63.0, 102.5, 0),
    'SW1': (88.0, 140.0, 0), 'SW2': (95.0, 140.0, 0),
    'J4': (103.0, 128.0, 0), 'J5': (103.0, 135.0, 0), 'J6': (108.0, 128.0, 0),
    'R98': (88.0, 123.0, 90), 'C110': (89.6, 123.0, 90), 'R99': (92.0, 123.0, 90), 'C111': (93.6, 123.0, 90),
    'R100': (120.0, 112.0, 0), 'R96': (124.0, 116.0, 90), 'R97': (118.0, 114.0, 0),
}
for r, at in PLACE.items():
    assert r not in GROUP_OF, f'{r} is in rigid group {GROUP_OF[r]}'
    parts[r]['pcb'] = list(at)
unplaced = sorted(set(parts) - set(PLACE) - set(GROUP_OF))
if unplaced:
    print('WARNING unplaced (left at Rev E coordinates):', ' '.join(unplaced))


def P(ref_pin, dx=0.0, dy=0.0):
    """Board-frame pad centre after placement, plus an optional offset."""
    ref, num = ref_pin.split('.')
    x, y = pad_at(ref, num, parts[ref]['pcb'])
    return (r3(x + dx), r3(y + dy))


# ------------------------------------------------------------------ copy rigid-group copper
def e_pad_boxes():
    """Rev E pad rectangles (board frame) per part, from the inventory used in phase 1."""
    inv = json.loads((ROOT / 'validation/rev-f-floorplan/rev-e-inventory.json').read_text())['parts']
    out = {}
    for r, p in inv.items():
        out[r] = [(x, y, *p['pad_half'][n], net) for n, (x, y, net) in p['pads'].items()]
    return inv, out


INV, E_PADS = e_pad_boxes()


def group_box(name, margin=0.6):
    xs, ys = [], []
    for r in GROUPS[name]['refs']:
        a, b = INV[r]['at'], INV[r]['courtyard_box_rel']
        xs += [a[0] + b[0], a[0] + b[2]]
        ys += [a[1] + b[1], a[1] + b[3]]
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def in_box(pt, bx):
    return bx[0] <= pt[0] <= bx[2] and bx[1] <= pt[1] <= bx[3]


def foreign_pad(pt, members):
    for r, pads in E_PADS.items():
        if r in members:
            continue
        for x, y, hx, hy, _ in pads:
            if abs(pt[0] - x) <= hx + 0.05 and abs(pt[1] - y) <= hy + 0.05:
                return r
    return None


routing = {'tracks': [], 'vias': [], 'zones': [], 'keepouts': []}
COPIED = {}
for name, g in GROUPS.items():
    members = set(g['refs'])
    nets = {n for r in members for n in parts[r]['pins'].values() if n}
    bx = group_box(name)
    nt = nv = 0
    for t in rev_e_routing['tracks']:
        if t['net'] not in nets:
            continue
        pts = [tuple(p) for p in t['points']]
        for a, b in zip(pts, pts[1:]):
            if a == b or not (in_box(a, bx) and in_box(b, bx)):
                continue
            if foreign_pad(a, members) or foreign_pad(b, members):
                continue
            routing['tracks'].append({'net': t['net'], 'layer': t['layer'], 'width': t.get('width', 0.2),
                                      'points': [list(B(name, *a)), list(B(name, *b))], 'src': f'copy:{name}'})
            nt += 1
    for v in rev_e_routing['vias']:
        if v['net'] in nets and in_box(v['at'], bx) and not foreign_pad(tuple(v['at']), members):
            routing['vias'].append(dict(v, at=list(B(name, *v['at'])), src=f'copy:{name}'))
            nv += 1
    COPIED[name] = (nt, nv)

# ------------------------------------------------------------------ zones and keepouts
routing['zones'] = [{'layer': 'In1.Cu', 'net': 'GND',
                     'points': [[50.5, 45.5], [149.5, 45.5], [149.5, 144.5], [50.5, 144.5]]}]


def move_poly(points, pivot_e, to, turn):
    out = []
    for x, y in points:
        dx, dy = rot(x - pivot_e[0], y - pivot_e[1], turn)
        out.append([r3(to[0] + dx), r3(to[1] + dy)])
    return out


# Rev E plane voids follow their op-amp: the source stage moves with its group, the U6/U7 pin voids
# turn with the IC (Rev E rotation -> Rev F rotation about the IC centre).
for ko in rev_e_routing['keepouts']:
    nm = ko['name']
    if nm.startswith('OPA810'):
        pts = [list(B('source', x, y)) for x, y in ko['points']]
    elif nm in ('OPA2810 high sense signal pins', 'U6 source follower output relief'):
        e, f = E_POSE['U6'], parts['U6']['pcb']
        pts = move_poly(ko['points'], e[:2], f[:2], f[2] - e[2])
    elif nm == 'OPA2810 TIA and low sense signal pins':
        e, f = E_POSE['U7'], parts['U7']['pcb']
        pts = move_poly(ko['points'], e[:2], f[:2], f[2] - e[2])
    else:
        continue      # TIA summing node and R94 relief are redrawn for the Rev F TIA in rev_f_routes.py
    routing['keepouts'].append(dict(ko, points=pts))

# ------------------------------------------------------------------ hand routes
SRC_FILE = CAD / 'tools' / 'rev_f_routes.py'


def _src():
    f = sys._getframe(2)
    return f'rev_f_routes.py:{f.f_lineno}' if f.f_code.co_filename.endswith('rev_f_routes.py') else 'rev_f.py'


def T(net, layer, *pts, w=0.2):
    pts = [P(p) if isinstance(p, str) else (r3(p[0]), r3(p[1])) for p in pts]
    routing['tracks'].append({'net': net, 'layer': layer, 'width': w, 'points': [list(p) for p in pts],
                              'src': _src()})


def T45(net, layer, a, b, first='h', w=0.2):
    """Two segments a -> corner -> b: one orthogonal leg and one 45-degree leg.  first='h' or 'v'
    puts the horizontal / vertical leg first; first='d' puts the diagonal first (the orthogonal leg
    then runs along whichever axis has the longer span).  Pure geometry: no obstacle awareness."""
    a = P(a) if isinstance(a, str) else a
    b = P(b) if isinstance(b, str) else b
    dx, dy = b[0] - a[0], b[1] - a[1]
    sx, sy = math.copysign(1, dx), math.copysign(1, dy)
    d = min(abs(dx), abs(dy))
    if first in ('h', 'v'):
        assert (first == 'h') == (abs(dx) >= abs(dy)), f'T45 {net}: first={first} but |dx|={abs(dx):.3f} |dy|={abs(dy):.3f}'
        c = (b[0] - sx * d, a[1]) if first == 'h' else (a[0], b[1] - sy * d)
    else:
        c = (a[0] + sx * d, a[1] + sy * d)
    routing['tracks'].append({'net': net, 'layer': layer, 'width': w,
                              'points': [[r3(a[0]), r3(a[1])], [r3(c[0]), r3(c[1])], [r3(b[0]), r3(b[1])]],
                              'src': _src()})


def V(net, x, y=None, d=0.45):
    if isinstance(x, str) or (isinstance(x, tuple) and y is None):
        x, y = P(x) if isinstance(x, str) else x
    routing['vias'].append({'net': net, 'at': [r3(x), r3(y)], 'diameter': d, 'drill': 0.3, 'src': _src()})


def KO(name, pts, layers=('In1.Cu', 'In2.Cu', 'B.Cu')):
    routing['keepouts'].append({'name': name, 'layers': list(layers), 'points': [list(p) for p in pts],
                                'tracks': True})


exec(compile(SRC_FILE.read_text(), str(SRC_FILE), 'exec'), globals())

# ------------------------------------------------------------------ prune copied copper left dangling
def prune_copied():
    """Copied Rev E copper that no longer leads anywhere (a stub cut at the group boundary, a via whose
    other layer went with it) is removed, iterating until none is left.  The test is the pre-DRC's
    dangling rule (calibrated against KiCad's via_dangling / track_dangling).  Hand-routed copper is
    never pruned: the pre-DRC reports it with its rev_f_routes.py line."""
    removed = 0
    while True:
        res = predrc.check({'parts': list(parts.values()), 'board': design['board']}, routing)
        drop = {v['item'] for v in res['violations'] if v['kind'] == 'dangling' and v.get('item')
                and str(v['src']).startswith('copy:')}
        if not drop:
            return removed
        removed += len(drop)
        routing['tracks'] = [t for i, t in enumerate(routing['tracks']) if ('track', i) not in drop]
        routing['vias'] = [v for i, v in enumerate(routing['vias']) if ('via', i) not in drop]


pruned = prune_copied()

# GND vias of the copied blocks that now sit on a hand-placed part's land are dropped (they belonged
# to Rev E neighbours); reported so a block's own stitching is never lost silently.
for v in routing['vias']:
    v['drill'] = 0.3
    v['diameter'] = max(v.get('diameter', 0.6), 0.45)

# ------------------------------------------------------------------ silk and reference text
design['board']['silk'] = [
    ['TEMPER LCR / REV F', 78, 47.2, 1.0],
    ['HCUR', 67, 58.2, 0.8], ['HPOT', 89, 58.2, 0.8], ['LPOT', 111, 58.2, 0.8], ['LCUR', 133, 58.2, 0.8],
    ['DISCHARGED DUT ONLY', 100, 47.2, 0.8],
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--render', default='')
    ap.add_argument('--no-write', action='store_true')
    a = ap.parse_args()
    design['parts'] = [parts[p['ref']] for p in design['parts']]
    print(f"{len(design['parts'])} parts, {len(routing['tracks'])} tracks, {len(routing['vias'])} vias; "
          f"copied {sum(n for n, _ in COPIED.values())} segments / {sum(v for _, v in COPIED.values())} vias, "
          f"pruned {pruned}")
    if a.check or a.render:
        res = predrc.check(design, routing)
        print(predrc.summary(res, limit=60))
        if a.render:
            names = list(VIEWS) if a.render == 'all' else a.render.split(',')
            for n in names:
                out = ROOT / 'build' / f'rev-f-{n}.png'
                predrc.render(design, routing, res, VIEWS[n], out, title=f'Rev F {n}')
                print('  render', out)
    if not a.no_write:
        clean = {'tracks': [{k: v for k, v in t.items() if k != 'src'} for t in routing['tracks']],
                 'vias': [{k: v for k, v in v.items() if k != 'src'} for v in routing['vias']],
                 'zones': routing['zones'], 'keepouts': routing['keepouts']}
        (CAD / 'design.json').write_text(json.dumps(design, indent=2) + '\n')
        (CAD / 'routing.json').write_text(json.dumps(clean, indent=2) + '\n')


VIEWS = {
    'bnc': (50, 45, 150, 62), 'afe_hi': (78, 55, 96, 105), 'relays': (90, 55, 112, 106),
    'tia': (104, 55, 126, 85), 'k4': (122, 55, 150, 86), 'source': (55, 55, 82, 80),
    'codec': (50, 74, 86, 102), 'ldo': (120, 84, 150, 114), 'drivers': (78, 100, 124, 118),
    'switcher': (116, 112, 150, 145), 'digital': (50, 100, 120, 145), 'board': (50, 45, 150, 145),
}

if __name__ == '__main__':
    main()
