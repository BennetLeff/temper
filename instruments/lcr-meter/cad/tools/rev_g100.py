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
    ('VB', 62.225): (59.4, 112.9, 59.4, 111.3),          # USB_VBUS at U16 IN, north of C113
    ('GND', 64.225): (61.3, 112.9, 61.3, 111.3),
}
for t in _tp:
    for (nm, ox), new in _TP_MOVE.items():
        if t[0] == nm and abs(t[2] - ox) < 1e-6:
            t[2], t[3], t[5], t[6] = new

# ------------------------------------------------------------------ parts placed again (x, y, rot)
PLACE_G100 = {
    # QSPI flash west of U1's south side (pins 1-4 east, facing U1's QSPI pins), its passives around it
    'U2': (62.6, 141.45, 180),
    # buttons east of U1, where J5 was (J5 goes: the debugger takes VTREF / GND from TP8 / TP9 beside them)
    'SW1': (87.1, 138.9, 0), 'SW2': (87.1, 142.9, 0),
    # debug LEDs (lid-off): HB / FLT between the power entry and J4, LED north, resistor south
    'D19': (63.0, 113.5, 270), 'R117': (63.0, 116.5, 270), 'D20': (64.8, 113.5, 270), 'R118': (64.8, 116.5, 270),
    # RAW_P series resistor into the LDO pair: 2.8 mm north, clear of the switcher's new top row
    'R95': (129.6, 116.0, 0),
}
for r, at in PLACE_G100.items():
    parts[r]['pcb'] = list(at)
del parts['J5']
design['parts'] = [p for p in design['parts'] if p['ref'] != 'J5']

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--render', default='')
    ap.add_argument('--layers', default='B.Cu,In2.Cu,F.Cu')
    ap.add_argument('--no-write', action='store_true')
    ap.add_argument('--pads', default='')
    a = ap.parse_args()
    if a.pads:
        pads_of(*a.pads.split(','))  # noqa: F821
    design['parts'] = [parts[p['ref']] for p in design['parts']]
    print('moved:', MOVED)
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


VIEWS100 = {'south': (50, 100, 150, 145), 'west': (50, 108, 92, 145), 'mid': (84, 110, 126, 145),
            'east': (112, 95, 150, 145), 'board': (50, 45, 150, 145), 'u1': (56, 112, 92, 145)}

if __name__ == '__main__':
    main()
