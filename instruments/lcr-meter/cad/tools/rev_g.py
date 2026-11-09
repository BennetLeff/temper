"""Rev G: Rev F plus jack protection and isolation, on 100 x 110 mm, as explicit edits of the Rev F script.

python3 cad/tools/rev_g.py [--check] [--render BLOCK,...|all] [--no-write] [--pads REF,...]

Runs cad/tools/rev_f.py up to its craft passes (Rev E sources from git, the Rev F placement and hand routes),
then:
  * Board 100 x 110 mm.  Everything south of y 57.0 (the Rev F BNC band ends at 56.9) moves 10 mm south
    as one rigid body, so the analog core's copper is unchanged; the new 10 mm band (y 57-67) under the
    jacks takes the protection.  Only vertical copper crosses the cut (rev_g_routes.py checks it).
  * Netlist: the jacks become JK_HCUR / JK_HPOT / JK_LPOT / JK_LCUR, each behind a TVS and a normally-open
    TLP172AM photoMOS and a series resistor; R105 / R106 / R107 and K4 (both poles) on the jack side;
    second-stage clamps on DUT_HI / HPOT / LPOT / DUT_LO; residual-voltage senses on GPIO 28 / 29; the LED
    drive on GPIO 15; the UART header on GPIO 0 / 1.  Values and the screens behind them:
    validation/rev-g-protection/README.md; decisions: docs/rev-g-plan.md.
  * cad/tools/rev_g_routes.py adds the band copper by coordinates (no autorouter, no path search), then the
    craft passes, GND pours, silk and fab notes run as in Rev F.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
_REV_F = _TOOLS / 'rev_f.py'
_src = _REV_F.read_text()
_CRAFT = '# ------------------------------------------------------------------ craft passes'
_SILK_FNS = '# ------------------------------------------------------------------ silk reference designators'
_COIL_TP = '# relay-coil test pads keep'
exec(compile(_src[:_src.index(_CRAFT)], str(_REV_F), 'exec'), globals())

REV_F_TESTPOINTS = TESTPOINTS  # noqa: F821  (rev_f_routes.py)

# ------------------------------------------------------------------ the cut: everything south of y 57.0 moves 10 mm
CUT, SHIFT = 57.0, 10.0
BAND = (57.0, 67.0)
FRONT = {'J3', 'J7', 'J8', 'J9', 'D4', 'R12'}       # stay at the front edge


def sy(y):
    return round(y + SHIFT, 4) if y > CUT else y


for r, p in parts.items():
    if p['pcb'][1] > CUT:
        assert r not in FRONT, r
        p['pcb'][1] = sy(p['pcb'][1])
    else:
        assert r in FRONT, (r, p['pcb'])

CROSSING = []          # copper that spans the cut (stretched): must be vertical, or is edited below
for t in routing['tracks']:
    ys = [p[1] for p in t['points']]
    if min(ys) <= CUT < max(ys):
        CROSSING.append((t['net'], t['layer'], [tuple(p) for p in t['points']]))
    t['points'] = [[x, sy(y)] for x, y in t['points']]
for v in routing['vias']:
    v['at'] = [v['at'][0], sy(v['at'][1])]
for z in routing['zones']:
    z['points'] = [[x, sy(y)] for x, y in z['points']]
for ko in routing['keepouts']:
    ys = [p[1] for p in ko['points']]
    if sum(ys) / len(ys) > CUT:          # a keep-out moves with its centre (FID1's ring dips 0.02 mm over the cut)
        ko['points'] = [[x, round(y + SHIFT, 4)] for x, y in ko['points']]
    else:
        assert max(ys) <= CUT, ko['name']

OUTLINE = [50, 45, 150, 155]
design['board'].update(
    size=[100, 110], outline=OUTLINE,
    holes=[[x, sy(y)] for x, y in design['board']['holes']],
    fiducials=[[x, sy(y)] for x, y in design['board']['fiducials']],
    testpoints=[[n, net, x, sy(y), d] for n, net, x, y, d in design['board']['testpoints']])
TESTPOINTS = [(n, net, x, sy(y), d, lx, sy(ly)) for n, net, x, y, d, lx, ly in REV_F_TESTPOINTS]
design['revision'] = 'G'
design['date'] = '2026-11-09'


# ------------------------------------------------------------------ jack copper (Rev G frame, after the shift)
def take(net, layer, first=None, last=None):
    """The one hand-routed polyline of this net and layer starting (ending) at the given point."""
    hit = [t for t in routing['tracks'] if t['net'] == net and t['layer'] == layer
           and (first is None or math.dist(t['points'][0], first) < 1e-3)
           and (last is None or math.dist(t['points'][-1], last) < 1e-3)]
    assert len(hit) == 1, (net, layer, first, last, len(hit))
    return hit[0]


def drop_track(t):
    routing['tracks'].remove(t)


def via_at(net, x, y):
    hit = [v for v in routing['vias'] if v['net'] == net and math.dist(v['at'], (x, y)) < 1e-3]
    assert len(hit) == 1, (net, x, y)
    return hit[0]


# HCUR: the B.Cu run under the jack band to K4 COM2 stays, now jack side (JK_HCUR)
take('DUT_HI', 'B.Cu', first=(67.0, 51.0))['net'] = 'JK_HCUR'
via_at('DUT_HI', 131.5, 76.0)['net'] = 'JK_HCUR'
take('DUT_HI', 'F.Cu', first=(131.5, 76.0))['net'] = 'JK_HCUR'
# DUT_HI (protected side) keeps the x 90.2 F.Cu spine to the RG resistors; it now starts at the band
routing['vias'].remove(via_at('DUT_HI', 90.2, 56.9))
take('DUT_HI', 'F.Cu', first=(90.2, 56.9))['points'][0] = [90.2, 65.8]
drop_track(take('DUT_HI', 'F.Cu', last=(90.2, 71.125)))      # R105 moves to the jack side
# HPOT / LPOT: the jack legs go; the runs to U6 +IN / U7 +IN stay (open ends at y 68.725 / 70.8)
t = take('HPOT', 'F.Cu', first=(89.0, 51.0))
t['points'] = t['points'][2:]
drop_track(take('HPOT', 'F.Cu', last=(87.475, 69.475)))
t = take('LPOT', 'F.Cu', first=(111.0, 51.0))
t['points'] = t['points'][2:]
drop_track(take('LPOT', 'F.Cu', last=(115.5, 70.0)))
# DUT_LO: the J9 leg and the R106 stub go; the R107 stub is jack side (JK_LCUR); the run to the TIA stays
drop_track(take('DUT_LO', 'F.Cu', first=(133.0, 51.0)))
drop_track(take('DUT_LO', 'F.Cu', first=(130.5, 70.1)))   # R107 now joins JK_LCUR from rev_g_routes.py
# UART: GPIO 28 / 29 become the jack senses (their F.Cu escapes and vias stay, renamed); the header J6 goes,
# and with it the In2 runs to it
for t in list(routing['tracks']):
    if t['net'] in ('UART_TX', 'UART_RX'):
        if t['layer'] == 'F.Cu':
            t['net'] = {'UART_TX': 'JACK_HC', 'UART_RX': 'JACK_LC'}[t['net']]
        else:
            routing['tracks'].remove(t)
for v in routing['vias']:
    if v['net'] in ('UART_TX', 'UART_RX'):
        v['net'] = {'UART_TX': 'JACK_HC', 'UART_RX': 'JACK_LC'}[v['net']]
assert {(n, l) for n, l, _ in CROSSING} == {('DUT_HI', 'B.Cu'), ('DUT_HI', 'F.Cu'), ('HPOT', 'F.Cu'),
                                              ('LPOT', 'F.Cu'), ('DUT_LO', 'F.Cu'), ('STATUS', 'In2.Cu')}, CROSSING
for t in routing['tracks']:                  # what still spans the cut is vertical there
    for a, b in zip(t['points'], t['points'][1:]):
        if min(a[1], b[1]) <= CUT < max(a[1], b[1]):
            assert abs(a[0] - b[0]) < 1e-6, (t['net'], t['layer'], a, b)

# ------------------------------------------------------------------ netlist
for j, n in (('J3', 'JK_HCUR'), ('J7', 'JK_HPOT'), ('J8', 'JK_LPOT'), ('J9', 'JK_LCUR')):
    parts[j]['pins']['5'] = n
parts['R105']['pins'] = {'1': 'JK_HCUR', '2': 'JK_HPOT'}
parts['R106']['pins'] = {'1': 'JK_LCUR', '2': 'JK_LPOT'}
parts['R107']['pins']['1'] = 'JK_LCUR'
parts['K4']['pins'].update({'8': 'JK_HCUR', '3': 'JK_HCUR', '4': 'JK_HPOT'})   # pole 1 shorts HCUR-HPOT (bypass)
parts['U1']['pins'].update({'40': 'JACK_HC', '41': 'JACK_LC', '18': 'ISO_DRIVE'})
# The optional UART header goes (docs/rev-g-plan.md): the firmware never enables UART stdio, GPIO 28 / 29 are now
# the jack senses, and GPIO 0 / 1 cannot leave U1's east side past the I2S / QSPI / USB escape vias.
assert parts['J6']['pins'] == {'1': 'UART_TX', '2': 'UART_RX'}, parts['J6']
del parts['J6']
design['parts'] = [p for p in design['parts'] if p['ref'] != 'J6']
for r in ('R105', 'R106'):
    parts[r]['sheet'] = 'protect'
for r in ('R105', 'R106', 'R107'):
    parts[r]['source_query'] += '; Rev G: jack side of the isolation switches'

design['pinouts']['TVS'] = {'1': ['A1', 'passive'], '2': ['A2', 'passive']}
design['pinouts']['PHOTOMOS'] = {'1': ['A', 'passive'], '3': ['K', 'passive'], '4': ['D', 'passive'],
                                 '6': ['D', 'passive']}
design['pinouts']['BAV99'] = {'1': ['A1', 'passive'], '2': ['K2', 'passive'], '3': ['K1A2', 'passive']}


def like(src, ref, pins, query, **kw):
    """A new part with the BOM record (MPN, LCSC, price) of an existing one."""
    p = {k: v for k, v in parts[src].items() if k not in ('group',)}
    p.update(ref=ref, pins=pins, pcb=[0, 0, 0], sheet='protect', source_query=query, **kw)
    return p


def new(ref, kind, value, fp, pins, mpn, mfr, lcsc, usd, stock, lib, query):
    return {'ref': ref, 'value': value, 'kind': kind, 'footprint': fp, 'pins': pins, 'pcb': [0, 0, 0],
            'sheet': 'protect', 'mpn': mpn, 'manufacturer': mfr, 'lcsc': lcsc, 'unit_usd': usd, 'stock': stock,
            'library_type': lib, 'assembly': 'SMT', 'source_query': query}


# part records: validation/rev-g-protection/part-selection/parts.json (recommended rows, JLC 2026-11-08)
_SEL = 'validation/rev-g-protection/part-selection/parts.json'
_TVS = ('H4V5HD3B', 'Zhuhai Hongjiacheng (HJC)', 'C20615803', 0.0373, 62587, 'preferred')
_TVS2 = ('H3V3LD5B', 'Zhuhai Hongjiacheng (HJC)', 'C20615817', 0.0192, 3936764, 'preferred')
_MOS = ('TLP172AM(TPL,E)', 'Toshiba', 'C2152276', 0.7934, 46709, 'extended')
_R10 = ('CRCW080510R0FKEAHP', 'Vishay Draloric', 'C844598', 0.0359, 219436, 'extended')
_R100 = ('CRCW0603100RFKEAHP', 'Vishay Draloric', 'C844725', 0.028, 108992, 'extended')
_C1N = ('CC0603JRNPO9BN102', 'Yageo', 'C106246', 0.0066, 784506, 'extended')
_PAIR = ('BAV99,215', 'Nexperia', 'C2500', 0.0111, 1220356, 'basic')
_R300 = ('0603WAF3000T5E', 'UNI-ROYAL(Uniroyal Elec)', 'C23025', 0.0017, 2847215, 'basic')
JACKS = {'HCUR': ('J3', 'JK_HCUR'), 'HPOT': ('J7', 'JK_HPOT'), 'LPOT': ('J8', 'JK_LPOT'), 'LCUR': ('J9', 'JK_LCUR')}
INNER = {'HCUR': 'DUT_HI', 'HPOT': 'HPOT', 'LPOT': 'LPOT', 'LCUR': 'DUT_LO'}
G_PARTS = []
for i, (name, (j, jk)) in enumerate(JACKS.items()):
    iso = 'ISO_' + name
    G_PARTS.append(new(f'D{21 + i}', 'TVS', 'H4V5HD3B', 'LCR:D_SOD-323_HJC', {'1': jk, '2': 'GND'}, *_TVS,
                       f'{name} jack TVS, bidirectional 4.5 V standoff, VC 10 V at 40 A 8/20 ({_SEL})'))
    # LED strings: HCUR + HPOT on ISO_S1, LPOT + LCUR on ISO_S2, both sunk by Q7 (ISO_SINK)
    a, k_ = {'HPOT': ('ISO_S1', 'ISO_S1M'), 'HCUR': ('ISO_S1M', 'ISO_SINK'),
             'LPOT': ('ISO_S2', 'ISO_S2M'), 'LCUR': ('ISO_S2M', 'ISO_SINK')}[name]
    d_jack, d_in = ('4', '6') if name in ('HCUR', 'LCUR') else ('6', '4')   # output pins interchangeable: north = jack
    G_PARTS.append(new(f'U{18 + i}', 'PHOTOMOS', 'TLP172AM', 'LCR:Toshiba_11-4M1S',
                       {'1': a, '3': k_, d_jack: jk, d_in: iso}, *_MOS,
                       f'{name} isolation switch, normally open, 60 V / 0.7 A ({_SEL})'))
    cur = name in ('HCUR', 'LCUR')
    G_PARTS.append(new(f'R{122 + i}', 'R', '10R' if cur else '100R',
                       'Resistor_SMD:R_0805_2012Metric' if cur else 'Resistor_SMD:R_0603_1608Metric',
                       {'1': iso, '2': INNER[name]}, *(_R10 if cur else _R100),
                       f'{name} series resistor after the switch, anti-surge thick film ({_SEL})'))
for i, name in enumerate(('HCUR', 'HPOT', 'LPOT')):
    G_PARTS.append(new(f'D{25 + i}', 'TVS', 'H3V3LD5B', 'Diode_SMD:D_SOD-523', {'1': INNER[name], '2': 'GND'},
                       *_TVS2, f'{INNER[name]} second-stage TVS, 3.3 V standoff ({_SEL})'))
for i, net in enumerate(('HPOT', 'LPOT')):
    G_PARTS.append(new(f'C{119 + i}', 'C', '1nF C0G', 'Capacitor_SMD:C_0603_1608Metric', {'1': net, '2': 'GND'},
                       *_C1N, f'{net} edge filter with the 100R series resistor ({_SEL})'))
G_PARTS.append(new('D28', 'BAV99', 'BAV99', 'Package_TO_SOT_SMD:SOT-23', {'1': 'GND', '2': 'GND', '3': 'DUT_LO'},
                   *_PAIR, f'DUT_LO (TIA input) +-0.6 V clamp pair ({_SEL})'))
# residual-voltage senses: 1.5M from the CUR jack, 240k to 3V3, 240k + 100 nF to GND (drive_budget.py)
for k_, (jk, sns, r0, c) in enumerate((('JK_HCUR', 'JACK_HC', 126, 121), ('JK_LCUR', 'JACK_LC', 129, 122))):
    G_PARTS += [
        like('R111', f'R{r0}', {'1': jk, '2': sns}, f'{sns} divider top, at the jack'),
        like('R83', f'R{r0 + 1}', {'1': sns, '2': '3V3'}, f'{sns} bias to 3V3 (mid-scale)'),
        like('R83', f'R{r0 + 2}', {'1': sns, '2': 'GND'}, f'{sns} divider bottom'),
        like('C116', f'C{c}', {'1': sns, '2': 'GND'}, f'{sns} filter, 11 ms with the divider'),
    ]
G_PARTS += [
    new('R132', 'R', '300R', 'Resistor_SMD:R_0603_1608Metric', {'1': 'VRLY', '2': 'ISO_S1'}, *_R300,
        'HCUR + HPOT LED string, 5.0 mA at 4.31 V and VF 1.4 V (drive_budget.py)'),
    new('R133', 'R', '300R', 'Resistor_SMD:R_0603_1608Metric', {'1': 'VRLY', '2': 'ISO_S2'}, *_R300,
        'LPOT + LCUR LED string, 5.0 mA at 4.31 V and VF 1.4 V (drive_budget.py)'),
    like('Q6', 'Q7', {'1': 'ISO_G', '2': 'GND', '3': 'ISO_SINK'}, 'isolation LED sink (the Q6 pattern)'),
    like('R108', 'R134', {'1': 'ISO_DRIVE', '2': 'ISO_G'}, 'Q7 gate resistor (GPIO15)'),
    like('R109', 'R135', {'1': 'ISO_G', '2': 'GND'}, 'Q7 gate pull-down: switches open from power-up'),
]
for p in G_PARTS:
    assert p['ref'] not in parts, p['ref']
    parts[p['ref']] = p
design['parts'] += G_PARTS

# ------------------------------------------------------------------ placement of the band (x, y, rot)
XJ = {'HCUR': 67.0, 'HPOT': 89.0, 'LPOT': 111.0, 'LCUR': 133.0}
PLACE_G = {}
for i, (name, xj) in enumerate(XJ.items()):
    lc = name == 'LCUR'
    PLACE_G[f'D{21 + i}'] = (xj + 1.1, 58.2, 0)                       # pad 1 on the jack line, pad 2 to the BNC GND leg
    PLACE_G[f'U{18 + i}'] = (xj + 3.15, 61.6, 180) if lc else (xj - 3.15, 61.6, 0)   # output pins on x = xj
PLACE_G.update({
    # HCUR and LCUR switches face outward (LED pins east), HPOT / LPOT inward (LED pins west); see rev_g_routes.py
    'U18': (70.15, 61.6, 180),
    'R122': (64.1, 62.87, 180), 'R123': (91.9, 62.87, 0), 'R124': (113.9, 62.87, 0), 'R125': (130.0, 62.87, 180),
    'D25': (61.1, 62.87, 180), 'C119': (85.6, 65.4, 180), 'D26': (85.9, 67.2, 180),
    'C120': (117.9, 65.6, 0), 'D27': (117.6, 67.4, 0), 'D28': (124.9, 65.2, 180),
    # POT-CUR ties in the gaps between the jacks, on the jack pins' own F.Cu legs
    'R105': (78.0, 51.0, 0), 'R106': (122.0, 51.0, 180),
    # sense tops at the CUR jacks; dividers and filters north of U1 (3V3 on the B.Cu codec feed at y 109)
    'R126': (59.2, 53.0, 270), 'R129': (141.5, 51.0, 0),
    # sense dividers: ground legs and filter caps at the west end of the band (on the west-edge runs), the 3V3
    # legs north-west of U1 beside its 3V3 escape
    'C121': (55.4, 59.2, 0), 'R128': (55.4, 60.8, 0), 'C122': (55.4, 62.6, 0), 'R131': (55.4, 64.2, 0),
    'R127': (64.6, 121.6, 270), 'R130': (66.2, 121.6, 270),
    # LED sink between U18 and U19; string resistors at K1's VRLY pad and beside U20
    'Q7': (77.45, 59.2, 180), 'R134': (78.3875, 62.4, 90), 'R135': (80.2, 59.325, 90),
    'R132': (95.22, 65.6, 90), 'R133': (101.4, 60.6, 90),
})
for r, at in PLACE_G.items():
    parts[r]['pcb'] = list(at)

# The pre-DRC needs every footprint's pads (cad/tools/pad_library.json, dumped from a built board)
_missing = sorted({predrc.fp_name(p) for p in parts.values()} - set(LIB))
if _missing:
    design['parts'] = [parts[p['ref']] for p in design['parts']]
    (CAD / 'design.json').write_text(json.dumps(design, indent=2) + '\n')
    (CAD / 'routing.json').write_text(json.dumps({**routing, 'craft_exceptions': []}, indent=2) + '\n')
    sys.exit(f'pad_library.json lacks {_missing}: wrote design.json; run <kicad-python> cad/build_cad.py, then '
             '<kicad-python> cad/tools/pad_library.py, then rev_g.py again')

# ------------------------------------------------------------------ hand routes (Rev G band)
L.src_file = 'rev_g_routes.py'
SRC_FILE = CAD / 'tools' / 'rev_g_routes.py'
exec(compile(SRC_FILE.read_text(), str(SRC_FILE), 'exec'), globals())

# ------------------------------------------------------------------ craft, pours (as Rev F; the core block moves with the cut)
design['board']['craft'] = True
design['board']['teardrops'] = True
CRAFT = craft.run(routing, *predrc.craft_inputs({'parts': list(parts.values()), 'board': design['board']}),
                  rules=predrc.RULES)
import pour  # noqa: E402
pour.ANALOG_CORE = [(x, sy(y)) for x, y in pour.ANALOG_CORE]
POUR = pour.add({'parts': list(parts.values()), 'board': design['board']}, routing)

# ------------------------------------------------------------------ silk and reference text
design['board']['silk'] = [
    ['TEMPER LCR REV G', 106.0, 150.2, 1.0],
    ['HCUR', 63, 57.6, 1.0], ['HPOT', 85, 57.6, 1.0], ['LPOT', 107, 57.6, 1.0], ['LCUR', 129, 57.6, 1.0],   # beside the TVS row
    ['DISCHARGED', 100, 46.35, 1.0], ['DUT ONLY', 100, 47.95, 1.0],
    ['5V', 102.0, 143.3, 1.0], ['3V3', 104.6, 144.8, 1.0], ['+12', 107.2, 143.3, 1.0], ['-12', 109.8, 144.8, 1.0],
    ['HB', 58.8, 112.6, 1.0], ['FLT', 61.2, 111.2, 1.0],
] + [[name, lx, ly, 1.0] for name, _, _, _, _, lx, ly in TESTPOINTS]
design['board']['ref_size'] = [1.0, 0.15]
design['board']['ref_text'] = {'U3': [56.85, 148.3], 'U7': [118.3, 78.2], 'U13': [144.3, 147.5], 'U14': [64.0, 105.2],
                               'U16': [51.9, 142.4], 'U6': [82.0, 78.3], 'U15': [56.6, 89.7]}
_s = _src.index(_SILK_FNS)
exec(compile(_src[_s:_src.index(_COIL_TP)], str(_REV_F), 'exec'), globals())     # ref_key, silk_obstacles, silk_refs

COIL_TP_MIN = 10.0
_an = [x['geom'] for x in sum(predrc.dyn_items(routing), []) + predrc.static_items(
    {'parts': list(parts.values()), 'board': design['board']})[0] if x['net'] in pour.ANALOG]
COIL_TP = {t[0]: round(min(g.distance(predrc.Point(t[2], t[3])) for g in _an), 2)
           for t in design['board']['testpoints'] if t[1].startswith('RLY_')}
assert all(d >= COIL_TP_MIN for d in COIL_TP.values()), COIL_TP

SILK_REFS, SILK_MISSING, _todo, _ink, _obs = silk_refs()  # noqa: F821
SILK_VIOL = craft.ref_checks(SILK_REFS, _ink, _todo, _obs)
assert not SILK_VIOL, SILK_VIOL
design['board']['ref_text'].update(SILK_REFS)
design['board']['refs_on_silk_only_if_placed'] = True


# ------------------------------------------------------------------ fabrication drawing
def fab_notes():
    from collections import Counter
    x0, y0, x1, y1 = design['board']['outline']
    pads, drills, _ = predrc.static_items({'parts': list(parts.values()), 'board': design['board']})
    vias = Counter((v.get('drill', 0.3), v.get('diameter', 0.6)) for v in routing['vias'])
    size = lambda g: tuple(sorted(round(b - a, 2) for a, b in zip(g.bounds[:2], g.bounds[2:])))  # noqa: E731
    pth = Counter(size(d['geom']) for d in drills if d['net'] is not None)
    npth = Counter(size(d['geom']) for d in drills if d['net'] is None)
    fmt = lambda wh: f'{wh[0]:.2f} mm' if abs(wh[0] - wh[1]) < 0.01 else f'{wh[0]:.2f} x {wh[1]:.2f} mm slot'  # noqa: E731
    drill = [f'  vias      {n:4d} x {d:.2f} mm drill, {pad:.2f} mm pad' for (d, pad), n in sorted(vias.items())]
    drill += [f'  PTH       {n:4d} x {fmt(wh)}' for wh, n in sorted(pth.items())]
    drill += [f'  NPTH      {n:4d} x {fmt(wh)}' for wh, n in sorted(npth.items())]
    total = sum(vias.values()) + sum(pth.values()) + sum(npth.values())
    lines = [
        'TEMPER LCR REV G - FABRICATION NOTES',
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
design['board']['fab_dims'] = [[OUTLINE[0], OUTLINE[3], OUTLINE[2], OUTLINE[3], 6.0],
                               [OUTLINE[0], OUTLINE[3], OUTLINE[0], OUTLINE[1], -6.0]]

def views():
    from_f = {'afe_hi': (78, 55, 96, 105), 'relays': (90, 55, 112, 106), 'tia': (104, 55, 126, 85),
              'k4': (122, 55, 150, 86), 'source': (55, 55, 82, 80), 'codec': (50, 74, 86, 102),
              'ldo': (120, 84, 150, 114), 'drivers': (78, 100, 124, 118), 'switcher': (116, 112, 150, 145),
              'digital': (50, 100, 92, 145), 'south': (50, 95, 150, 145), 'mid': (85, 112, 125, 145)}
    v = {n: (x0, sy(y0), x1, sy(y1)) for n, (x0, y0, x1, y1) in from_f.items()}
    v.update({'band': (50, 45, 150, 72), 'band_w': (50, 45, 100, 72), 'band_e': (100, 45, 150, 80),
              'west': (50, 55, 75, 140), 'u1': (60, 120, 92, 150), 'u1w': (58, 128, 72, 142), 'esc': (64, 133, 72, 140), 'midw': (62, 56, 92, 132), 'divs': (52, 104, 80, 120), 'dive': (76, 104, 96, 124), 'nw1': (56, 117, 70, 129), 'uart': (74, 130, 92, 155), 'board': (50, 45, 150, 155)})
    return v


VIEWS = views()


def pads_of(*refs):
    for r in refs:
        print(r, parts[r]['pcb'], '  '.join(f"{p['num']}:{parts[r]['pins'].get(p['num'])}@{P(r + '.' + p['num'])[0]:.3f},"
                                              f"{P(r + '.' + p['num'])[1]:.3f}" for p in fp(r)['pads'] if p['num']))


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
    print(f"{len(design['parts'])} parts, {len(routing['tracks'])} tracks, {len(routing['vias'])} vias")
    if a.check or a.render:
        res = predrc.check(design, routing)
        print(predrc.summary(res, limit=80))
        (ROOT / 'build').mkdir(exist_ok=True)
        (ROOT / 'build' / 'rev-g-predrc.json').write_text(json.dumps(res, indent=1) + '\n')
        if a.render:
            names = list(VIEWS) if a.render == 'all' else a.render.split(',')
            for n in names:
                lay = tuple(a.layers.split(','))
                tag = '' if len(lay) == 3 else '-' + '+'.join(l.split('.')[0] for l in lay)
                out = ROOT / 'build' / f'rev-g-{n}{tag}.png'
                predrc.render(design, routing, res, VIEWS[n], out, title=f'Rev G {n}', layers=lay)
                print('  render', out)
    if not a.no_write:
        clean = {'tracks': [{k: v for k, v in t.items() if k != 'src'} for t in routing['tracks']],
                 'vias': [{k: v for k, v in v.items() if k != 'src'} for v in routing['vias']],
                 'zones': routing['zones'], 'keepouts': routing['keepouts'],
                 'craft_exceptions': routing['craft_exceptions']}
        (CAD / 'design.json').write_text(json.dumps(design, indent=2) + '\n')
        (CAD / 'routing.json').write_text(json.dumps(clean, indent=2) + '\n')


if __name__ == '__main__':
    main()
