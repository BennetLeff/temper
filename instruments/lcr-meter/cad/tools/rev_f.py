"""Rev F: the Rev E circuit re-laid on 100 x 100 mm, as explicit edits of the Rev E sources.

python3 cad/tools/rev_f.py [--check] [--render BLOCK,...|all] [--no-write]

Reads Rev E cad/design.json and cad/routing.json from git (48b012771), writes cad/design.json and
cad/routing.json.  Placement, copper, outline, holes and silk change; the netlist and BOM change only in
the indicator-LED block (front-panel D4, six debug LEDs, 2026-10-29).
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
import re
import math
import subprocess
import sys
from pathlib import Path

CAD = Path(__file__).resolve().parents[1]
ROOT = CAD.parent
REV_E = '48b012771'
sys.path.insert(0, str(CAD / 'tools'))
import predrc  # noqa: E402
from temper_boardkit import craft, model  # noqa: E402  (predrc put instruments/boardkit/src on the path)
from temper_boardkit.model import norm_rot, r3, rot, unrot  # noqa: E402,F401


def git_json(name):
    out = subprocess.run(['git', 'show', f'{REV_E}:./{name}'], cwd=CAD, check=True,
                         capture_output=True, text=True).stdout
    return json.loads(out)


design = git_json('design.json')
rev_e_routing = git_json('routing.json')
parts = {p['ref']: p for p in design['parts']}
E_POSE = {r: tuple(p['pcb']) for r, p in parts.items()}       # Rev E (x, y, rot)
LIB = predrc.LIB

# ------------------------------------------------------------------ indicator LEDs (Rev F, 2026-10-29)
# The netlist changes only here: D4 becomes a front-panel side-looking orange LED, and six debug LEDs
# are added.  Decisions and sizing: docs/rev-f-plan.md, "Indicator LEDs".
parts['D4'].update(value='ORANGE', footprint='LCR:LED_LiteOn_LTST-S270KFKT_SideView', mpn='LTST-S270KFKT',
                   manufacturer='Lite-On', lcsc='C160472', unit_usd=0.0382, stock=5577, library_type='extended',
                   source_query='side-looking orange LED, sources/rev-f/LTST-S270KFKT.txt; VF 2.0 typ / 2.4 max at 20 mA')
parts['R12'].update(value='390', mpn='0603WAF3900T5E', lcsc='C23151', unit_usd=0.0017, stock=2246779,
                    source_query='390ohm 0603: (3.3 - 1.9 V) / 390 = 3.6 mA nominal, 2.2-4.3 mA over corners')
parts['U1']['pins'].update({'34': 'FAULT', '35': 'HEARTBEAT'})      # GPIO22, GPIO23


def _part(ref, kind, value, pins, mpn, lcsc, usd, stock, query, fp=None, mfr='UNI-ROYAL(Uniroyal Elec)'):
    fp = fp or ('Resistor_SMD:R_0603_1608Metric' if kind == 'R' else 'LED_SMD:LED_0603_1608Metric')
    return {'ref': ref, 'value': value, 'kind': kind, 'footprint': fp, 'pins': pins, 'pcb': [0, 0, 0],
            'sheet': 'digital', 'mpn': mpn, 'manufacturer': mfr, 'lcsc': lcsc, 'unit_usd': usd, 'stock': stock,
            'library_type': 'basic', 'assembly': 'SMT', 'source_query': query}


_RED = dict(kind='LED', value='RED', mpn='KT-0603R', lcsc='C2286', usd=0.0073, stock=7351610, mfr='Hubei KENTO Elec')
# unit price: JLC 1-piece tier, manufacturing/prices/jlc-parts-2026-10-29.json (10k as already on the BOM)
# Values already on the BOM (5.1k R1/R2, 3k, 24k 1% R110), so the LEDs add no resistor line.  About 0.5 mA
# each (2026-10-29, halved from 1 mA): the +-12 V pair costs 5.4x its current at the 5 V input
# (through the LDOs and the TPS65131 at 0.64), and a C2286 is plainly visible at 0.5 mA with the lid off.
_R = {'3k': ('0603WAF3001T5E', 'C4211', 0.0024, 7044852), '5.1k': ('0603WAF5101T5E', 'C23186', 0.0015, 21527625),
      '24k 1%': ('0603WAF2402T5E', 'C23352', 0.0024, 677865)}
NEW_PARTS = []
# (LED, resistor, rail/GPIO net, LED net, resistor value, reason); the -12 V LED is reversed (anode on GND)
for d, r, rail, led, rv, why in (
        ('D15', 'R113', '5V', 'LED_5V', '5.1k', '(5.0 - 1.8 V) / 5.1k = 0.63 mA'),
        ('D16', 'R114', '3V3', 'LED_3V3', '3k', '(3.3 - 1.8 V) / 3k = 0.5 mA'),
        ('D17', 'R115', '12V', 'LED_P12', '24k 1%', '(11.9 - 1.8 V) / 24k = 0.42 mA, 4 mW'),
        ('D18', 'R116', '-12V', 'LED_N12', '24k 1%', '(11.9 - 1.8 V) / 24k = 0.42 mA, 4 mW; LED anode on GND'),
        ('D19', 'R117', 'HEARTBEAT', 'LED_HB', '3k', 'GPIO23 high: (3.3 - 1.8 V) / 3k = 0.5 mA'),
        ('D20', 'R118', 'FAULT', 'LED_FLT', '3k', 'GPIO22 high: (3.3 - 1.8 V) / 3k = 0.5 mA')):
    mpn, lcsc, usd, stock = _R[rv]
    NEW_PARTS.append(_part(r, 'R', rv, {'1': led, '2': rail},          # pad 2: rail / GPIO side
                           mpn, lcsc, usd, stock, f'{rv}ohm 0603 debug LED resistor: {why}'))
    k_net, a_net = (led, 'GND') if rail == '-12V' else ('GND', led)
    NEW_PARTS.append(_part(d, pins={'1': k_net, '2': a_net}, fp=None,
                           query=f'debug LED ({rail}), KiCad pad 1 = K', **_RED))
for p in NEW_PARTS:
    parts[p['ref']] = p
design['parts'] += NEW_PARTS


# Pad addressing and the hand-routing helpers (P, B, T, T45, V, DROP, WIDEN, KO) are temper_boardkit.model.Layout;
# rev_f_routes.py calls them by these names, and their 'src' quotes its line.
L = model.Layout(LIB, parts, src_file='rev_f_routes.py', src_default='rev_f.py')
fp, pad_local, pad_at = L.fp, L.pad_local, L.pad_at


# ------------------------------------------------------------------ board
OUTLINE = [50, 45, 150, 145]
design['board'] = {
    'origin': [50, 45], 'size': [100, 100], 'outline': OUTLINE,
    'holes': [[54, 54], [146, 54], [54, 141], [146, 141]],
    'ref_text': {},
    'silk': [],          # filled at the end of this file once placement is known
    # global fiducials (KiCad Fiducial_1mm_Mask2mm, board-only), three corners, asymmetric; each has
    # no copper within 2.0 mm of its centre (F.Cu rule area in rev_f_routes.py section 12)
    'fiducials': [[53.0, 59.0], [147.0, 48.0], [147.0, 136.0]],
    'testpoints': [],    # [name, net, x, y, pad diameter]: rev_f_routes.py section 12
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


L.groups = GROUPS
B = L.B

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
    'C104': (113.3, 73.95, 180),   # under U7.1/U7.2 (loop <= Rev E's 1.85 mm2)
    'R43': (109.6, 74.575, 180), 'R45': (109.6, 77.9, 180),
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
    # and the 3V3/GND header south-east of U1, at the ends of the In2 run along the south edge
    'J4': (69.0, 108.0, -90), 'J6': (86.5, 139.0, -90), 'J5': (86.0, 131.0, 180),
    'SW1': (85.2, 143.1, 0), 'SW2': (93.0, 138.6, 180),
    # front-panel status light: side-looking D4 at the front edge west of HCUR, in front of H1, lens on y 45
    'D4': (55.0, 45.95, 0), 'R12': (57.7, 47.6, 90),
    # debug LEDs, lid-off: HB / FLT west of U1 (LED north, resistor south), rail LEDs at the rail
    # monitors (resistor north on the rail, LED south, GND via below); labels on silk
    'D19': (58.8, 105.9, 270), 'R117': (58.8, 108.9, 270), 'D20': (61.2, 105.9, 270), 'R118': (61.2, 108.9, 270),
    'R113': (102.0, 127.0, 90), 'D15': (102.0, 130.0, 90), 'R114': (104.6, 127.0, 90), 'D16': (104.6, 130.0, 90),
    'R115': (107.2, 127.0, 90), 'D17': (107.2, 130.0, 90), 'R116': (109.8, 127.0, 90), 'D18': (109.8, 130.0, 270),
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


P = L.P


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
L.routing = routing
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


T, T45, V, DROP, WIDEN, KO = L.T, L.T45, L.V, L.DROP, L.WIDEN, L.KO

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

# ------------------------------------------------------------------ craft passes (temper_boardkit.craft, 2026-10-29)
# T-junction splits, straight land entries, 45-degree chamfers on 90-degree bends, 0.6 mm via pads where
# they clear.  Deterministic edits of the copper above; predrc enforces the same rules (design.board.craft).
design['board']['craft'] = True
design['board']['teardrops'] = True        # KiCad teardrops on every via and pad (cad/fill_zones.py)
CRAFT = craft.run(routing, *predrc.craft_inputs({'parts': list(parts.values()), 'board': design['board']}),
                  rules=predrc.RULES)

# ------------------------------------------------------------------ GND pours and stitching (cad/tools/pour.py)
import pour  # noqa: E402
POUR = pour.add({'parts': list(parts.values()), 'board': design['board']}, routing)

# ------------------------------------------------------------------ silk and reference text
design['board']['silk'] = [
    ['TEMPER LCR REV F', 111, 140.2, 1.0],
    ['HCUR', 67, 57.4, 1.0], ['HPOT', 89, 57.4, 1.0], ['LPOT', 111, 57.4, 1.0], ['LCUR', 133, 57.4, 1.0],
    ['DISCHARGED', 100, 46.35, 1.0], ['DUT ONLY', 100, 47.95, 1.0],
    # debug LED labels (2026-10-29): rail LEDs under their column (staggered: 1.0 mm text is wider than
    # the 2.6 mm column pitch), HB / FLT above theirs
    ['5V', 102.0, 133.3, 1.0], ['3V3', 104.6, 134.8, 1.0], ['+12', 107.2, 133.3, 1.0], ['-12', 109.8, 134.8, 1.0],
    ['HB', 58.8, 102.6, 1.0], ['FLT', 61.2, 101.2, 1.0],   # FLT raised: 1.0 mm labels would run together
] + [[name, lx, ly, 1.0] for name, _, _, _, _, lx, ly in TESTPOINTS]   # test-point labels
# IC reference text (the only references on silk): clear of lands and of each other
design['board']['ref_size'] = [1.0, 0.15]     # IC references on silk: 1.0 mm high, 0.15 mm stroke (2026-10-29)
design['board']['ref_text'] = {'U3': [56.85, 138.3], 'U7': [118.3, 68.2], 'U13': [141.9, 134.6], 'U14': [64.0, 95.2],
                               'U16': [51.9, 132.4], 'U6': [82.0, 68.3], 'U15': [56.6, 79.7]}


# ------------------------------------------------------------------ silk reference designators (craft.place_refs)
# Every other reference goes on silk where craft.place_refs finds a spot beside its own part (1.0 / 0.15 mm text,
# clear of lands, bodies, silk and other text, nearer its own part than any other); the rest stay on F.Fab and
# are on the assembly drawing (manufacturing/assembly-top.pdf).  Fonts and footprint silk: silk_library.json.
REF_ORDER = ('U', 'K', 'J', 'Q', 'D', 'L', 'Y', 'SW', 'FB', 'F', 'R', 'C')


def ref_key(ref):
    m = re.match(r'([A-Z]+)(\d+)', ref)
    pre, n = (m.group(1), int(m.group(2))) if m else (ref, 0)
    return (REF_ORDER.index(pre) if pre in REF_ORDER else len(REF_ORDER), pre, n)


def silk_obstacles(slib):
    """Lands, holes, fiducial mask openings, footprint silk, board labels and the hand-placed references."""
    board = design['board']
    h, w = board['ref_size']
    pads, drills, _ = predrc.static_items({'parts': list(parts.values()), 'board': board})
    obs = [{'poly': [list(c) for c in p['geom'].exterior.coords], 'clear': 0.15} for p in pads]
    obs += [{'poly': [list(c) for c in d['geom'].exterior.coords], 'clear': 0.3} for d in drills if d['net'] is None]
    obs += [{'poly': [list(c) for c in predrc.Point(x, y).buffer(3.0, 16).exterior.coords], 'clear': 0.0}
            for x, y in board['holes']]                                   # M3 screw heads
    obs += [{'poly': [list(c) for c in predrc.Point(x, y).buffer(1.0, 16).exterior.coords], 'clear': 0.15}
            for x, y in board['fiducials']]                               # 2 mm mask openings
    placed = [(p, p['pcb']) for p in parts.values()] + \
        [({'footprint': f'x:TestPoint_Pad_D{d:.1f}mm'}, [x, y, 0]) for _, _, x, y, d in board['testpoints']]
    for p, (x, y, t) in placed:
        for pts in slib['footprints'].get(predrc.fp_name(p), []):
            if len(pts) >= 3:
                g = predrc.place_geom(predrc.Polygon(pts).buffer(0), (x, y), t)
                for q in ([g] if g.geom_type == 'Polygon' else list(g.geoms)):
                    obs.append({'poly': [list(c) for c in q.exterior.coords], 'clear': 0.15})
    texts = [(s_, x, y, size, 0.15) for s_, x, y, size in board['silk']] + \
        [(r, v[0], v[1], h, w, *(v[2:] or [parts[r]['pcb'][2] % 180])) for r, v in board['ref_text'].items()]
    for s_, x, y, size, stroke, *ang in texts:     # a hand reference without an angle turns with its part (kept upright)
        assert not ang or ang[0] in (0, 90), (s_, ang)
        b = craft.ref_box([x, y, int(ang[0]) if ang else 0], slib['text'][f'{s_}|{size}|{stroke}'])
        obs.append({'poly': [list(c) for c in b.exterior.coords], 'clear': 0.2})
    return obs


def silk_refs():
    slib = json.loads((CAD / 'tools' / 'silk_library.json').read_text())
    board = design['board']
    h, w = board['ref_size']
    need = sorted({f'{r}|{h}|{w}' for r in parts} | {f'{s_}|{size}|0.15' for s_, _, _, size in board['silk']})
    if set(need) - set(slib['text']):
        (ROOT / 'build').mkdir(exist_ok=True)
        (ROOT / 'build' / 'silk-strings.json').write_text(json.dumps(need, indent=0) + '\n')
        sys.exit(f'silk_library.json lacks {sorted(set(need) - set(slib["text"]))}: run '
                 '<kicad-python> cad/tools/silk_library.py (it reads build/silk-strings.json), then rev_f.py again')
    _, _, courts = predrc.static_items({'parts': list(parts.values()), 'board': board})
    court = {}
    for c in courts:
        court.setdefault(c['ref'], []).append(c['geom'])
    todo = []
    for ref in sorted(parts, key=ref_key):
        if ref in board['ref_text'] or ref not in court:
            continue
        g = max(court[ref], key=lambda q: q.area)
        todo.append({'ref': ref, 'courtyard': [list(c) for c in g.exterior.coords]})
    ink = {p['ref']: slib['text'][f"{p['ref']}|{h}|{w}"] for p in todo}
    obstacles = silk_obstacles(slib)
    got, missing = craft.place_refs(todo, ink, obstacles, board)
    return got, missing, todo, ink, obstacles


# relay-coil test pads keep >= 10 mm from every analog-net item (rev_f_routes.py section 12)
COIL_TP_MIN = 10.0
_an = [x['geom'] for x in sum(predrc.dyn_items(routing), []) + predrc.static_items(
    {'parts': list(parts.values()), 'board': design['board']})[0] if x['net'] in pour.ANALOG]
COIL_TP = {t[0]: round(min(g.distance(predrc.Point(t[2], t[3])) for g in _an), 2)
           for t in design['board']['testpoints'] if t[1].startswith('RLY_')}
assert all(d >= COIL_TP_MIN for d in COIL_TP.values()), COIL_TP

SILK_REFS, SILK_MISSING, _todo, _ink, _obs = silk_refs()
SILK_VIOL = craft.ref_checks(SILK_REFS, _ink, _todo, _obs)
assert not SILK_VIOL, SILK_VIOL
design['board']['ref_text'].update(SILK_REFS)
design['board']['refs_on_silk_only_if_placed'] = True     # build_cad: a reference not in ref_text goes to F.Fab


# ------------------------------------------------------------------ fabrication drawing (Dwgs.User; build_cad.py draws it)
def fab_notes():
    """Notes and the drill summary for the fab drawing, from the design itself (counts follow the routing)."""
    from collections import Counter
    x0, y0, x1, y1 = design['board']['outline']
    pads, drills, _ = predrc.static_items({'parts': list(parts.values()), 'board': design['board']})
    vias = Counter((v.get('drill', 0.3), v.get('diameter', 0.6)) for v in routing['vias'])
    size = lambda g: tuple(sorted(round(b - a, 2) for a, b in zip(g.bounds[:2], g.bounds[2:])))
    pth = Counter(size(d['geom']) for d in drills if d['net'] is not None)
    npth = Counter(size(d['geom']) for d in drills if d['net'] is None)
    fmt = lambda wh: f'{wh[0]:.2f} mm' if abs(wh[0] - wh[1]) < 0.01 else f'{wh[0]:.2f} x {wh[1]:.2f} mm slot'
    drill = [f'  vias      {n:4d} x {d:.2f} mm drill, {pad:.2f} mm pad' for (d, pad), n in sorted(vias.items())]
    drill += [f'  PTH       {n:4d} x {fmt(wh)}' for wh, n in sorted(pth.items())]
    drill += [f'  NPTH      {n:4d} x {fmt(wh)}' for wh, n in sorted(npth.items())]
    total = sum(vias.values()) + sum(pth.values()) + sum(npth.values())
    lines = [
        'TEMPER LCR REV F - FABRICATION NOTES',
        f'1. Board {x1 - x0:.2f} x {y1 - y0:.2f} mm, 4 layers, 1.6 mm finished. FR-4, TG 135-140.',
        '2. Stackup JLC04161H-7628: F.Cu 1 oz | 7628 prepreg | In1.Cu 0.5 oz GND plane | core |',
        '   In2.Cu 0.5 oz signals + GND pour | 7628 prepreg | B.Cu 1 oz signals + GND pour.',
        '3. Finish ENIG. Solder mask both sides; silkscreen top only (bottom intentionally empty).',
        '4. Vias: every drill 0.30 mm. Covering "Plugged" (JLC default); do NOT order POFV.',
        '   Exposed-pad thermal vias in U1, U11, U12, U13, U14: plugged from the bottom only,',
        '   top lands left clean and open under paste. No other via touches an SMT land.',
        f'5. Drill summary ({total} holes; drill files temper-lcr-PTH.drl / -NPTH.drl govern):',
        *drill,
        '6. Panel: edge rails added by JLCPCB, V-cut on the LEFT and RIGHT edges only.',
        '   No rail on the front (BNC, y = top in this view) edge or the back edge.',
        '7. Overhang: BNC J3, J7, J8, J9 reach 18.5 mm past the front edge (hand-fitted after',
        '   reflow); J1 USB-C shell 0.2 mm past the left edge, >= 0.9 mm above the board.',
        '8. Minimum track / space 0.15 / 0.15 mm; minimum via ring 0.075 mm; copper to edge >= 0.4 mm.',
        '9. Origin (0, 0) at the lower-left board corner for Gerber, drill and placement files.',
    ]
    return [[t, x1 + 6.0, y0 + 2.0 + 2.1 * i, 1.2] for i, t in enumerate(lines)]


design['board']['fab_notes'] = fab_notes()
design['board']['fab_dims'] = [[design['board']['outline'][0], design['board']['outline'][3],
                                design['board']['outline'][2], design['board']['outline'][3], 6.0],      # width, below
                               [design['board']['outline'][0], design['board']['outline'][3],
                                design['board']['outline'][0], design['board']['outline'][1], -6.0]]     # height, left


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
    print('craft:', CRAFT)
    print('pour:', POUR)
    print('coil test pads, mm to analog copper:', COIL_TP)
    print(f'silk refs: {len(SILK_REFS)} placed by search, {len(design["board"]["ref_text"]) - len(SILK_REFS)} by hand, '
          f'{len(SILK_MISSING)} on F.Fab only: {" ".join(SILK_MISSING)}')
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
                 'zones': routing['zones'], 'keepouts': routing['keepouts'],
                 'craft_exceptions': routing['craft_exceptions']}
        (CAD / 'design.json').write_text(json.dumps(design, indent=2) + '\n')
        (CAD / 'routing.json').write_text(json.dumps(clean, indent=2) + '\n')


VIEWS = {
    'bnc': (50, 45, 150, 62), 'afe_hi': (78, 55, 96, 105), 'relays': (90, 55, 112, 106),
    'tia': (104, 55, 126, 85), 'c104': (108, 68, 118, 80), 'k4': (122, 55, 150, 86), 'source': (55, 55, 82, 80),
    'codec': (50, 74, 86, 102), 'codec_top': (58, 68, 80, 90), 'ldo': (120, 84, 150, 114), 'drivers': (78, 100, 124, 118),
    'switcher': (116, 112, 150, 145), 'digital': (50, 100, 92, 145), 'south': (50, 95, 150, 145), 'mid': (85, 112, 125, 145), 'board': (50, 45, 150, 145),
}

if __name__ == '__main__':
    main()
