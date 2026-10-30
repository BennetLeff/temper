"""Plain-dict board model and the pad-addressed hand-routing helpers (pure; Python 3.9+, no shapely).

Shared records (mm, board frame, y down; angles in degrees, KiCad convention):

  part       {ref, footprint: 'Lib:Name', pcb: [x, y, rot], pins: {num: net}, ...}
  pad lib    {footprint name: {pads: [{num, at: [x, y], size, shape, rot, attr, copper, drill?, rr?, poly?}],
              courtyard: [[[x, y], ...]]}}  as dumped by a board's pad_library.py (KiCad Python)
  track      {net, layer, width, points: [[x, y], ...], src?}
  via        {net, at: [x, y], diameter, drill, src?}
  keepout    {name, layers, points, tracks}
  routing    {tracks, vias, zones?, keepouts?, craft_exceptions?}

Layout binds a pad library, the parts and (later) a routing dict, and provides the hand-routing helpers a
routes script calls by coordinates:

    P('U6.3', dx, dy)        board-frame pad centre after placement (+ offset)
    B('codec', x, y)         a reference-revision coordinate taken through a rigid group's transform
    T(net, layer, *pts)      a polyline;  T45(net, layer, a, b, first) one orthogonal and one 45-degree leg
    V(net, x, y)             a via;  DROP / WIDEN / KO edit copied copper, widths and rule areas

No path search anywhere: every helper is plain geometry.  Tracks and vias carry 'src' = '<routes file>:<line>'
of the call (sys._getframe), so a checker can quote the line that made them.
"""
from __future__ import annotations

import json
import math
import sys


def rot(dx, dy, t):
    """KiCad convention: footprint-local (dx, dy) at orientation t (degrees) -> board offset (y down)."""
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return dx * c + dy * s, -dx * s + dy * c


def unrot(dx, dy, t):
    return rot(dx, dy, -t)


def r3(v):
    """Coordinates are kept to 0.1 um (4 decimals); + 0.0 turns -0.0 into 0.0."""
    return round(v + 0.0, 4)


def norm_rot(t):
    t = (t + 180) % 360 - 180
    return 180 if t == -180 else t


def fp_name(part):
    """'Lib:Name' -> 'Name'."""
    return part['footprint'].split(':', 1)[1]


def load_pad_library(path):
    with open(path) as f:
        return json.load(f)


class Layout:
    """Hand-routing helpers over one board.

    lib       pad library (footprint name -> {pads, courtyard})
    parts     {ref: part}; P() reads each part's current 'pcb' pose, so placement edits are seen
    groups    {name: {'pivot': (x, y), 'to': (x, y), 'turn': deg, 'refs': [...]}} for B()
    routing   the routing dict T/T45/V/DROP/WIDEN/KO append to (may be bound later: layout.routing = ...)
    src_file  basename of the routes script whose line numbers go into 'src'; calls from anywhere else get
              src_default
    """

    def __init__(self, lib, parts, groups=None, routing=None, src_file='routes.py', src_default='layout'):
        self.lib = lib
        self.parts = parts
        self.groups = groups if groups is not None else {}
        self.routing = routing
        self.src_file = src_file
        self.src_default = src_default

    # ---------------------------------------------------------------- pads
    def fp(self, ref):
        return self.lib[fp_name(self.parts[ref])]

    def pad_local(self, ref, num):
        for p in self.fp(ref)['pads']:
            if p['num'] == num:
                return p['at']
        raise KeyError(f'{ref}.{num}')

    def pad_at(self, ref, num, pose):
        lx, ly = self.pad_local(ref, num)
        bx, by = rot(lx, ly, pose[2])
        return (r3(pose[0] + bx), r3(pose[1] + by))

    def P(self, ref_pin, dx=0.0, dy=0.0):
        """Board-frame pad centre after placement, plus an optional offset."""
        ref, num = ref_pin.split('.')
        x, y = self.pad_at(ref, num, self.parts[ref]['pcb'])
        return (r3(x + dx), r3(y + dy))

    def B(self, group, x, y):
        """A reference-revision board coordinate taken through a rigid group's transform."""
        g = self.groups[group]
        dx, dy = rot(x - g['pivot'][0], y - g['pivot'][1], g['turn'])
        return (r3(g['to'][0] + dx), r3(g['to'][1] + dy))

    # ---------------------------------------------------------------- copper
    def _src(self):
        f = sys._getframe(2)
        return (f'{self.src_file}:{f.f_lineno}' if f.f_code.co_filename.endswith(self.src_file)
                else self.src_default)

    def T(self, net, layer, *pts, w=0.2):
        pts = [self.P(p) if isinstance(p, str) else (r3(p[0]), r3(p[1])) for p in pts]
        self.routing['tracks'].append({'net': net, 'layer': layer, 'width': w, 'points': [list(p) for p in pts],
                                       'src': self._src()})

    def T45(self, net, layer, a, b, first='h', w=0.2):
        """Two segments a -> corner -> b: one orthogonal leg and one 45-degree leg.  first='h' or 'v'
        puts the horizontal / vertical leg first; first='d' puts the diagonal first (the orthogonal leg
        then runs along whichever axis has the longer span).  Pure geometry: no obstacle awareness."""
        a = self.P(a) if isinstance(a, str) else a
        b = self.P(b) if isinstance(b, str) else b
        dx, dy = b[0] - a[0], b[1] - a[1]
        sx, sy = math.copysign(1, dx), math.copysign(1, dy)
        d = min(abs(dx), abs(dy))
        if first in ('h', 'v'):
            assert (first == 'h') == (abs(dx) >= abs(dy)), \
                f'T45 {net}: first={first} but |dx|={abs(dx):.3f} |dy|={abs(dy):.3f}'
            c = (b[0] - sx * d, a[1]) if first == 'h' else (a[0], b[1] - sy * d)
        else:
            c = (a[0] + sx * d, a[1] + sy * d)
        self.routing['tracks'].append({'net': net, 'layer': layer, 'width': w,
                                       'points': [[r3(a[0]), r3(a[1])], [r3(c[0]), r3(c[1])], [r3(b[0]), r3(b[1])]],
                                       'src': self._src()})

    def V(self, net, x, y=None, d=0.45, drill=0.3):
        """A via.  A copied via ('src' copy:...) of the same net at the same spot is replaced (no stacked
        drills; the hand via's land is the smaller one)."""
        if isinstance(x, str) or (isinstance(x, tuple) and y is None):
            x, y = self.P(x) if isinstance(x, str) else x
        vias = self.routing['vias']
        vias[:] = [v for v in vias if not (v['net'] == net and str(v.get('src', '')).startswith('copy:')
                                           and math.dist(v['at'], (x, y)) < 0.01)]
        vias.append({'net': net, 'at': [r3(x), r3(y)], 'diameter': d, 'drill': drill, 'src': self._src()})

    def DROP(self, net, x0, y0, x1, y1):
        """Remove copied copper ('src' copy:...) of one net inside a box (an escape a new route replaces)."""
        def inside(p):
            return x0 <= p[0] <= x1 and y0 <= p[1] <= y1
        r = self.routing
        r['tracks'][:] = [t for t in r['tracks'] if not (t['net'] == net and str(t.get('src', '')).startswith('copy:')
                                                         and all(inside(p) for p in t['points']))]
        r['vias'][:] = [v for v in r['vias'] if not (v['net'] == net and str(v.get('src', '')).startswith('copy:')
                                                     and inside(v['at']))]

    def WIDEN(self, net, layer, x0, y0, x1, y1, w):
        """Set the width of every track of one net and layer lying wholly inside a box (current capacity).
        Geometry is unchanged; the pre-DRC checks the clearance."""
        n = 0
        for t in self.routing['tracks']:
            if t['net'] == net and t['layer'] == layer and all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in t['points']):
                t['width'] = max(t.get('width', 0.2), w)
                n += 1
        assert n, f'WIDEN {net} {layer}: nothing in the box'

    def KO(self, name, pts, layers=('In1.Cu', 'In2.Cu', 'B.Cu')):
        """A rule area forbidding tracks and vias on the given layers."""
        self.routing['keepouts'].append({'name': name, 'layers': list(layers), 'points': [list(p) for p in pts],
                                         'tracks': True})
