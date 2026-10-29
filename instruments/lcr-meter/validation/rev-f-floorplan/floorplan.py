"""Rev F phase 1: 100 x 100 mm floorplan of the Rev E circuit, checked before any placement or routing.

python3 validation/rev-f-floorplan/floorplan.py            (about 1 s; numpy + matplotlib)

Inputs: rev-e-inventory.json (Rev E courtyards, pads, track lengths per net and layer; written once by
cad/tools/rev_f_inventory.py with KiCad's Python, so this script needs no KiCad) and the Rev E
extraction ../layout-parasitics/extracted_reve_bnc.json (board 80d44838, the as-built BNC/K4 layout).
Outputs: floorplan.json (every number quoted in docs/rev-f-plan.md) and floorplan.png.

What it does, in order:
  1. Assigns every Rev E footprint to one Rev F block and checks the assignment is complete.
  2. Places the anchor parts (edge items, holes, ICs, relays, magnetics) at explicit Rev F
     coordinates and rotations; checks they sit inside the 100 x 100 outline and their block, and
     that no two anchor courtyards overlap.
  3. Block utilisation: sum of member courtyards / block area, against the densest block Rev E
     already carries (same membership, courtyard bounding box) -- a demonstrated hand-routable
     density with the same rules, not a theoretical limit.
  4. Planned route skeletons (waypoints + layer) for the analog nets that set stability, against
     the Rev E lengths per layer from the native board.
  5. A FORECAST of the extracted node capacitances: Rev E extracted value, minus its trace length
     times a per-layer capacitance per mm, plus the Rev F planned length times the same figure.
     The per-mm figures are closed-form microstrip estimates (Hammerstad), stated below. This is an
     estimate to decide whether to proceed; the phase-3 FD extraction replaces it.
  6. Switcher-to-analog distances (the regulator_check.py metric: part centres).

Coordinates: Rev F board x 50-150, y 45-145 mm (top edge y 45 carries the BNCs, as on Rev E).
Rotation convention is KiCad's: local (x, y) -> board (x cos t + y sin t, -x sin t + y cos t).
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
INV = json.loads((HERE / 'rev-e-inventory.json').read_text())
PARTS = INV['parts']
EXTRACTED = json.loads((HERE.parent / 'layout-parasitics/extracted_reve_bnc.json').read_text())

OUTLINE = (50.0, 45.0, 150.0, 145.0)       # Rev F: x0, y0, x1, y1
REV_E_OUTLINE = (50.0, 45.0, 190.0, 150.0)

# ------------------------------------------------------------------ 1. blocks
# Rectangles (x0, y0, x1, y1); a block may be an L made of two rectangles.
BLOCKS = {
    'bnc':      {'rects': [(57.5, 45.0, 142.5, 57.0)],
                 'refs': 'J3 J7 J8 J9'},
    'holes':    {'rects': [(50.0, 45.0, 57.5, 57.5), (142.5, 45.0, 150.0, 57.5),
                           (50.0, 137.5, 57.5, 145.0), (142.5, 137.5, 150.0, 145.0)],
                 'refs': 'H1 H2 H3 H4'},
    'source':   {'rects': [(57.5, 57.0, 80.0, 72.0)],
                 'refs': 'U5 R30 R31 R32 R33 C34 C35 C114 C115 C37 C38 C39 C40'},
    'codec':    {'rects': [(50.0, 72.0, 80.0, 106.0), (50.0, 57.5, 57.5, 72.0)],
                 'refs': 'U14 U15 C60 C61 C62 C63 C64 C65 C66 C67 C68 R62 R63 R64 R65 R68 R69 R70 R71 '
                         'R72 R73 D11 D12 D13 D14 C69 C70 C72 C73 C74 C75 C76 C77 FB1 C103'},
    'afe_hi':   {'rects': [(80.0, 57.0, 93.4, 103.0)],
                 'refs': 'U6 C42 C43 C44 C45 C50 C51 R104 R105 R40 R41 R42 R60'},
    'relays':   {'rects': [(93.4, 57.0, 106.6, 103.0)],
                 'refs': 'K1 K2 K3'},
    'tia':      {'rects': [(106.6, 57.0, 124.0, 84.0), (106.6, 84.0, 122.0, 103.0)],
                 'refs': 'U7 C46 C47 C48 C49 C52 C53 R43 R44 R45 C104 R94 C78 R106 R61 R66 R67'},
    'k4':       {'rects': [(124.0, 57.0, 142.5, 84.0), (142.5, 57.5, 150.0, 84.0)],
                 'refs': 'K4 R107 Q6 R108 R109 D9'},
    'ldo':      {'rects': [(122.0, 84.0, 150.0, 113.0)],
                 'refs': 'U11 U12 C93 C94 C95 C96 C97 C98 C99 C100 C101 C102 R85 R86 R87 R88 R89 '
                         'R112 R95 R96 R97 R100'},
    'drivers':  {'rects': [(80.0, 103.0, 118.0, 116.0), (118.0, 103.0, 122.0, 113.0)],
                 'refs': 'Q2 Q3 Q4 Q5 R74 R75 R76 R77 R78 R79 R102 R103 D5 D6 D7 D8 R101 C112'},
    'switcher': {'rects': [(118.0, 113.0, 150.0, 137.5), (118.0, 137.5, 142.5, 145.0)],
                 'refs': 'U13 L1 L2 D2 D3 C80 C81 C82 C83 C84 C85 C86 C87 C88 C89 C90 C91 C92 '
                         'R80 R81 R82 R83 R84 R111'},
    'digital':  {'rects': [(50.0, 106.0, 80.0, 137.5), (57.5, 137.5, 80.0, 145.0), (80.0, 116.0, 118.0, 145.0)],
                 'refs': None},   # everything else: the digital sheet plus U3, U16 and their parts
}
for b in BLOCKS.values():
    if b['refs'] is not None:
        b['refs'] = b['refs'].split()
claimed = {r for b in BLOCKS.values() if b['refs'] for r in b['refs']}
BLOCKS['digital']['refs'] = sorted(r for r in PARTS if r not in claimed)

# ------------------------------------------------------------------ 2. anchors (x, y, rotation deg)
# Relays at 270: pins 1-5 (pole 1: VRLY, NC, COM1 = SOURCE_BUF, NO1 = RGx, SET) face -x toward U6;
# pins 6-10 (RESET, NO2 = RFx, COM2 = TIA_OUT, NC, VRLY) face +x toward the TIA. K1 (100 ohm, the
# range whose RF loop inductance matters most) is nearest U6/U7. K4 at 90 puts COM2 (DUT_HI) and
# NO2 (REF_A) on its west side, R107 to DUT_LO next to the LCUR jack.
ANCHORS = {
    'J3': (67.0, 51.0, 0), 'J7': (89.0, 51.0, 0), 'J8': (111.0, 51.0, 0), 'J9': (133.0, 51.0, 0),
    'H1': (54.0, 54.0, 0), 'H2': (146.0, 54.0, 0), 'H3': (54.0, 141.0, 0), 'H4': (146.0, 141.0, 0),
    'K1': (100.0, 65.0, 270), 'K2': (100.0, 80.0, 270), 'K3': (100.0, 95.0, 270),
    'K4': (138.0, 66.0, 90),
    'U6': (88.0, 66.0, 90), 'U7': (112.0, 70.0, 90), 'U5': (75.0, 64.0, 0),
    'J1': (54.0, 122.0, -90), 'U16': (62.0, 114.0, 0), 'U3': (61.0, 140.0, 0),
}


# Rigid groups: Rev E sub-layouts moved as one body (translation, optionally a quarter turn about
# the group's pivot part), so their hand-routed intra-group copper carries over coordinate for
# coordinate (explicit hand routes, transformed; no autorouter). Members are checked like anchors.
RIGID = {
    'rp2040_core': {'pivot': 'U1', 'to': (74.0, 124.0), 'turn': 0,
                    'refs': 'U1 U2 Y1 C1 C2 C3 C4 C5 C6 C7 C8 C9 C10 C11 C12 C13 C14 R3 R4 R7 R8 R9 R10 R13'},
    'codec_core': {'pivot': 'U14', 'to': (64.0, 88.5), 'turn': 0,
                   'refs': 'U14 U15 C60 C61 C62 C63 C64 C65 C66 C67 C68 R72 R73'},
    'ldo_pair': {'pivot': 'U11', 'to': (130.0, 100.0), 'turn': 0,
                 'refs': 'U11 U12 C93 C94 C95 C96 C97 C98 C99 C100 C101 C102 R85 R86 R87 R88 R89 R112 R95'},
    # pose from a 0.5 mm grid search over the four quarter turns (max of the min distance from L1,
    # L2, D2, D3, U13 to U5/U6/U7/U14, every courtyard inside the block and clear of the rest):
    # a quarter turn (L2/D3 north-east, L1/D2 south-west) at U13 = (137.5, 135)
    'switcher': {'pivot': 'U13', 'to': (137.5, 135.0), 'turn': 90,
                 'refs': 'U13 L1 L2 D2 D3 C81 C82 C83 C84 C85 C86 C87 C88 C89 C90 C91 C92 R80 R81 R82 R83 R84 R111'},
    'drivers': {'pivot': 'Q3', 'to': (86.0, 111.6), 'turn': 0,
                'refs': 'Q2 Q3 Q4 Q5 R74 R75 R76 R77 R78 R79 R102 R103 D5 D6 D7 D8'},
}
GROUP_OF = {}


def _place_rigid():
    for name, g in RIGID.items():
        g['refs'] = g['refs'].split()
        px, py = PARTS[g['pivot']]['at']
        for r in g['refs']:
            e = PARTS[r]
            dx, dy = rot(e['at'][0] - px, e['at'][1] - py, g['turn'])
            t = (e['rot'] + g['turn'] + 180) % 360 - 180
            ANCHORS[r] = (round(g['to'][0] + dx, 3), round(g['to'][1] + dy, 3), t)
            GROUP_OF[r] = name


def rot(dx, dy, t):
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return dx * c + dy * s, -dx * s + dy * c


def unrot(dx, dy, t):
    return rot(dx, dy, -t)


_place_rigid()


def placed_pads(ref):
    """Rev F pad positions of an anchored part (Rev E pad offsets taken back to the footprint frame)."""
    p = PARTS[ref]
    x, y, t = ANCHORS[ref]
    out = {}
    for num, (px, py, net) in p['pads'].items():
        lx, ly = unrot(px - p['at'][0], py - p['at'][1], p['rot'])
        bx, by = rot(lx, ly, t)
        out[num] = (round(x + bx, 3), round(y + by, 3), net)
    return out


def courtyard(ref, at=None):
    p = PARTS[ref]
    x0, y0, x1, y1 = p['courtyard_box_rel']
    if at is None:
        return (p['at'][0] + x0, p['at'][1] + y0, p['at'][0] + x1, p['at'][1] + y1)
    x, y, t = at
    pts = [rot(*unrot(cx, cy, p['rot']), t) for cx in (x0, x1) for cy in (y0, y1)]
    xs, ys = [x + a for a, _ in pts], [y + b for _, b in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def overlap(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def inside(a, rects, tol=0.06):
    """a is covered by the union of rects (checked on a 0.25 mm sample grid)."""
    n = 12
    for i in range(n + 1):
        for j in range(n + 1):
            x = a[0] + (a[2] - a[0]) * i / n
            y = a[1] + (a[3] - a[1]) * j / n
            if not any(r[0] - tol <= x <= r[2] + tol and r[1] - tol <= y <= r[3] + tol for r in rects):
                return False
    return True


def area(rects):
    return sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects)


# ------------------------------------------------------------------ 4. planned route skeletons
# Waypoints are pad references 'REF.pin' (anchored parts) or coordinates; each leg names its layer.
# Lengths are Manhattan between waypoints (hand routes use 45-degree corners, so this is the upper
# side of the eventual length). Stubs to pads of small parts not anchored here are explicit numbers.
def P(ref_pin):
    ref, pin = ref_pin.split('.')
    x, y, _ = placed_pads(ref)[pin]
    return (x, y)


ROUTES = {
    # SOURCE_BUF: R104.2 -> via -> In2 bus at x 93.6 (just west of the K1-K3 COM1 pads) -> each COM1
    # pad by a 1.6 mm F.Cu stub. R104 sits between U6.1 and the bus at y 70.5.
    'SOURCE_BUF': [('F.Cu', [(92.7, 70.5), (93.6, 70.5)]),
                   ('In2.Cu', [(93.6, 65.0), (93.6, 95.0)]),
                   ('F.Cu', 3 * 1.6)],
    'SRC_DRV': [('F.Cu', [P('U6.1'), (87.03, 70.5), (91.1, 70.5)])],
    # TIA_OUT: U7.1 -> C104 / R67 stubs -> via -> In2 bus at x 106.4 east of the COM2 pads.
    'TIA_OUT': [('F.Cu', [P('U7.1'), (110.0, 73.0)]),
                ('In2.Cu', [(110.0, 73.0), (106.4, 73.0), (106.4, 65.0)]),
                ('In2.Cu', [(106.4, 73.0), (106.4, 95.0)]),
                ('F.Cu', 3 * 1.6 + 2.0 + 3.0)],          # COM2 stubs, C104 pad, R67 tap at U7
    # RF nets: NO2 pad -> R4x at x 108.2 (TIA_SUM pads at the U7 end, as on Rev E)
    'RF100': [('F.Cu', [P('K1.7'), (108.2, 67.54), (108.2, 70.5)])],
    'RF5K': [('F.Cu', [P('K2.7'), (107.3, 82.54)]), ('In2.Cu', [(107.3, 82.54), (107.3, 74.5)])],
    'RF100K': [('F.Cu', [P('K3.7'), (107.3, 97.54)]), ('In2.Cu', [(107.3, 97.54), (107.3, 76.2)])],
    'TIA_SUM': [('F.Cu', [(109.0, 70.5), (109.0, 76.2)]), ('F.Cu', [(109.0, 72.6), P('U7.2')]),
                ('F.Cu', 2.5 + 2.0)],                     # C104 and R94 pads
    # DUT_LO: J9 centre -> R107/R106 stubs -> C78/R94 at the TIA (F.Cu then B.Cu, clear of U7's void)
    'DUT_LO': [('F.Cu', [P('J9.5'), (130.0, 57.8)]), ('B.Cu', [(130.0, 57.8), (116.0, 76.0)]),
               ('F.Cu', [(116.0, 76.0), (114.0, 76.0)]), ('F.Cu', 3.0 + 3.0)],
    # DUT_HI: J3 centre -> y 58.5 -> B.Cu bus x 90.2 past R40-R42 (so SRC_DRV/R104 cross it on F.Cu)
    # -> B.Cu south of K3 at y 101.5
    # (clear of the codec divider runs under K2 and of the TIA plane voids) -> north along x 123 ->
    # K4 COM2 on its west side.
    'DUT_HI': [('F.Cu', [P('J3.5'), (67.0, 58.5), (90.2, 58.5)]),
               ('B.Cu', [(90.2, 58.5), (90.2, 101.5)]),        # under R40-R42 (via + F.Cu stub each)
               ('B.Cu', [(90.2, 101.5), (123.0, 101.5), (123.0, 66.0)]),
               ('F.Cu', [(123.0, 66.0), P('K4.8')]),
               ('F.Cu', 3 * 1.2 + 2.5)],                  # R40-R42 and R105 stubs
    'HPOT': [('F.Cu', [P('J7.5'), P('U6.5')]), ('F.Cu', 4.0)],                    # + R105
    'LPOT': [('F.Cu', [P('J8.5'), P('U7.5')]), ('F.Cu', 6.0)],                    # + R106
    'HIGH_BUF': [('F.Cu', 6.0)],                          # U6.6/7 -> R60 (codec C1P leg) at U6
    'LOW_BUF': [('F.Cu', 8.0)],                           # U7.6/7 -> R61, R66 at U7
    'REF_A': [('F.Cu', 2.4)],
    'RG100': [('F.Cu', 2.4)], 'RG5K': [('F.Cu', 2.4)], 'RG100K': [('F.Cu', 2.4)],
    # EXCITE leaves U5 southward, clear of the DUT_HI run at y 58.5
    'EXCITE': [('F.Cu', [P('U5.1'), (73.86, 71.2), (86.0, 71.2), (86.0, 68.11), P('U6.3')]),
               ('F.Cu', 5.0)],   # + R33/C115
    'DAC_P': [('F.Cu', [P('U14.20'), (70.75, 74.0), (72.0, 70.0)])],
    'DAC_M': [('F.Cu', [P('U14.19'), (71.25, 74.0), (78.0, 70.0)])],
    # codec divider nodes for the U7 legs cross under the relays on B.Cu at y 85-87 (R61/R66/R67 at U7)
    'C1M_DIV': [('B.Cu', [(110.0, 84.0), (80.0, 87.0)])],
    'C2P_DIV': [('B.Cu', [(110.0, 85.0), (80.0, 88.0)])],
    'C2M_DIV': [('B.Cu', [(110.0, 86.0), (80.0, 89.0)])],
}


def seg_len(t):
    pts = []
    for q in t['points']:
        if isinstance(q, str):
            x, y, _ = PARTS[q.split('.')[0]]['pads'][q.split('.')[1]]
            pts.append((x, y))
        else:
            pts.append(q)
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def route_length(segs):
    per = defaultdict(float)
    for layer, wp in segs:
        if isinstance(wp, (int, float)):
            per[layer] += wp
        else:
            per[layer] += sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(wp, wp[1:]))
    return {k: round(v, 1) for k, v in per.items()}


# ------------------------------------------------------------------ 5. capacitance per mm
# 0.2 mm track. F.Cu: microstrip over In1 (prepreg 0.2104 mm, er 4.4). In2: In1 is the only plane,
# 1.065 mm core (er 4.6) away; B.Cu: 1.29 mm (core + prepreg). Hammerstad-Jensen w/h < 1 form.
def microstrip_pf_per_mm(w, h, er):
    u = w / h
    eeff = (er + 1) / 2 + (er - 1) / 2 * ((1 + 12 / u) ** -0.5 + 0.04 * (1 - u) ** 2)
    z0 = 60 / math.sqrt(eeff) * math.log(8 / u + u / 4)
    return math.sqrt(eeff) / (299792458.0 * z0) * 1e12 / 1e3


C_MM = {'F.Cu': microstrip_pf_per_mm(0.2, 0.2104, 4.4),
        'In2.Cu': microstrip_pf_per_mm(0.2, 1.065, 4.6),
        'B.Cu': microstrip_pf_per_mm(0.2, 1.29, 4.5)}

# harness node -> nets whose copper it carries (per range k the selected RF/RG net joins tia/source)
RANGE_NETS = [('RF100', 'RG100'), ('RF5K', 'RG5K'), ('RF100K', 'RG100K')]
NODE_NETS = {'sum': ['TIA_SUM'], 'low': ['DUT_LO'], 'hi': ['DUT_HI'], 'lowbuf': ['LOW_BUF'],
             'highbuf': ['HIGH_BUF'], 'srcdrv': ['SRC_DRV'], 'hpot': ['HPOT'], 'lpot': ['LPOT'],
             'refa': ['REF_A']}


def node_nets(node, k):
    if node == 'tia':
        return ['TIA_OUT', RANGE_NETS[k][0]]
    if node == 'source':
        return ['SOURCE_BUF', RANGE_NETS[k][1]]
    return NODE_NETS[node]


def trace_pf(lengths_by_net, nets):
    return sum(C_MM.get(layer, C_MM['In2.Cu']) * mm for n in nets for layer, mm in lengths_by_net.get(n, {}).items())


def net_forecast(lengths_e, lengths_f):
    """Per net: Rev E extracted ground C (raw_net_ground_pf: board copper, part terms and the BNC jack
    estimate), its modelled trace share removed and the Rev F planned trace share added. The high
    corner keeps the Rev E high/nominal ratio of the same net."""
    raw = EXTRACTED['raw_net_ground_pf']
    out = {}
    for net in raw['nom']:
        e_nom, e_high = raw['nom'][net], raw['high'][net]
        te, tf = trace_pf(lengths_e, [net]), trace_pf(lengths_f, [net]) if net in lengths_f else None
        if tf is None:
            continue
        if te <= e_nom:
            fixed = e_nom - te
            f_nom = fixed + tf
        else:
            # the microstrip figure overstates this net (plane void under it, e.g. TIA_SUM): scale
            # the extracted value by length instead
            fixed = 0.0
            f_nom = e_nom * tf / te
        out[net] = {'rev_e_nom': e_nom, 'rev_e_high': e_high, 'rev_e_trace_model': round(te, 2),
                    'rev_e_fixed_remainder': round(fixed, 2), 'rev_f_trace_model': round(tf, 2),
                    'rev_f_nom': round(f_nom, 2), 'rev_f_high': round(f_nom * e_high / e_nom, 2)}
    return out


def main():
    report = {'outline_mm': OUTLINE, 'rev_e_outline_mm': REV_E_OUTLINE,
              'inventory_board_sha256': INV['board_sha256'], 'checks': [], 'c_per_mm_pf': C_MM}
    fail = []

    def check(name, ok, value):
        report['checks'].append({'check': name, 'pass': bool(ok), 'value': value})
        if not ok:
            fail.append(name)

    # 1. assignment
    seen = defaultdict(list)
    for b, d in BLOCKS.items():
        for r in d['refs']:
            seen[r].append(b)
    check('every Rev E footprint in exactly one block', set(seen) == set(PARTS) and all(len(v) == 1 for v in seen.values()),
          {'footprints': len(PARTS), 'assigned': len(seen), 'unknown': sorted(set(seen) - set(PARTS))})

    # 2. anchors
    cy = {r: courtyard(r, ANCHORS[r]) for r in ANCHORS}

    def overhang(c, o):
        return max(o[0] - c[0], c[2] - o[2], o[1] - c[1], c[3] - o[3], 0.0)
    # an edge connector may cross the edge by as much as it already does on Rev E (J1: 0.2 mm lip)
    out_of_board = [r for r, c in cy.items()
                    if overhang(c, OUTLINE) > max(0.06, overhang(courtyard(r), REV_E_OUTLINE) + 0.01)]
    check('anchor courtyards inside the 100 x 100 outline', not out_of_board, out_of_board)
    # pairs inside one rigid group keep their Rev E relative geometry (and any Rev E courtyard
    # overlap, which the Rev E DRC passed); every other pair must be clear
    clashes = [(a, b, round(overlap(cy[a], cy[b]), 3)) for i, a in enumerate(cy) for b in list(cy)[i + 1:]
               if overlap(cy[a], cy[b]) > 1e-6 and not (GROUP_OF.get(a) and GROUP_OF.get(a) == GROUP_OF.get(b))]
    check('no two placed courtyards overlap (outside inherited rigid-group pairs)', not clashes, clashes)
    block_of = {r: b for b, d in BLOCKS.items() for r in d['refs']}
    clip = {r: (max(c[0], OUTLINE[0]), max(c[1], OUTLINE[1]), min(c[2], OUTLINE[2]), min(c[3], OUTLINE[3]))
            for r, c in cy.items()}
    outside = [r for r in ANCHORS if not inside(clip[r], BLOCKS[block_of[r]]['rects'])]
    check('each anchor inside its block', not outside, outside)
    blocks_overlap = [(a, b) for i, a in enumerate(BLOCKS) for b in list(BLOCKS)[i + 1:]
                      if any(overlap(x, y) > 1e-6 for x in BLOCKS[a]['rects'] for y in BLOCKS[b]['rects'])]
    check('blocks do not overlap', not blocks_overlap, blocks_overlap)
    total_block = sum(area(d['rects']) for d in BLOCKS.values())
    check('blocks tile the board', abs(total_block - 1e4) < 1.0, round(total_block, 1))
    report['anchors'] = {r: {'at': list(ANCHORS[r]), 'courtyard': [round(v, 2) for v in cy[r]]} for r in ANCHORS}

    # 3. utilisation vs Rev E density of the same membership
    util = {}
    for b, d in BLOCKS.items():
        cour = sum(PARTS[r]['courtyard_mm2'] for r in d['refs'])
        boxes = [courtyard(r) for r in d['refs']]
        bb = (min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes))
        e_area = (bb[2] - bb[0]) * (bb[3] - bb[1])
        util[b] = {'parts': len(d['refs']), 'courtyard_mm2': round(cour, 1), 'rev_f_block_mm2': round(area(d['rects']), 1),
                   'rev_f_util': round(cour / area(d['rects']), 3),
                   'rev_e_bbox_mm': [round(bb[2] - bb[0], 1), round(bb[3] - bb[1], 1)],
                   'rev_e_bbox_util': round(cour / e_area, 3)}
    # Reference: the densest multi-part block Rev E routes at DRC 0 (blocks of >= 10 parts; the
    # BNC band, holes, relay column and K4 are a few large bodies and are compared one to one).
    ref_blocks = [b for b in util if util[b]['parts'] >= 10]
    e_max = max(util[b]['rev_e_bbox_util'] for b in ref_blocks)
    report['utilisation'] = util
    report['rev_e_max_block_util'] = e_max
    over = {b: util[b]['rev_f_util'] for b in ref_blocks if util[b]['rev_f_util'] > e_max}
    check('every Rev F multi-part block at or below the densest Rev E multi-part block', not over,
          {'rev_e_max': e_max, 'over': over})
    big = {b: (util[b]['rev_f_util'], util[b]['rev_e_bbox_util']) for b in ('relays', 'k4')}
    check('relay column packed no tighter than the Rev E relay row', util['relays']['rev_f_util'] <= util['relays']['rev_e_bbox_util'], big)
    report['courtyard_total_mm2'] = round(sum(p['courtyard_mm2'] for p in PARTS.values()), 1)
    report['courtyard_fraction'] = {'rev_e': round(report['courtyard_total_mm2'] / (140 * 105), 3),
                                    'rev_f': round(report['courtyard_total_mm2'] / 1e4, 3)}

    # 4. planned lengths vs Rev E
    lengths_f = {n: route_length(s) for n, s in ROUTES.items()}
    lengths_e = {n: INV['track_mm'].get(n, {}) for n in ROUTES}
    report['net_length_mm'] = {n: {'rev_e': lengths_e[n], 'rev_e_total': round(sum(lengths_e[n].values()), 1),
                                   'rev_f_plan': lengths_f[n], 'rev_f_total': round(sum(lengths_f[n].values()), 1)}
                               for n in ROUTES}

    # 5. capacitance forecast per net, then per harness node (worst over ranges)
    nets_fc = net_forecast(lengths_e, lengths_f)
    report['net_ground_capacitance_forecast_pf'] = nets_fc
    nodes = {}
    for node in ['sum', 'low', 'tia', 'hi', 'lowbuf', 'highbuf', 'source', 'srcdrv', 'hpot', 'lpot', 'refa']:
        best = None
        for k in range(3):
            nets = node_nets(node, k)
            if not all(n in nets_fc for n in nets):
                continue
            row = {c: round(sum(nets_fc[n][c] for n in nets), 2) for c in ('rev_e_nom', 'rev_e_high', 'rev_f_nom', 'rev_f_high')}
            if best is None or row['rev_e_high'] > best['rev_e_high']:
                best = dict(row, nets=nets)
        nodes[node] = best
    report['node_ground_capacitance_forecast_pf'] = nodes

    # loop-inductance forecast: Rev E free-space RF loops scaled by planned loop length
    # (TIA_OUT from U7.1 to the relay COM2 + the RF net); C104 loop unchanged (local, as on Rev E).
    e_path = {'RF100': 48.0 + 28.7, 'RF5K': 45.2 + 12.2, 'RF100K': 62.8 + 40.4}   # README-rev-e.md
    ind = EXTRACTED['inductance_nh']
    e_l = {'RF100': ind['r100']['high'], 'RF5K': ind['r5k']['high'], 'RF100K': ind['r100k']['high']}
    u7 = P('U7.1')
    f_path = {}
    for rf, kk in (('RF100', 'K1'), ('RF5K', 'K2'), ('RF100K', 'K3')):
        com2 = P(kk + '.8')
        f_path[rf] = abs(u7[0] - com2[0]) + abs(u7[1] - com2[1]) + sum(lengths_f[rf].values())
    report['rf_loop_forecast'] = {rf: {'rev_e_path_mm': round(e_path[rf], 1), 'rev_e_L_high_nH': e_l[rf],
                                       'rev_f_path_mm': round(f_path[rf], 1),
                                       'rev_f_L_forecast_nH': round(e_l[rf] * f_path[rf] / e_path[rf], 1)}
                                  for rf in e_path}

    # 6. switcher distances (part centres, regulator_check.py metric) Rev E vs Rev F
    sw = ['L1', 'L2', 'D2', 'D3', 'U13']
    analog = ['U5', 'U6', 'U7', 'U14']
    e_pos = {r: PARTS[r]['at'] for r in sw + analog}
    f_pos = {r: ANCHORS[r][:2] for r in sw + analog}
    dist = {}
    for name, pos in (('rev_e', e_pos), ('rev_f', f_pos)):
        per = {u: min((round(math.dist(pos[s], pos[u]), 1), s) for s in sw) for u in analog}
        dist[name] = {'per_ic': per, 'nearest': min((v[0], v[1], u) for u, v in per.items())}
    e_n, f_n = dist['rev_e']['nearest'][0], dist['rev_f']['nearest'][0]
    dist['near_field_dipole_ratio_db'] = round(60 * math.log10(e_n / f_n), 2)   # (r_E / r_F)^3 in dB
    # per IC: change of a magnetic-dipole (1/r^3) coupling from Rev E to Rev F, + = more pickup
    dist['per_ic_dipole_change_db'] = {u: round(60 * math.log10(dist['rev_e']['per_ic'][u][0] / dist['rev_f']['per_ic'][u][0]), 1)
                                       for u in analog}
    report['switcher_distance_mm'] = dist

    # 7. Rev E copper the rigid groups carry over (segments and vias wholly inside the group's Rev E
    #    courtyard box + 1 mm, on a net with a pad in the group): the share of phase-2 routing that is
    #    a coordinate transform rather than new hand routing.
    routing = json.loads((HERE.parents[1] / 'cad/routing.json').read_text())
    tot_len = sum(seg_len(t) for t in routing['tracks'])
    reuse = {}
    for name, g in RIGID.items():
        boxes = [courtyard(r) for r in g['refs']]
        bb = (min(b[0] for b in boxes) - 1, min(b[1] for b in boxes) - 1, max(b[2] for b in boxes) + 1, max(b[3] for b in boxes) + 1)
        nets = {pd[2] for r in g['refs'] for pd in PARTS[r]['pads'].values()}
        refs = set(g['refs'])
        n_t = l_t = n_v = 0
        for t in routing['tracks']:
            if t['net'] not in nets:
                continue
            pts, ok = [], True
            for q in t['points']:
                if isinstance(q, str):
                    ok &= q.split('.')[0] in refs
                    x, y, _ = PARTS[q.split('.')[0]]['pads'][q.split('.')[1]]
                    pts.append((x, y))
                else:
                    pts.append(tuple(q))
            if ok and all(bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] for x, y in pts):
                n_t += 1
                l_t += seg_len(t)
        n_v = sum(1 for v in routing['vias'] if v['net'] in nets and bb[0] <= v['at'][0] <= bb[2] and bb[1] <= v['at'][1] <= bb[3])
        reuse[name] = {'tracks': n_t, 'track_mm': round(l_t, 1), 'vias': n_v}
    report['rigid_copper_reuse'] = {'groups': reuse, 'rev_e_tracks': len(routing['tracks']),
                                    'rev_e_track_mm': round(tot_len, 1), 'rev_e_vias': len(routing['vias']),
                                    'reused_tracks': sum(v['tracks'] for v in reuse.values()),
                                    'reused_track_mm': round(sum(v['track_mm'] for v in reuse.values()), 1),
                                    'reused_vias': sum(v['vias'] for v in reuse.values())}

    # 8. Fabrication line and enclosure, Rev E vs Rev F. The JLC quote (manufacturing/order_estimate.py
    #    FAB_QUOTE, 5 boards, quoted at 140 x 100 mm) is re-scaled by board area for the lines that
    #    depend on it: 'Board' always, 'Surface finish (ENIG)' in the low case only. An ESTIMATE:
    #    JLC prices are tiered, not linear; re-quote before ordering.
    import ast
    src = (HERE.parents[1] / 'manufacturing/order_estimate.py').read_text()
    quote = ast.literal_eval(src[src.index('FAB_QUOTE = ') + len('FAB_QUOTE = '):src.index('ECONOMIC = ')].strip())
    lines = quote['lines']
    k = (OUTLINE[2] - OUTLINE[0]) * (OUTLINE[3] - OUTLINE[1]) / (140.0 * 100.0)
    rev_e = sum(lines.values())
    hi = rev_e - lines['Board'] * (1 - k)
    lo = hi - lines['Surface finish (ENIG)'] * (1 - k)
    report['fab_estimate_usd_5_boards'] = {'quote_lines': lines, 'quoted_outline_mm': [140, 100], 'area_ratio': round(k, 4),
                                           'rev_e': round(rev_e, 2), 'rev_f_low': round(lo, 2), 'rev_f_high': round(hi, 2),
                                           'saving_range': [round(rev_e - hi, 2), round(rev_e - lo, 2)]}
    # enclosure: the owner's Rev E box is the board + 10 mm each way (150 x 115 x 36); same margins
    w, h = OUTLINE[2] - OUTLINE[0], OUTLINE[3] - OUTLINE[1]
    holes = [ANCHORS[f'H{i}'][:2] for i in range(1, 5)]
    report['enclosure'] = {'rev_e_board_mm': [140, 105], 'rev_e_box_mm': [150, 115, 36],
                           'rev_f_board_mm': [w, h], 'rev_f_box_mm': [w + 10, h + 10, 36],
                           'footprint_change': round((w + 10) * (h + 10) / (150 * 115) - 1, 3),
                           'rev_e_hole_pattern_mm': [132, 92],
                           'rev_f_hole_pattern_mm': [holes[1][0] - holes[0][0], holes[2][1] - holes[0][1]],
                           'bnc_centres_from_left_edge_mm': [ANCHORS[j][0] - OUTLINE[0] for j in ('J3', 'J7', 'J8', 'J9')],
                           'rev_e_bnc_centres_from_left_edge_mm': [PARTS[j]['at'][0] - REV_E_OUTLINE[0] for j in ('J3', 'J7', 'J8', 'J9')],
                           'usb_c_centre_from_top_edge_mm': {'rev_e': PARTS['J1']['at'][1] - REV_E_OUTLINE[1],
                                                             'rev_f': ANCHORS['J1'][1] - OUTLINE[1], 'edge': 'left (x 50) on both'}}

    # 9. 5 V trunk from U16 OUT (left edge) to the switcher's 5 V pins: Manhattan length and copper
    #    resistance (1 oz outer, 35 um, 1.72e-8 ohm m) at 1.0 / 1.5 mm, against Rev E's U16 -> C80 run.
    u16 = P('U16.6')
    vin = P('U13.5')
    L = abs(u16[0] - vin[0]) + abs(u16[1] - vin[1])
    rr = {w: round(1.72e-8 * L * 1e-3 / (w * 1e-3 * 35e-6), 4) for w in (1.0, 1.5)}
    report['five_volt_trunk'] = {'from': 'U16.6', 'to': 'U13.5', 'manhattan_mm': round(L, 1), 'ohm_by_width_mm': rr,
                                 'drop_mv_at_0p45a': {w: round(v * 0.45 * 1e3, 1) for w, v in rr.items()},
                                 'rev_e_u16_to_u13_mm': round(abs(PARTS['U16']['at'][0] - PARTS['U13']['at'][0])
                                                              + abs(PARTS['U16']['at'][1] - PARTS['U13']['at'][1]), 1)}

    report['all_checks_pass'] = not fail
    (HERE / 'floorplan.json').write_text(json.dumps(report, indent=1) + '\n')
    plot(report, cy)
    print(json.dumps({'checks_failed': fail, 'utilisation': {b: u['rev_f_util'] for b, u in util.items()},
                      'rev_e_max_block_util': e_max,
                      'nets': {n: (v['rev_e_total'], v['rev_f_total']) for n, v in report['net_length_mm'].items()},
                      'switcher': dist['rev_f']['nearest'], 'switcher_rev_e': dist['rev_e']['nearest']}, indent=1))
    return 0 if not fail else 1


COLORS = {'bnc': '#9aa5b1', 'holes': '#d9d9d9', 'source': '#f4b183', 'codec': '#a9d18e', 'afe_hi': '#9dc3e6',
          'relays': '#ffd966', 'tia': '#8faadc', 'k4': '#ffe699', 'ldo': '#c9a0dc', 'drivers': '#f8cbad',
          'switcher': '#e06666', 'digital': '#b4c7e7'}


def plot(report, cy):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig, ax = plt.subplots(figsize=(12.6, 11.2), dpi=130)
    x0, y0, x1, y1 = OUTLINE
    for b, d in BLOCKS.items():
        for i, r in enumerate(d['rects']):
            ax.add_patch(Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], fc=COLORS[b], ec='#555', lw=0.6, alpha=0.45))
        r = max(d['rects'], key=lambda q: (q[2] - q[0]) * (q[3] - q[1]))
        if b != 'holes':
            u = report['utilisation'][b]
            ax.text(r[0] + 0.8, r[3] - 0.8, f"{b}  {u['rev_f_util'] * 100:.0f} %", fontsize=7.5, va='bottom',
                    ha='left', weight='bold', color='#222')
    for ref, c in cy.items():
        big = PARTS[ref]['courtyard_mm2'] > 15 or ref[0] in 'UKJ'
        ax.add_patch(Rectangle((c[0], c[1]), c[2] - c[0], c[3] - c[1], fc='white', ec='#222' if big else '#666',
                               lw=0.8 if big else 0.4, alpha=0.85))
        if big:
            ax.text((c[0] + c[2]) / 2, (c[1] + c[3]) / 2, ref, fontsize=6.5, ha='center', va='center')
    netcol = {'SOURCE_BUF': '#c00000', 'TIA_OUT': '#0050c0', 'DUT_HI': '#ff7f0e', 'DUT_LO': '#2ca02c',
              'HPOT': '#8c564b', 'LPOT': '#9467bd', 'EXCITE': '#d62728', 'RF100': '#17becf', 'RF5K': '#17becf',
              'RF100K': '#17becf', 'C1M_DIV': '#7f7f7f', 'C2P_DIV': '#7f7f7f', 'C2M_DIV': '#7f7f7f'}
    style = {'F.Cu': '-', 'In2.Cu': '--', 'B.Cu': ':'}
    for n, segs in ROUTES.items():
        if n not in netcol:
            continue
        first = True
        for layer, wp in segs:
            if isinstance(wp, (int, float)):
                continue
            pts = []
            for a, b in zip(wp, wp[1:]):
                pts += [a, (b[0], a[1]), b]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], style[layer], color=netcol[n], lw=1.4,
                    label=n if first and n not in ('RF5K', 'RF100K', 'C2P_DIV', 'C2M_DIV') else None)
            first = False
    sw = report['switcher_distance_mm']['rev_f']['nearest']
    a, b = ANCHORS[sw[1]][:2], ANCHORS[sw[2]][:2]
    ax.annotate('', xy=b, xytext=a, arrowprops=dict(arrowstyle='<->', color='k', lw=1))
    ax.text((a[0] + b[0]) / 2 + 1, (a[1] + b[1]) / 2, f"{sw[0]:.1f} mm\n{sw[1]}-{sw[2]}", fontsize=7.5)
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec='k', lw=1.6))
    for xb in (67, 89, 111, 133):
        ax.add_patch(Rectangle((xb - 4.8, y0 - 12), 9.6, 12, fc='#bbb', ec='#555', lw=0.6))
    ax.text(100, y0 - 13.5, 'HCUR  HPOT  LPOT  LCUR barrels (22 mm pitch) through the front wall', ha='center', fontsize=7.5)
    ax.text(x0 - 1, 122, 'USB-C', rotation=90, ha='right', va='center', fontsize=7.5)
    ax.set_xlim(x0 - 6, x1 + 4)
    ax.set_ylim(y1 + 3, y0 - 17)
    ax.set_aspect('equal')
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.legend(loc='center left', bbox_to_anchor=(1.01, 0.5), fontsize=7.5,
              title='planned routes\nF.Cu solid, In2 dashed,\nB.Cu dotted', title_fontsize=7.5, framealpha=0.9)
    fc = report['courtyard_fraction']
    ax.set_title(f"Rev F floorplan, 100 x 100 mm (courtyards {fc['rev_f'] * 100:.1f} % of board; Rev E "
                 f"{fc['rev_e'] * 100:.1f} % of 140 x 105)", fontsize=10)
    fig.tight_layout()
    fig.savefig(HERE / 'floorplan.png')


if __name__ == '__main__':
    raise SystemExit(main())
