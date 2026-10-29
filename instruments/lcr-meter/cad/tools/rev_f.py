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
    'rp2040_core': ('U1', (74.0, 123.5), 0,
                    'U1 U2 Y1 C1 C2 C3 C4 C5 C6 C7 C8 C9 C10 C11 C12 C13 C14 R3 R4 R7 R8 R9 R10 R13 '
                    'C18 R5 R6'),   # + the 3V3 bulk cap and the VBUS sense divider at their Rev E offsets
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
    # USB-C receptacle with its CC resistors, ESD array and VBUS cap: the Rev E fan-out moves 45 mm south
    'usb': ('J1', (54.0, 122.0), 0, 'J1 D1 R1 R2 C15'),
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
    # U6 high-side buffer and source follower (90: HPOT/HIGH_BUF/12V north, SRC_DRV/EXCITE/-12V south)
    'U6': (86.5, 66.0, 90),
    'C50': (83.9, 64.0, 90),
    'C51': (89.1, 67.6, 90),
    'R104': (85.1, 71.2, 270), 'R60': (85.6, 59.9, 90), 'R105': (88.9, 60.3, 90),
    'R40': (91.9, 67.54, 180), 'R41': (91.9, 82.54, 180), 'R42': (91.9, 97.54, 180),
    # U6 second-tier bypass on its supply taps (12V west tap, -12V south tap)
    'C42': (85.9, 79.6, 0), 'C44': (86.0, 81.6, 0), 'C43': (87.4, 74.6, 180), 'C45': (87.2, 76.8, 180),
    # U7 TIA (SUM node west, plane void under it) and low-side buffer (R61/R66 north)
    'U7': (114.5, 70.0, 90),
    'C104': (112.15, 73.8, 90), 'R43': (109.6, 74.575, 180), 'R45': (109.6, 77.9, 180),
    'R44': (109.6, 76.2, 180), 'R94': (113.8, 76.7, 90), 'C78': (113.8, 79.8, 270),
    'R67': (110.9, 69.4, 90), 'R61': (114.0, 62.0, 180), 'R66': (114.0, 63.6, 180),
    'C52': (112.2, 65.9, 90), 'C46': (110.5, 65.9, 90), 'C48': (108.6, 64.6, 90),
    'C53': (117.2, 72.5, 270), 'C47': (118.8, 72.5, 270), 'C49': (120.6, 72.6, 270),
    'R106': (118.8, 60.0, 180),
    # K4 reference relay driver and the DUT_LO reference resistor
    'R107': (129.6, 63.46, 0), 'Q6': (144.5, 78.0, 0), 'R108': (140.2, 77.0, 0), 'R109': (140.2, 78.8, 180),
    'D9': (146.5, 72.0, 90),
    # relay supply filter, at the relay column foot
    'R101': (100.5, 106.4, 0), 'C112': (103.3, 107.0, 270),
    # power entry and digital extras
    # power entry under the receptacle: TPS2553 (IN/EN east, OUT/ILIM west), C113 at IN, C16 shared by
    # U16 OUT and U3 IN, U3 with C17 at OUT; the 5 V trunk leaves on B.Cu east of U3
    'U16': (55.6, 129.9, 180), 'C113': (59.2, 130.0, -90), 'R110': (52.0, 129.9, 90),
    'C16': (55.0, 132.9, 180), 'U3': (56.85, 135.9, 0), 'C17': (60.0, 135.65, -90),
    # codec 5VA filter at U15
    'FB1': (53.0, 87.0, 90), 'C103': (55.2, 87.0, -90),
    # TPS65131 input bulk at L1's 5 V end
    'C80': (125.6, 143.0, 180),
    # debug headers (DNP lands) and buttons: SWD north-west of U1 (its SWD pins face north), UART, buttons,
    # status LED and the 3V3/GND header south-east of U1, at the ends of the In2 run along the south edge
    'J4': (69.0, 108.0, -90), 'J6': (86.5, 139.0, -90), 'J5': (86.0, 131.0, 180),
    'SW1': (85.2, 143.1, 0), 'SW2': (93.0, 138.6, 180),
    'R12': (101.0, 136.0, 0), 'D4': (104.0, 136.0, 180),
    # rail monitors: MON12 divider + filter (west column), MON_N12 (east column), between U1 and the drivers
    'R97': (91.0, 123.0, 0), 'R98': (91.0, 124.6, 180), 'C110': (91.0, 126.2, 180),
    'R100': (95.0, 123.0, 0), 'R99': (95.0, 124.6, 180), 'C111': (95.0, 126.2, 180),
    'R96': (142.5, 106.0, 90),       # RAW_N -> LDOIN_N series R below U12 (mirror of R95 at U11)
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
    """A via.  A copied Rev E via of the same net at the same spot is replaced (no stacked drills; the
    hand via's 0.45 mm land is the smaller one)."""
    if isinstance(x, str) or (isinstance(x, tuple) and y is None):
        x, y = P(x) if isinstance(x, str) else x
    routing['vias'][:] = [v for v in routing['vias'] if not (v['net'] == net and str(v.get('src', '')).startswith('copy:')
                                                          and math.dist(v['at'], (x, y)) < 0.01)]
    routing['vias'].append({'net': net, 'at': [r3(x), r3(y)], 'diameter': d, 'drill': 0.3, 'src': _src()})


def DROP(net, x0, y0, x1, y1):
    """Remove copied Rev E copper of one net inside a box (a Rev E escape that the Rev F route replaces)."""
    inside = lambda p: x0 <= p[0] <= x1 and y0 <= p[1] <= y1
    routing['tracks'][:] = [t for t in routing['tracks'] if not (t['net'] == net and str(t.get('src', '')).startswith('copy:')
                                                                and all(inside(p) for p in t['points']))]
    routing['vias'][:] = [v for v in routing['vias'] if not (v['net'] == net and str(v.get('src', '')).startswith('copy:')
                                                          and inside(v['at']))]


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


def drop_superseded():
    """Copied Rev E copper that a hand route now duplicates or orphans, which KiCad reports as dangling
    although the pre-DRC's centre-line join accepts it:
      * a copied segment lying entirely on a hand-routed segment of the same net and layer;
      * a copied via that no track of its net reaches (a stitching via whose Rev E part moved away)."""
    def on_seg(p, a, b, tol=0.005):
        ax, ay = a; bx, by = b; px, py = p
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.dist(p, (ax + t * dx, ay + t * dy)) < tol
    hand = [t for t in routing['tracks'] if not str(t.get('src', '')).startswith('copy:')]
    keep, n = [], 0
    for t in routing['tracks']:
        if str(t.get('src', '')).startswith('copy:') and len(t['points']) == 2 and any(
                h['net'] == t['net'] and h['layer'] == t['layer'] and
                any(on_seg(t['points'][0], a, b) and on_seg(t['points'][1], a, b)
                    for a, b in zip(h['points'], h['points'][1:])) for h in hand):
            n += 1
            continue
        keep.append(t)
    routing['tracks'][:] = keep
    ends = {}
    for t in routing['tracks']:
        for a, b in zip(t['points'], t['points'][1:]):
            ends.setdefault(t['net'], []).append((a, b))
    pads = [p for p in predrc.static_items({'parts': list(parts.values()), 'board': design['board']})[0]]
    vias = []
    for v in routing['vias']:
        if str(v.get('src', '')).startswith('copy:') and not any(
                on_seg(v['at'], a, b, tol=v.get('diameter', 0.45) / 2) for a, b in ends.get(v['net'], [])) \
                and not any(p['net'] == v['net'] and p['geom'].contains(predrc.Point(*v['at'])) for p in pads):
            n += 1
            continue
        vias.append(v)
    routing['vias'][:] = vias
    return n


pruned = 0
while True:              # a pruned stub can orphan a via, and the reverse
    n = prune_copied() + drop_superseded()
    pruned += n
    if not n:
        break

# GND vias of the copied blocks that now sit on a hand-placed part's land are dropped (they belonged
# to Rev E neighbours); reported so a block's own stitching is never lost silently.
for v in routing['vias']:
    v['drill'] = 0.3
    v['diameter'] = max(v.get('diameter', 0.6), 0.45)

# ------------------------------------------------------------------ silk and reference text
design['board']['silk'] = [
    ['TEMPER LCR REV F', 111, 140.2, 1.0],
    ['HCUR', 67, 57.4, 0.8], ['HPOT', 89, 57.4, 0.8], ['LPOT', 111, 57.4, 0.8], ['LCUR', 133, 57.4, 0.8],
    ['DISCHARGED', 100, 46.6, 0.8], ['DUT ONLY', 100, 47.8, 0.8],
]
# IC reference text (the only references on silk): clear of lands and of each other
design['board']['ref_text'] = {'U3': [56.85, 138.3], 'U7': [118.3, 68.2], 'U13': [141.9, 134.6], 'U14': [64.0, 95.2],
                               'U16': [52.3, 132.3]}


def pads_of(*refs):
    for r in refs:
        print(r, parts[r]['pcb'], '  '.join(f"{p['num']}:{parts[r]['pins'].get(p['num'])}@{P(r + '.' + p['num'])[0]:.3f},{P(r + '.' + p['num'])[1]:.3f}"
                                              for p in fp(r)['pads'] if p['num']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--render', default='')
    ap.add_argument('--layers', default='B.Cu,In2.Cu,F.Cu', help='copper layers drawn by --render')
    ap.add_argument('--no-write', action='store_true')
    ap.add_argument('--pads', default='', help='print board-frame pad centres and nets of these parts')
    a = ap.parse_args()
    if a.pads:
        pads_of(*a.pads.split(','))
    design['parts'] = [parts[p['ref']] for p in design['parts']]
    print(f"{len(design['parts'])} parts, {len(routing['tracks'])} tracks, {len(routing['vias'])} vias; "
          f"copied {sum(n for n, _ in COPIED.values())} segments / {sum(v for _, v in COPIED.values())} vias, "
          f"pruned {pruned}")
    if a.check or a.render:
        res = predrc.check(design, routing)
        print(predrc.summary(res, limit=60))
        (ROOT / 'build' / 'rev-f-predrc.json').write_text(json.dumps(res, indent=1) + '\n')
        if a.render:
            names = list(VIEWS) if a.render == 'all' else a.render.split(',')
            for n in names:
                lay = tuple(a.layers.split(','))
                tag = '' if len(lay) == 3 else '-' + '+'.join(l.split('.')[0] for l in lay)
                out = ROOT / 'build' / f'rev-f-{n}{tag}.png'
                predrc.render(design, routing, res, VIEWS[n], out, title=f'Rev F {n}', layers=lay)
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
    'codec': (50, 74, 86, 102), 'codec_top': (58, 68, 80, 90), 'ldo': (120, 84, 150, 114), 'drivers': (78, 100, 124, 118),
    'switcher': (116, 112, 150, 145), 'digital': (50, 100, 92, 145), 'south': (50, 95, 150, 145), 'mid': (85, 112, 125, 145), 'board': (50, 45, 150, 145),
}

if __name__ == '__main__':
    main()
