"""Rev G100: Rev G (protected jacks) on 100 x 100 mm, as explicit edits of the Rev G script.

python3 cad/tools/rev_g100.py [--check] [--render BLOCK,...|all] [--no-write] [--pads REF,...]

Runs cad/tools/rev_g.py up to its craft passes (Rev F placement and routes, the Rev G cut and band), then takes
10 mm out of the digital / power section without touching the analog core, the protection band or the LDO pair:
  * two rigid bodies move 10 mm north with their own copper:
      west  J1 and the USB block, the power entry (U16, U3 and their passives), the VB / GND test pads;
      east  the TPS65131 switcher block, its sequencer U17, the 5 V bulk C117, FID3 and H4;
    a body's copper is every segment of its nets with both ends inside its outline; a vertical segment that
    leaves the outline keeps its outside end (it shortens), any other is dropped and hand-routed again;
  * parts in the way are placed again (PLACE_G100): the QSPI flash and its passives west of U1's south side,
    the buttons and J5 east of U1, the debug LEDs, the residual-sense 3V3 legs, R95;
  * the board loses its south 10 mm (outline 100 x 100, H3 / H4 at y 141 as on Rev F);
  * cad/tools/rev_g100_routes.py adds the copper by coordinates (no autorouter, no path search), then the craft
    passes, GND pours, silk and fab notes run as in Rev G.
Plan and decisions: docs/rev-g100-plan.md.  Feasibility: validation/rev-g/shrink-100-feasibility.json.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
_REV_G = _TOOLS / 'rev_g.py'
_gsrc = _REV_G.read_text()
_G_CRAFT = '# ------------------------------------------------------------------ craft, pours'
_g_head = _gsrc[:_gsrc.index(_G_CRAFT)]
exec(compile(_g_head, str(_REV_G), 'exec'), globals())

from shapely.geometry import LineString, Point, Polygon  # noqa: E402

DY = -10.0
OUTLINE = [50, 45, 150, 145]


# ------------------------------------------------------------------ split polylines into segments
def _segments():
    out = []
    for t in routing['tracks']:
        pts = t['points']
        for a, b in zip(pts, pts[1:]):
            if a != b:
                out.append(dict(t, points=[list(a), list(b)]))
    routing['tracks'][:] = out


_segments()

# ------------------------------------------------------------------ rigid bodies (Rev G frame outlines)
BODIES = {
    # the power entry (TPS2553, its ILIM / damping / bulk, the AP2112 3V3 LDO): 24 mm north into the free strip
    # between the I2S test pads and J1; it is all SMT, so the west-edge inner-layer runs pass under it
    'west': {'parts': 'U16 R110 C113 R121 C16 U3 C17'.split(), 'dy': -24.0,
             'outline': [(50.6, 137.9), (62.0, 137.9), (62.0, 148.0), (50.6, 148.0)]},
    'east': {'parts': ('U13 L1 L2 D2 D3 C80 C81 C82 C83 C84 C85 C86 C87 C88 C89 C90 C91 C92 R80 R81 R82 R83 R84 '
                       'R111 R119 R120 U17 C116 C118 C117').split(),
             'outline': [(113.6, 141.6), (124.6, 141.6), (124.6, 128.3), (151.0, 128.3), (151.0, 156.0),
                         (113.6, 156.0)], 'dy': DY},
}
MOVED = {}
for name, b in BODIES.items():
    poly, dy = Polygon(b['outline']), b['dy']
    nets = {n for r in b['parts'] for n in parts[r]['pins'].values() if n}
    inside = lambda p, poly=poly: poly.contains(Point(p))  # noqa: E731
    keep, n_mv, n_st, n_dr = [], 0, 0, 0
    for t in routing['tracks']:
        a, c = t['points']
        ia, ic = inside(a), inside(c)
        if t['net'] not in nets or not (ia or ic):
            keep.append(t)
        elif ia and ic:
            t['points'] = [[a[0], round(a[1] + dy, 4)], [c[0], round(c[1] + dy, 4)]]
            t['src'] = f'g100:{name}'
            keep.append(t)
            n_mv += 1
        elif abs(a[0] - c[0]) < 1e-6:          # vertical across the outline: the inside end moves, it shortens
            p_in, p_out = (a, c) if ia else (c, a)
            new_in = [p_in[0], round(p_in[1] + dy, 4)]
            if (p_out[1] - new_in[1]) * (p_out[1] - p_in[1]) > 0 and abs(p_out[1] - new_in[1]) < abs(p_out[1] - p_in[1]):
                t['points'] = [p_out, new_in]
                t['src'] = f'g100:{name}:stretch'
                keep.append(t)
                n_st += 1
            else:
                n_dr += 1
        else:
            n_dr += 1
    routing['tracks'][:] = keep
    nv = 0
    for v in routing['vias']:
        if v['net'] in nets and inside(v['at']):
            v['at'] = [v['at'][0], round(v['at'][1] + dy, 4)]
            v['src'] = f'g100:{name}'
            nv += 1
    for r in b['parts']:
        parts[r]['pcb'][1] = round(parts[r]['pcb'][1] + dy, 4)
    MOVED[name] = dict(segments=n_mv, stretched=n_st, dropped=n_dr, vias=nv)

_tp = [list(t) for t in TESTPOINTS]
_TP_MOVE = {  # (name, old x, old y) -> (x, y, label x, label y)
    ('VB', 62.225): (61.225, 137.0, 63.25, 137.0),        # USB_VBUS on J1's south pins' exit, where C15 was (C15 went to U16)
    ('GND', 64.225): (61.25, 112.9, 61.75, 111.3),
    ('GND', 92.0): (94.6, 141.6, 97.2, 141.6),           # the debugger's GND beside TP8 3V3 (old spot is past the edge)
    ('3V3', 92.0): (92.0, 141.6, 92.0, 143.5),           # TP8 stays; its label goes south (SW2 is west of it now)
    ('RAW+', 128.775): (128.775, 121.5, 128.775, 119.8),  # on RAW_P's run up to R95 (the switcher's top row took its spot)
    ('RAW-', 142.5): (145.6, 116.825, 145.6, 115.0),      # east of R96's RAW_N end, label north
}
for t in _tp:
    for (nm, ox), new in _TP_MOVE.items():
        if t[0] == nm and abs(t[2] - ox) < 1e-6:
            t[2], t[3], t[5], t[6] = new

# ------------------------------------------------------------------ parts placed again (x, y, rot)
PLACE_G100 = {
    # QSPI flash west of U1's south side, against H3's courtyard; VCC (pin 8) north-east, beside its 100 nF C11, which
    # stands between it and C8 (C8 0.25 mm east)
    'U2': (62.1, 141.45, 0), 'C11': (67.48, 139.4, 90), 'C8': (69.2, 139.5, 90),
    # buttons east of U1, where J5 was (J5 goes: the debugger takes VTREF / GND from TP8 / TP9 beside them)
    'SW1': (87.1, 138.9, 0), 'SW2': (87.1, 142.9, 0),
    # debug LEDs (lid-off): FLT between the power entry and J4 (LED north, resistor south); HB in the pocket west of
    # U1, under its In2 run (resistor north, LED south)
    'R117': (64.6, 127.6, 0), 'D19': (64.6, 129.3, 180), 'D20': (64.8, 111.75, 270), 'R118': (64.8, 114.75, 270),
    # RAW_P series resistor into the LDO pair: 2.8 mm north, clear of the switcher's new top row
    'R95': (129.6, 116.0, 0),
    # CC1 pull-down upright between the 3V3 LDO's output cap C17 and R127 (the moved C17 lands on its old place)
    'R1': (61.9, 122.2, 90),
    # the flash's clock series resistor turned so its flash side faces west; the CS pull-up and BOOTSEL resistor in
    # the free patch south of R3 / R4; the RUN pull-up beside SW2, the RUN cap beside SW1 (east of the buttons)
    'R13': (73.5, 143.5, 180), 'R8': (78.6, 142.2, 0), 'R7': (78.6, 143.8, 0),
    'R9': (83.25, 140.0, 90), 'C14': (91.0, 138.75, 90),
    # 3V3 bulk next to R130's 3V3 run
    'C18': (64.75, 125.0, 90),
    # U16's 100 nF IN bypass beside U16, on TP20's old spot north of C113 (audit G-PE-1; it was left at J1)
    'C15': (59.2, 112.8, 90),
}
for r, at in PLACE_G100.items():
    parts[r]['pcb'] = list(at)
del parts['J5']
design['parts'] = [p for p in design['parts'] if p['ref'] != 'J5']

# ------------------------------------------------------------------ datasheet audit (validation/datasheet-audit-rev-g100/)
# Value changes on the same lands, and the -12 V clamp.  JLC records 2026-11-09.


def _bom(refs, value, mpn, mfr, lcsc, usd, stock, lib, query):
    for r in refs.split():
        parts[r].update(value=value, mpn=mpn, manufacturer=mfr, lcsc=lcsc, unit_usd=usd, stock=stock, library_type=lib,
                        source_query=query)


_bom('R101', '0.33R', '0603WAF330LT5E', 'UNI-ROYAL(Uniroyal Elec)', 'C23410', 0.0055, 33494, 'extended',
     'VRLY feed: recovers the relay RESET margin G100\'s longer 5V trunk took (audit RCG-01, drive_budget.py)')
_bom('R132 R133', '270R', '0603WAF2700T5E', 'UNI-ROYAL(Uniroyal Elec)', 'C22966', 0.0017, 644588, 'basic',
     'TLP172AM LED string: >= 5 mA at VBUS 4.40 V and VF max on the routed rail (audit PROT-05, drive_budget.py)')
_bom('C85', '4.7nF 50V C0G', 'CC0603JRNPO9BN472', 'YAGEO', 'C576818', 0.0285, 250589, 'extended',
     'TPS65131 CN: C0G as the datasheet specifies (audit SL-11)')
_bom('C39 C40 C44 C45 C48 C49', '2.2uF 50V X7R', 'CC0805KKX7R9BB225', 'YAGEO', 'C125847', 0.1143, 85423, 'extended',
     'OPA2810 supply: 2.2-6.8 uF "must also be used" (SBOS799 11.1; audit G-AFE-05)')
# The op amps' supply current leaves through V- while +12 V is up before -12 V (U11 starts first): nothing sinks it
# and -12V rises until an input ESD diode conducts.  A Schottky from -12V to GND at C100 holds it near 0 V (audit SL-1).
_d29 = like('D2', 'D29', {'1': 'GND', '2': '-12V'}, '-12V power-up clamp, cathode GND (audit SL-1)')
_d29['sheet'] = 'power'
parts['D29'] = _d29
design['parts'].append(_d29)
PLACE_G100['D29'] = (137.9, 99.6, 90)          # north of C100, cathode on C100's GND via
parts['D29']['pcb'] = list(PLACE_G100['D29'])

# ------------------------------------------------------------------ board
design['board'].update(
    size=[100, 100], outline=OUTLINE,
    holes=[[54, 54], [146, 54], [54, 141.0], [146, 141.0]],
    fiducials=[[53.0, 69.0], [147.0, 48.0], [147.0, 136.0]],
)
routing['zones'] = [dict(z, points=[[x, min(y, 144.5)] for x, y in z['points']]) for z in routing['zones']]
for ko in routing['keepouts']:
    if ko.get('name') == 'FID3 clear':
        ko['points'] = [[x, round(y + DY, 4)] for x, y in ko['points']]
# the debugger's GND beside J4 (SWD), 3.1 mm east of SWCLK, clear of J4's courtyard (audit MD-10)
_tp.append(['GND', 'GND', 72.1, 118.0, 1.5, 72.1, 120.0])
TESTPOINTS = [tuple(t) for t in _tp]
design['board']['testpoints'] = [list(t[:5]) for t in TESTPOINTS]
design['revision'] = 'G'


# ------------------------------------------------------------------ prune copper left dangling (given nets)
def prune(nets):
    """Remove segments and vias of these nets that the pre-DRC reports dangling, until none is left."""
    removed = 0
    while True:
        res = predrc.check({'parts': list(parts.values()), 'board': design['board']}, routing)
        drop = {v['item'] for v in res['violations'] if v['kind'] == 'dangling' and v.get('item')
                and v['nets'][0] in nets}
        if not drop:
            return removed
        removed += len(drop)
        routing['tracks'][:] = [t for i, t in enumerate(routing['tracks']) if ('track', i) not in drop]
        routing['vias'][:] = [v for i, v in enumerate(routing['vias']) if ('via', i) not in drop]


def CLEAR(nets=None, box=None, below=None, layers=None):
    """Remove segments (any end) and vias of these nets (None: all) inside a box (x0, y0, x1, y1) or south of
    a y.  Returns the nets touched, for prune()."""
    def hit(p):
        if below is not None and p[1] > below:
            return True
        return box is not None and box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]
    touched = set()
    keep = []
    for t in routing['tracks']:
        if (nets is None or t['net'] in nets) and (layers is None or t['layer'] in layers) and any(map(hit, t['points'])):
            touched.add(t['net'])
        else:
            keep.append(t)
    routing['tracks'][:] = keep
    keepv = []
    for v in routing['vias']:
        if (nets is None or v['net'] in nets) and layers is None and hit(v['at']):
            touched.add(v['net'])
        else:
            keepv.append(v)
    routing['vias'][:] = keepv
    return touched


# ------------------------------------------------------------------ hand routes
L.src_file = 'rev_g100_routes.py'
SRC_FILE = CAD / 'tools' / 'rev_g100_routes.py'
exec(compile(SRC_FILE.read_text(), str(SRC_FILE), 'exec'), globals())

# ------------------------------------------------------------------ craft, pours (as Rev G; the analog core does not move)
design['board']['craft'] = True
design['board']['teardrops'] = True
CRAFT = craft.run(routing, *predrc.craft_inputs({'parts': list(parts.values()), 'board': design['board']}),
                  rules=predrc.RULES)
import pour  # noqa: E402
pour.ANALOG_CORE = [(x, sy(y)) for x, y in pour.ANALOG_CORE]
POUR = pour.add({'parts': list(parts.values()), 'board': design['board']}, routing)

# ------------------------------------------------------------------ silk and reference text
design['board']['silk'] = [
    ['TEMPER LCR REV G100', 116.1, 129.75, 1.0],                     # the old south strip is gone; east of the drivers
    ['HCUR', 63, 57.6, 1.0], ['HPOT', 85, 57.6, 1.0], ['LPOT', 107, 57.6, 1.0], ['LCUR', 129, 57.6, 1.0],
    ['DISCHARGED', 100, 46.35, 1.0], ['DUT ONLY', 100, 47.95, 1.0],
    # rail LEDs D15-D18: two staggered rows between the LEDs and the south edge (JLC's 1.0 mm minimum text)
    ['5V', 102.0, 142.4, 1.0], ['3V3', 104.6, 143.85, 1.0], ['+12', 107.2, 142.4, 1.0], ['-12', 109.8, 143.85, 1.0],
    ['HB', 62.0, 129.4, 1.0], ['FLT', 67.6, 110.85, 1.0],
] + [[name, lx, ly, 1.0] for name, _, _, _, _, lx, ly in TESTPOINTS]
design['board']['ref_size'] = [1.0, 0.15]
# U3 / U13 / U16 moved with their blocks: their Rev G hand spots are dropped and the search places them
design['board']['ref_text'] = {'U7': [118.3, 78.2], 'U14': [64.0, 105.2], 'U6': [82.0, 78.3], 'U15': [56.6, 89.7]}
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
        'TEMPER LCR REV G100 - FABRICATION NOTES',
        f'1. Board {x1 - x0:.2f} x {y1 - y0:.2f} mm, 4 layers, 1.6 mm finished. FR-4, TG 135-140.',
        '2. Stackup JLC04161H-7628: F.Cu 1 oz | 7628 prepreg | In1.Cu 0.5 oz GND plane | core |',
        '   In2.Cu 0.5 oz signals + GND pour | 7628 prepreg | B.Cu 1 oz signals + GND pour.',
        '3. Finish ENIG. Solder mask both sides; silkscreen top only (bottom intentionally empty).',
        '4. Vias: every drill 0.30 mm. Covering "Plugged" (JLC default); do NOT order POFV.',
        '   Exposed-pad thermal vias in U1, U11, U12, U13, U14 sit under paste windows; JLC\'s',
        '   plugging fills them (TI: "filled, plugged or tented"). No other via touches an SMT land.',
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


def pads_of(*refs):
    for r in refs:
        print(r, parts[r]['pcb'], '  '.join(f"{p['num']}:{parts[r]['pins'].get(p['num'])}@{P(r + '.' + p['num'])[0]:.3f},"
                                              f"{P(r + '.' + p['num'])[1]:.3f}" for p in fp(r)['pads'] if p['num']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--render', default='')
    ap.add_argument('--layers', default='B.Cu,In2.Cu,F.Cu')
    ap.add_argument('--no-write', action='store_true')
    ap.add_argument('--pads', default='')
    a = ap.parse_args()
    if a.pads:
        pads_of(*a.pads.split(','))
    design['parts'] = [parts[p['ref']] for p in design['parts']]
    print('moved:', MOVED)
    print('craft:', CRAFT)
    print('pour:', POUR)
    print('coil test pads, mm to analog copper:', COIL_TP)
    print(f'silk refs: {len(SILK_REFS)} placed by search, {len(design["board"]["ref_text"]) - len(SILK_REFS)} by hand, '
          f'{len(SILK_MISSING)} on F.Fab only: {" ".join(SILK_MISSING)}')
    print(f"{len(design['parts'])} parts, {len(routing['tracks'])} tracks, {len(routing['vias'])} vias")
    if a.check or a.render:
        res = predrc.check(design, routing)
        print(predrc.summary(res, limit=120))
        (ROOT / 'build').mkdir(exist_ok=True)
        (ROOT / 'build' / 'rev-g100-predrc.json').write_text(json.dumps(res, indent=1) + '\n')
        for n in (a.render.split(',') if a.render else []):
            lay = tuple(a.layers.split(','))
            out = ROOT / 'build' / f'rev-g100-{n}.png'
            predrc.render(design, routing, res, VIEWS100[n], out, title=f'Rev G100 {n}', layers=lay)
            print('  render', out)
    if not a.no_write:
        clean = {'tracks': [{k: v for k, v in t.items() if k != 'src'} for t in routing['tracks']],
                 'vias': [{k: v for k, v in v.items() if k != 'src'} for v in routing['vias']],
                 'zones': routing['zones'], 'keepouts': routing['keepouts'],
                 'craft_exceptions': routing['craft_exceptions']}
        (CAD / 'design.json').write_text(json.dumps(design, indent=2) + '\n')
        (CAD / 'routing.json').write_text(json.dumps(clean, indent=2) + '\n')


VIEWS100 = {'south': (50, 100, 150, 145), 'west': (50, 108, 92, 145), 'mid': (84, 110, 126, 145),
            'east': (112, 95, 150, 145), 'board': (50, 45, 150, 145), 'u1': (56, 112, 92, 145), 'nw': (55, 98, 92, 128), 'ldo': (55, 99, 70, 122), 'band': (55, 112, 150, 145)}

if __name__ == '__main__':
    main()
