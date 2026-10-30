"""Board craft: deterministic geometry passes over hand routes, and the checks that keep them (2026-10-29).

Pure functions over plain data, with no board files, no pcbnew and no project globals, so the module can move
to a shared library as is.  The LCR callers (cad/tools/rev_f.py, predrc.py, pour.py, pour_report.py and
validation/power-spurs/current_check.py) do the file I/O and turn their own records into these:

  track    {net, layer, width, points: [[x, y], ...], src?}           mm, board frame (y down)
  via      {net, at: [x, y], diameter, drill, src?}
  pad      {ref, pad, net, at, size: [w, h], shape, angle, layer | layers, smd?, exposed?, outline?}
           shape rect / roundrect / circle / oval; angle in degrees, counter-clockwise as seen on the board;
           `layers` (a list) for a through-hole pad; `outline` ([[x, y], ...], board frame) overrides
           size / shape / angle when the caller has the exact land; `exposed` marks a thermal pad (a plane,
           exempt from the entry rule and allowed under vias)
  drill    {at, net (None for NPTH), diameter | outline}
  routing  {tracks, vias, keepouts?: [{layers, points, tracks}]}      keepouts with tracks False only
                                                                      forbid zone fill and are ignored here
  board    {outline: [x0, y0, x1, y1]}
  rules    dict, defaults in RULES (clearance, edge, hole, hole2hole, angle limits, via pad, chamfer steps)
Every check returns a list of violation dicts with 'kind' and a human-readable 'where'.

Passes (run() applies them in this order; each edits the copper in place, trying fixed candidate geometries
in order with a local clearance test against the rules; no path search):
  split      a track end (or polyline vertex) landing inside another segment of its net and layer splits
             that segment there, so every junction is a shared end point (no T-junction onto a segment).
  entry      a track leaving an SMD land must lie on the land centre's horizontal or vertical line (a radial
             line for a round land).  An offending end is replaced by centre -> straight stub out of the land
             along the axis nearest the route -> the rest of the route, at 45 degrees where it fits, else
             straight on from the stub end.  Exposed pads are exempt (they are planes).
  merge      two legs of one net and layer leaving a point in the same direction become one.
  chamfer    a 90-degree corner between two segments of one net and layer becomes a 45-degree chamfer,
             cut back 3x the track width along each leg (then the smaller CHAMFER_STEPS; never more than
             45 % of a leg).  Corners at a via or inside a land are joints, not bends, and are left.
  vias       every via grows to the rules' via pad (0.6 mm) on its drill where it clears; exposed-pad
             thermal vias keep their size.
  stitch     stitch_vias(): stitching vias of one net at fixed candidates (beside layer changes of chosen
             nets, rows along their runs, a grid), each kept only if it clears every rule.
Corners and entries that no candidate fits come back as exceptions; the checks flag anything else.
Checks: tjunction_checks, entry_checks, corner_checks, via_checks, angle_checks, current_checks (IPC-2152),
teardrop_checks.
"""
from __future__ import annotations

import math
from collections import defaultdict

try:                                    # KiCad's bundled Python has no shapely: only the pure-data checks
    from shapely import STRtree         # (teardrop_checks, the IPC-2152 formulas) are usable there
    from shapely.affinity import rotate as _rotate, translate as _translate
    from shapely.geometry import LineString, Point, Polygon, box
except ImportError:                     # pragma: no cover
    STRtree = None

Q = 0.002                       # mm: end points closer than this are one point
ON_LINE = 0.01                  # mm: a land centre within this of a segment's line is "on" it
RULES = {
    'layers': ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu'],
    'clearance': 0.15,          # copper to copper, other nets
    'edge': 0.3,                # copper to board edge
    'hole': 0.2,                # drill to other-net copper
    'hole2hole': 0.25,          # drill to drill, edge to edge
    'min_angle': 45.0,          # degrees, inner angle between legs at a shared end point
    'angle_tol': 0.1,           # degrees
    'angle_join': 0.002,        # mm: shorter jogs are merged before the angle rule
    'eps': 1e-4,                # mm
    'via_pad': 0.6,             # mm: grow_vias target
    'chamfer_steps': (3.0, 2.0, 1.5, 1.0, 0.5),   # x track width
}


def rules_of(rules=None):
    return dict(RULES, **(rules or {}))


def key(p):
    return (round(p[0] / Q), round(p[1] / Q))


def where(net, layer, at):
    return f'{net} {layer} ({at[0]:.3f}, {at[1]:.3f})'


def violation(kind, layer, a, b, net, mm, at, src=''):
    at = [round(at[0], 4), round(at[1], 4)]
    return {'kind': kind, 'layer': layer, 'a': a, 'b': b, 'nets': [net, net], 'mm': mm, 'at': at, 'src': src,
            'where': where(net, layer, at)}


# ------------------------------------------------------------------ plain data -> geometry
def poly(d):
    """A polygon from [[x, y], ...] or {'outer': [...], 'holes': [[...], ...]}."""
    if isinstance(d, dict):
        return Polygon(d['outer'], d.get('holes', []))
    return Polygon(d)


def plain_polys(g):
    """Shapely (Multi)Polygon -> [{'outer', 'holes'}] for passing regions as plain data."""
    parts = [g] if g.geom_type == 'Polygon' else list(g.geoms)
    return [{'outer': [list(c) for c in p.exterior.coords], 'holes': [[list(c) for c in r.coords] for r in p.interiors]}
            for p in parts if not p.is_empty]


def union_of(ds):
    from shapely.ops import unary_union
    return unary_union([poly(d) for d in ds]) if ds else Polygon()


def pad_geom(p):
    if p.get('outline'):
        return Polygon(p['outline'])
    w, h = p['size']
    s = p.get('shape', 'rect')
    if s == 'circle':
        g = Point(0, 0).buffer(w / 2, 32)
    elif s == 'oval':
        r = min(w, h) / 2
        d = max(w, h) / 2 - r
        g = (LineString([(-d, 0), (d, 0)]) if w >= h else LineString([(0, -d), (0, d)])).buffer(r, 16) \
            if d > 1e-9 else Point(0, 0).buffer(r, 32)
    elif s == 'roundrect':
        r = p.get('roundrect_ratio', 0.25) * min(w, h)
        g = box(-w / 2 + r, -h / 2 + r, w / 2 - r, h / 2 - r).buffer(r, 8) if r > 1e-9 else box(-w / 2, -h / 2, w / 2, h / 2)
    else:
        g = box(-w / 2, -h / 2, w / 2, h / 2)
    g = _rotate(g, -p.get('angle', 0.0), origin=(0, 0))      # y down: counter-clockwise on the board
    return _translate(g, *p['at'])


def prepare_pads(pads):
    """Plain pads -> internal records with geometry (idempotent)."""
    if pads and 'geom' in pads[0]:
        return pads
    out = []
    for p in pads:
        layers = p.get('layers') or ([p['layer']] if isinstance(p.get('layer'), str) else list(p.get('layer', [])))
        out.append({'geom': pad_geom(p), 'net': p['net'], 'layers': layers, 'ref': p['ref'], 'num': p['pad'],
                    'at': tuple(p['at']), 'smd': p.get('smd', True), 'exposed': p.get('exposed', False),
                    'shape': p.get('shape', 'rect'), 'who': f"{p['ref']}.{p['pad']}", 'kind': 'pad'})
    return out


def prepare_drills(drills):
    if drills and 'geom' in drills[0]:
        return drills
    return [{'geom': Polygon(d['outline']) if d.get('outline') else Point(d['at']).buffer(d['diameter'] / 2, 32),
             'net': d.get('net'), 'at': tuple(d['at']), 'who': d.get('who', 'drill')} for d in drills]


def dyn_items(routing, layers):
    """Track segments and vias with their copper geometry."""
    tracks, vias = [], []
    for i, t in enumerate(routing['tracks']):
        pts = [tuple(p) for p in t['points']]
        w = t.get('width', 0.2)
        src = t.get('src', f'tracks[{i}]')
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            tracks.append({'geom': LineString([a, b]).buffer(w / 2, 8), 'net': t['net'], 'layers': [t['layer']],
                           'layer': t['layer'], 'a': a, 'b': b, 'w': w, 'idx': i, 'src': src,
                           'who': f"{t['net']} track", 'kind': 'track'})
    for i, v in enumerate(routing['vias']):
        at = tuple(v['at'])
        vias.append({'geom': Point(at).buffer(v.get('diameter', 0.6) / 2, 16), 'net': v['net'], 'layers': layers,
                     'idx': i, 'at': at, 'd': v.get('diameter', 0.6), 'drill': v.get('drill', 0.3),
                     'src': v.get('src', f'vias[{i}]'), 'who': f"{v['net']} via", 'kind': 'via'})
    return tracks, vias


def seg_list(routing):
    """Explode polylines into two-point tracks (zero-length pieces dropped); keeps net, layer, width, src."""
    out = []
    for t in routing['tracks']:
        pts = [tuple(p) for p in t['points']]
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) >= Q:
                out.append(dict({k: v for k, v in t.items() if k != 'points'}, points=[list(a), list(b)]))
    routing['tracks'] = out


def interior(p, a, b, tol=0.003):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0 or math.dist(p, a) < tol or math.dist(p, b) < tol:
        return False
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    return 0 < t < 1 and math.dist(p, (a[0] + t * dx, a[1] + t * dy)) < tol


# ------------------------------------------------------------------ local clearance (the rules)
class Index:
    """Other-net copper, drills, keep-outs and the edge, for testing one new piece of copper at a time."""

    def __init__(self, pads, drills, board, routing, rules=None):
        self.rules = rules_of(rules)
        self.pads = prepare_pads(pads)
        self.drills = prepare_drills(drills)
        x0, y0, x1, y1 = board['outline']
        self.outline = box(x0, y0, x1, y1)
        self.edge = self.outline.exterior
        self.kos = [(Polygon(k['points']), set(k['layers'])) for k in routing.get('keepouts', []) if k.get('tracks')]
        self.rebuild(routing)

    def rebuild(self, routing):
        tracks, vias = dyn_items(routing, self.rules['layers'])
        self.vias = vias
        self.layer = {}
        for layer in self.rules['layers']:
            items = [p for p in self.pads if layer in p['layers']] + [t for t in tracks if t['layer'] == layer] + vias
            self.layer[layer] = (items, STRtree([i['geom'] for i in items]))
        self.added = []                       # (geom, net, layers) accepted since the last rebuild
        smd = [p for p in self.pads if p['smd'] and not p['exposed']]
        self.smd = (smd, STRtree([p['geom'] for p in smd]))
        self.dr = (self.drills, STRtree([d['geom'] for d in self.drills])) if self.drills else ([], None)

    def ok(self, g, net, layers, ignore=()):
        """True if copper g of net on these layers keeps every rule against other-net copper."""
        R = self.rules
        if not g.within(self.outline) or g.distance(self.edge) < R['edge'] - R['eps']:
            return False
        for poly_, kl in self.kos:
            if kl & set(layers) and g.intersects(poly_):
                return False
        for layer in layers:
            items, tree = self.layer[layer]
            for j in tree.query(g.buffer(R['clearance'])):
                o = items[int(j)]
                if o['net'] != net and id(o) not in ignore and g.distance(o['geom']) < R['clearance'] - R['eps']:
                    return False
        for ag, an, al in self.added:
            if an != net and set(al) & set(layers) and g.distance(ag) < R['clearance'] - R['eps']:
                return False
        drills, tree = self.dr
        if tree is not None:
            for j in tree.query(g.buffer(R['hole'])):
                d = drills[int(j)]
                if (d['net'] is None or d['net'] != net) and g.distance(d['geom']) < R['hole'] - R['eps']:
                    return False
        return True

    def accept(self, g, net, layers):
        self.added.append((g, net, list(layers)))


def seg_geom(a, b, w):
    return LineString([a, b]).buffer(w / 2, 8)


# ------------------------------------------------------------------ pass: T-junction split
def split_tjunctions(routing):
    """Insert every junction point into the segment it lands on.  Returns the number of splits."""
    n = 0
    while True:
        by = defaultdict(list)
        for i, t in enumerate(routing['tracks']):
            by[(t['net'], t['layer'])].append(i)
        hit = None
        for i, t in enumerate(routing['tracks']):
            for p in t['points']:
                for j in by[(t['net'], t['layer'])]:
                    if j == i:
                        continue
                    a, b = routing['tracks'][j]['points']
                    if interior(p, a, b):
                        hit = (j, p)
                        break
                if hit:
                    break
            if hit:
                break
        if not hit:
            return n
        j, p = hit
        t = routing['tracks'][j]
        a, b = t['points']
        routing['tracks'][j] = dict(t, points=[a, list(p)])
        routing['tracks'].insert(j + 1, dict(t, points=[list(p), b]))
        n += 1


def tjunction_checks(routing):
    """A track end or vertex on the interior of another segment of its net and layer."""
    by = defaultdict(list)
    for t in routing['tracks']:
        pts = t['points']
        for a, b in zip(pts, pts[1:]):
            by[(t['net'], t['layer'])].append((tuple(a), tuple(b)))
    out = []
    for t in routing['tracks']:
        for p in t['points']:
            for a, b in by[(t['net'], t['layer'])]:
                if interior(tuple(p), a, b):
                    out.append(violation('tjunction', t['layer'], t.get('src', t['net']), 'segment interior', t['net'],
                                         0.0, p, t.get('src', '')))
                    break
    return out


# ------------------------------------------------------------------ pass: pad entries
AXES = ((1, 0), (-1, 0), (0, 1), (0, -1))
_LAND_TREE = {}


def lands_at(pads, net, layer, p):
    if id(pads) not in _LAND_TREE or _LAND_TREE[id(pads)][2] is not pads:
        smd = [pd for pd in pads if pd['smd'] and not pd['exposed']]
        _LAND_TREE.clear()
        _LAND_TREE[id(pads)] = (smd, STRtree([pd['geom'] for pd in smd]), pads)
    smd, tree, _ = _LAND_TREE[id(pads)]
    pt = Point(p)
    return [smd[int(j)] for j in tree.query(pt) if smd[int(j)]['net'] == net and layer in smd[int(j)]['layers']
            and smd[int(j)]['geom'].covers(pt)]


def entry_ok(pd, p, o):
    c = pd['at']
    if math.dist(p, o) < Q:
        return True
    # distance from the land centre to the infinite line through p, o
    (x1, y1), (x2, y2) = p, o
    dist = abs((x2 - x1) * (y1 - c[1]) - (x1 - c[0]) * (y2 - y1)) / math.dist(p, o)
    if pd['shape'] == 'circle':
        return dist <= ON_LINE
    horiz, vert = abs(y2 - y1) <= Q, abs(x2 - x1) <= Q
    return (horiz or vert) and dist <= ON_LINE


def entry_violations(routing, pads):
    """(track index, end index 0/1, land) for every offending land entry."""
    out = []
    for i, t in enumerate(routing['tracks']):
        a, b = (tuple(t['points'][0]), tuple(t['points'][-1]))
        for end, (p, o) in enumerate(((a, b), (b, a))):
            for pd in lands_at(pads, t['net'], t['layer'], p):
                if pd['geom'].covers(Point(o)):
                    continue                          # a segment inside its own land
                if not entry_ok(pd, p, o):
                    out.append((i, end, pd))
    return out


def extents(pd):
    c = pd['at']
    x0, y0, x1, y1 = pd['geom'].bounds
    return {(1, 0): x1 - c[0], (-1, 0): c[0] - x0, (0, 1): y1 - c[1], (0, -1): c[1] - y0}


def outside(pd, q):
    return not pd['geom'].buffer(0.01).covers(Point(q))


def land_to_land(pa, pb):
    """Centre-to-centre paths between two lands of one net: straight, a 45-degree jog in the gap, or an L
    (whose corner the chamfer pass then cuts)."""
    ca, cb = pa['at'], pb['at']
    v = (cb[0] - ca[0], cb[1] - ca[1])
    out = []
    for u in sorted(AXES, key=lambda u: -(u[0] * v[0] + u[1] * v[1]))[:2]:
        a = u[0] * v[0] + u[1] * v[1]
        b = -u[1] * v[0] + u[0] * v[1]
        n = (-u[1], u[0])
        gap = a - extents(pa)[u] - extents(pb)[(-u[0], -u[1])]
        if a <= 0:
            continue
        if abs(b) < 0.005:
            out.append([ca, cb])
        elif gap >= abs(b) + 0.04:
            t = extents(pa)[u] + (gap - abs(b)) / 2
            s1 = (ca[0] + t * u[0], ca[1] + t * u[1])
            s2 = (s1[0] + abs(b) * u[0] + b * n[0], s1[1] + abs(b) * u[1] + b * n[1])
            out.append([ca, s1, s2, cb])
        q = (ca[0] + a * u[0], ca[1] + a * u[1])          # L corner on A's line, B's perpendicular
        if outside(pa, q) and outside(pb, q) and abs(b) >= 0.005:
            out.append([ca, q, cb])
    return [[(round(x, 4), round(y, 4)) for x, y in cd] for cd in out]


def entry_candidates(pd, o, po=None):
    if po is not None:
        return land_to_land(pd, po)
    c = pd['at']
    v = (o[0] - c[0], o[1] - c[1])
    if pd['shape'] == 'circle':
        return [[c, o]]
    ext = extents(pd)
    cands = []
    for u in sorted(AXES, key=lambda u: -(u[0] * v[0] + u[1] * v[1]))[:2]:
        a = u[0] * v[0] + u[1] * v[1]
        b = -u[1] * v[0] + u[0] * v[1]
        e = ext[u]
        if a <= e:
            continue
        if abs(b) < 0.005:
            cands.append([c, o])
            continue
        d = a - abs(b)
        if d >= e + 0.02:
            cands.append([c, (c[0] + d * u[0], c[1] + d * u[1]), o])
    for u in sorted(AXES, key=lambda u: -(u[0] * v[0] + u[1] * v[1]))[:1]:
        a = u[0] * v[0] + u[1] * v[1]
        e = ext[u]
        d = e + 0.05
        if a > d + 0.05:
            cands.append([c, (c[0] + d * u[0], c[1] + d * u[1]), o])
    return [[(round(x, 4), round(y, 4)) for x, y in cd] for cd in cands]


def legs_at(routing, net, layer, q, skip):
    out = []
    for k, t in enumerate(routing['tracks']):
        if k in skip or t['net'] != net or t['layer'] != layer:
            continue
        a, b = t['points']
        if key(a) == key(q):
            out.append(tuple(b))
        elif key(b) == key(q):
            out.append(tuple(a))
    return out


def angles_ok(routing, net, layer, path, skip, rules=None):
    """No new inner angle under the rules' minimum at any vertex of a candidate path."""
    R = rules_of(rules)
    for n, q in enumerate(path):
        legs = legs_at(routing, net, layer, q, skip)
        if n > 0:
            legs.append(tuple(path[n - 1]))
        if n < len(path) - 1:
            legs.append(tuple(path[n + 1]))
        for x in range(len(legs)):
            for y in range(x + 1, len(legs)):
                du = (legs[x][0] - q[0], legs[x][1] - q[1])
                dv = (legs[y][0] - q[0], legs[y][1] - q[1])
                nu, nv = math.hypot(*du), math.hypot(*dv)
                if nu < Q or nv < Q:
                    continue
                c = (du[0] * dv[0] + du[1] * dv[1]) / (nu * nv)
                ang = math.degrees(math.acos(max(-1.0, min(1.0, c))))
                if 0.1 <= ang < R['min_angle'] - R['angle_tol']:
                    return False        # (a collinear overlap, ~0 degrees, is merged by merge_overlaps)
    return True


def fix_entries(routing, idx, deny=frozenset()):
    """Replace offending land entries.  Returns (fixed, exceptions)."""
    fixed, exc = 0, []
    for _ in range(8):
        viol = entry_violations(routing, idx.pads)
        if not viol:
            break
        done, touched, deferred = set(), set(), False
        new_tracks = list(routing['tracks'])
        for i, end, pd in viol:
            if i in done:
                continue
            t = routing['tracks'][i]
            p, o = (t['points'][0], t['points'][1]) if end == 0 else (t['points'][1], t['points'][0])
            if {key(p), key(o), key(pd['at'])} & touched:
                deferred = True             # a neighbour changed here this round: decide on the new state
                continue
            tag = ('entry', t['net'], t['layer'], key(p))
            ok = None
            po = [x for x in lands_at(idx.pads, t['net'], t['layer'], tuple(o)) if x is not pd]
            if tag not in deny:
                for cd in entry_candidates(pd, tuple(o), po[0] if po else None):
                    geoms = [seg_geom(a, b, t['width']) for a, b in zip(cd, cd[1:]) if math.dist(a, b) >= Q]
                    if all(idx.ok(g, t['net'], [t['layer']]) for g in geoms) and \
                            angles_ok(routing, t['net'], t['layer'], cd, {i}, idx.rules):
                        ok = cd
                        break
            if ok is None:
                exc.append({'kind': 'pad_entry', 'net': t['net'], 'layer': t['layer'], 'land': pd['who'],
                            'at': [round(p[0], 4), round(p[1], 4)],
                            'why': 'no straight stub out of the land clears' if tag not in deny else 'reverted: final pre-DRC'})
                continue
            done.add(i)
            touched |= {key(q) for q in ok} | {key(p), key(o)}
            for a, b in zip(ok, ok[1:]):
                idx.accept(seg_geom(a, b, t['width']), t['net'], [t['layer']])
            pieces = [dict(t, points=[list(a), list(b)], src=f"{t.get('src', '')} +entry")
                      for a, b in zip(ok, ok[1:]) if math.dist(a, b) >= Q]
            new_tracks[i] = pieces
            fixed += 1
        routing['tracks'] = [x for item in new_tracks for x in (item if isinstance(item, list) else [item])]
        idx.rebuild(routing)
        if not done and not deferred:
            break
    # exceptions are only those still offending at the end
    left = {(t['net'], t['layer'], key(t['points'][e])) for i, e, _ in entry_violations(routing, idx.pads)
            for t in [routing['tracks'][i]]}
    exc = [x for x in exc if (x['net'], x['layer'], key(x['at'])) in left]
    uniq = {(x['net'], x['layer'], key(x['at'])): x for x in exc}
    return fixed, list(uniq.values())


def entry_checks(routing, pads, exceptions=()):
    """A track leaving an SMD land off the land centre's axis (radial for a round land)."""
    pads = prepare_pads(pads)
    allowed = {(x['net'], x['layer'], key(x['at'])) for x in exceptions if x['kind'] == 'pad_entry'}
    out = []
    for i, end, pd in entry_violations(routing, pads):
        t = routing['tracks'][i]
        p = t['points'][0] if end == 0 else t['points'][-1]
        if (t['net'], t['layer'], key(p)) in allowed:
            continue
        out.append(violation('pad_entry', t['layer'], t.get('src', t['net']), pd['who'], t['net'], 0.0, p,
                             t.get('src', '')))
    return out


# ------------------------------------------------------------------ pass: merge overlapping collinear legs
def merge_overlaps(routing):
    """Two legs of one net and layer leaving a point in the same direction (a stub laid over a route):
    the shorter goes, and the longer is split at its far end, which keeps the copper and the junction."""
    n = 0
    while True:
        ends = defaultdict(list)
        for i, t in enumerate(routing['tracks']):
            for e in (0, 1):
                ends[(t['net'], t['layer'], key(t['points'][e]))].append((i, e))
        hit = None
        for legs in ends.values():
            for x in range(len(legs)):
                for y in range(len(legs)):
                    (i, ei), (j, ej) = legs[x], legs[y]
                    if i == j:
                        continue
                    ti, tj = routing['tracks'][i], routing['tracks'][j]
                    p, a, b = tuple(ti['points'][ei]), tuple(ti['points'][1 - ei]), tuple(tj['points'][1 - ej])
                    if math.dist(p, a) <= math.dist(p, b) and (interior(a, p, b) or key(a) == key(b)):
                        hit = (i, j, p, a, b)
                        break
                if hit:
                    break
            if hit:
                break
        if not hit:
            return n
        i, j, p, a, b = hit
        ti, tj = routing['tracks'][i], routing['tracks'][j]
        w = max(ti['width'], tj['width'])
        keep = [x for k, x in enumerate(routing['tracks']) if k not in (i, j)]
        if key(a) == key(b):
            keep.append(dict(tj, width=w))                       # a duplicate segment
        else:
            # the overlapped part (p -> a) takes the wider width; the rest (a -> b) keeps the route's width
            keep.append(dict(tj, width=w, points=[list(p), list(a)]))
            keep.append(dict(tj, points=[list(a), list(b)]))
        routing['tracks'] = keep
        n += 1


# ------------------------------------------------------------------ pass: chamfer 90-degree corners
def corners(routing, pads):
    """[(point, (i, end_i), (j, end_j))] for two-leg 90-degree corners that are bends (not joints)."""
    ends = defaultdict(list)
    for i, t in enumerate(routing['tracks']):
        for e in (0, 1):
            ends[(t['net'], t['layer'], key(t['points'][e]))].append((i, e))
    vias = {(v['net'], key(v['at'])) for v in routing['vias']}
    out = []
    for (net, layer, k), legs in ends.items():
        if len(legs) != 2 or (net, k) in vias:
            continue
        (i, ei), (j, ej) = legs
        ti, tj = routing['tracks'][i], routing['tracks'][j]
        p = tuple(ti['points'][ei])
        u, v = tuple(ti['points'][1 - ei]), tuple(tj['points'][1 - ej])
        du, dv = (u[0] - p[0], u[1] - p[1]), (v[0] - p[0], v[1] - p[1])
        c = (du[0] * dv[0] + du[1] * dv[1]) / (math.hypot(*du) * math.hypot(*dv))
        if abs(math.degrees(math.acos(max(-1.0, min(1.0, c)))) - 90) > 0.5:
            continue
        pt = Point(p)
        if any(pd['net'] == net and layer in pd['layers'] and pd['geom'].covers(pt) for pd in pads):
            continue
        out.append((p, (i, ei), (j, ej)))
    return out


def chamfer(routing, idx, deny=frozenset()):
    done, exc = 0, []
    for _ in range(4):                # a chamfer can expose the next corner on a shortened leg; repeat
        cs = corners(routing, idx.pads)
        changed = False
        for p, (i, ei), (j, ej) in cs:
            ti, tj = routing['tracks'][i], routing['tracks'][j]
            if tuple(ti['points'][ei]) != p or tuple(tj['points'][ej]) != p:
                continue                      # this corner moved earlier in the loop
            tag = ('chamfer', ti['net'], ti['layer'], key(p))
            u, v = tuple(ti['points'][1 - ei]), tuple(tj['points'][1 - ej])
            lu, lv = math.dist(p, u), math.dist(p, v)
            w = min(ti['width'], tj['width'])
            ok = None
            if tag not in deny:
                for m in idx.rules['chamfer_steps']:
                    cut = min(m * max(ti['width'], tj['width']), 0.45 * lu, 0.45 * lv)
                    if cut < 0.05:
                        break
                    a = (round(p[0] + (u[0] - p[0]) * cut / lu, 4), round(p[1] + (u[1] - p[1]) * cut / lu, 4))
                    b = (round(p[0] + (v[0] - p[0]) * cut / lv, 4), round(p[1] + (v[1] - p[1]) * cut / lv, 4))
                    g = seg_geom(a, b, w)
                    if lands_at(idx.pads, ti['net'], ti['layer'], a) or lands_at(idx.pads, ti['net'], ti['layer'], b):
                        continue                  # a chamfer end inside a land would be an off-axis entry
                    if idx.ok(g, ti['net'], [ti['layer']]):
                        ok = (a, b)
                        break
            if ok is None:
                exc.append({'kind': 'corner90', 'net': ti['net'], 'layer': ti['layer'], 'at': [round(p[0], 4), round(p[1], 4)],
                            'why': 'no chamfer >= 0.5x width clears' if tag not in deny else 'reverted: final pre-DRC'})
                continue
            a, b = ok
            idx.accept(seg_geom(a, b, w), ti['net'], [ti['layer']])
            ti['points'][ei] = list(a)
            tj['points'][ej] = list(b)
            routing['tracks'].append({'net': ti['net'], 'layer': ti['layer'], 'width': w, 'points': [list(a), list(b)],
                                      'src': f"{ti.get('src', '')} +chamfer"})
            done += 1
            changed = True
        idx.rebuild(routing)
        if not changed:
            break
    left = {(ti['net'], ti['layer'], key(p)) for p, (i, _), _ in corners(routing, idx.pads)
            for ti in [routing['tracks'][i]]}
    uniq = {(x['net'], x['layer'], key(x['at'])): x for x in exc if (x['net'], x['layer'], key(x['at'])) in left}
    return done, list(uniq.values())


def corner_checks(routing, pads, exceptions=()):
    """A 90-degree bend between two segments of one net and layer (not at a via, not inside a land)."""
    pads = prepare_pads(pads)
    allowed = {(x['net'], x['layer'], key(x['at'])) for x in exceptions if x['kind'] == 'corner90'}
    out = []
    for p, (i, _), (j, _) in corners(routing, pads):
        t = routing['tracks'][i]
        if (t['net'], t['layer'], key(p)) not in allowed:
            out.append(violation('corner90', t['layer'], t.get('src', t['net']), routing['tracks'][j].get('src', ''),
                                 t['net'], 90.0, p, t.get('src', '')))
    return out


# ------------------------------------------------------------------ pass: via pads
def thermal(v, pads):
    pt = Point(v['at'])
    return any(pd['exposed'] and pd['geom'].covers(pt) for pd in pads)


def via_fits(v, idx, d=None):
    d = d or idx.rules['via_pad']
    g = Point(v['at']).buffer(d / 2, 16)
    me = [o for o in idx.vias if o['at'] == tuple(v['at']) and o['net'] == v['net']]
    if not idx.ok(g, v['net'], idx.rules['layers'], ignore={id(o) for o in me}):
        return False
    smd, tree = idx.smd
    return not any(g.intersects(smd[int(j)]['geom']) for j in tree.query(g))


def grow_vias(routing, idx, deny=frozenset()):
    pad = idx.rules['via_pad']
    grown, kept = 0, 0
    for v in routing['vias']:
        if v.get('diameter', 0.6) >= pad - 1e-9 or thermal(v, idx.pads):
            continue
        if ('via', v['net'], key(v['at'])) not in deny and via_fits(v, idx):
            v['diameter'] = pad
            idx.accept(Point(v['at']).buffer(pad / 2, 16), v['net'], idx.rules['layers'])
            grown += 1
        else:
            kept += 1
    idx.rebuild(routing)
    return grown, kept


def via_checks(routing, idx):
    """A via under the rules' via pad that would clear at that size (not an exposed-pad thermal via)."""
    pad = idx.rules['via_pad']
    out = []
    for v in routing['vias']:
        if v.get('diameter', 0.6) < pad - 1e-9 and not thermal(v, idx.pads) and via_fits(v, idx):
            out.append(dict(violation('via_ring', 'via', v.get('src', v['net']), f'{pad} mm pad fits', v['net'],
                                      v['diameter'], v['at'], v.get('src', '')), at=list(v['at'])))
    return out


# ------------------------------------------------------------------ check: acute angles and fold-backs
def angle_checks(routing, rules=None):
    """Two segments of one net and layer meeting at a shared end point with an inner angle under the
    minimum (an acid trap), or folding back (0 degrees).  Sub-`angle_join` jogs are merged first."""
    R = rules_of(rules)
    J = R['angle_join']
    q = lambda p: (round(p[0] / J), round(p[1] / J))
    ends = defaultdict(list)
    for i, t in enumerate(routing['tracks']):
        src = t.get('src', f'tracks[{i}]')
        pts = [tuple(p) for p in t['points']]
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) < J:
                continue            # a sub-micron jog: its two neighbours meet at the merged point
            ends[(t['net'], t['layer'], q(a))].append((a, b, src))
            ends[(t['net'], t['layer'], q(b))].append((b, a, src))
    out = []
    for (net, layer, _), legs in ends.items():
        for x in range(len(legs)):
            for y in range(x + 1, len(legs)):
                (p, u, s1), (_, v, s2) = legs[x], legs[y]
                du, dv = (u[0] - p[0], u[1] - p[1]), (v[0] - p[0], v[1] - p[1])
                c = (du[0] * dv[0] + du[1] * dv[1]) / (math.hypot(*du) * math.hypot(*dv))
                ang = math.degrees(math.acos(max(-1.0, min(1.0, c))))
                if ang < R['min_angle'] - R['angle_tol']:
                    out.append(violation('angle', layer, s1, s2, net, round(ang, 2), p, s1))
    return out


# ------------------------------------------------------------------ driver and checks
def run(routing, pads, drills, board, rules=None, deny=frozenset()):
    """All passes in order.  Mutates routing (tracks, vias, craft_exceptions); returns a report dict."""
    seg_list(routing)
    n_split = split_tjunctions(routing)
    idx = Index(pads, drills, board, routing, rules)
    n_entry, x_entry = fix_entries(routing, idx, deny)
    n_merge = merge_overlaps(routing)
    n_split += split_tjunctions(routing)
    idx.rebuild(routing)
    n_ch, x_ch = chamfer(routing, idx, deny)
    n_split += split_tjunctions(routing)
    idx.rebuild(routing)
    grown, kept = grow_vias(routing, idx, deny)
    routing['craft_exceptions'] = sorted(x_entry + x_ch, key=lambda x: (x['kind'], x['net'], x['at']))
    return {'tjunction_splits': n_split, 'overlaps_merged': n_merge, 'entries_fixed': n_entry, 'entry_exceptions': len(x_entry),
            'chamfers': n_ch, 'corner_exceptions': len(x_ch), 'vias_grown': grown, 'vias_kept_small': kept}


def checks(routing, pads, drills, board, rules=None):
    """The permanent craft rules: tjunction, pad_entry, corner90, via_ring (listed exceptions allowed)."""
    exc = routing.get('craft_exceptions', [])
    idx = Index(pads, drills, board, routing, rules)
    return (tjunction_checks(routing) + entry_checks(routing, idx.pads, exc) + corner_checks(routing, idx.pads, exc)
            + via_checks(routing, idx))


# ------------------------------------------------------------------ stitching vias
STITCH = {'net': 'GND', 'diameter': 0.6, 'drill': 0.3, 'inset': 0.6, 'follow_nets': (), 'row_layers': (),
          'ring_radii': (0.95, 1.2, 1.5), 'ring_step_deg': 45, 'row_offset': 0.9, 'row_pitch': 3.0,
          'grid_pitch': 5.5, 'grid_nudge': 0.6, 'drill_margin': 0.05}


def stitch_vias(routing, pads, drills, board, region, avoid=(), plan=None, rules=None):
    """Stitching vias of plan['net'], appended to routing['vias'].  Candidates in order:
      1. beside every via of plan['follow_nets'], the first clear spot on rings of ring_radii;
      2. rows ROW_OFFSET from the centre line of their plan['row_layers'] segments, every row_pitch;
      3. a grid_pitch grid over the board (centre, then four grid_nudge offsets).
    A candidate is kept only if its pad lies inside `region` shrunk by `inset`, misses every `avoid` polygon
    and every SMD land, clears the rules (Index.ok) and keeps drill_margin over hole-to-hole from every
    via.  region / avoid: polygons as [[x, y], ...] or {'outer', 'holes'}.  Returns counts."""
    P = dict(STITCH, **(plan or {}))
    idx = Index(pads, drills, board, routing, rules)
    R = idx.rules
    area = union_of(region).buffer(-P['inset'])
    av = union_of(list(avoid))
    d, dr, net = P['diameter'], P['drill'], P['net']

    def try_via(x, y):
        x, y = round(x, 3), round(y, 3)
        g = Point(x, y).buffer(d / 2, 16)
        if not area.contains(g) or g.intersects(av):
            return False
        if not idx.ok(g, net, R['layers']):
            return False
        smd, tree = idx.smd
        if any(g.intersects(smd[int(j)]['geom']) for j in tree.query(g)):
            return False
        for v in routing['vias']:
            if math.dist(v['at'], (x, y)) < v.get('drill', dr) / 2 + dr / 2 + R['hole2hole'] + P['drill_margin']:
                return False
        routing['vias'].append({'net': net, 'at': [x, y], 'diameter': d, 'drill': dr})
        idx.accept(g, net, R['layers'])
        return True

    n_lc = n_row = n_grid = 0
    ring = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for r in P['ring_radii']
            for a in range(0, 360, P['ring_step_deg'])]
    for v in [v for v in routing['vias'] if v['net'] in P['follow_nets']]:
        for dx, dy in ring:
            if try_via(v['at'][0] + dx, v['at'][1] + dy):
                n_lc += 1
                break
    pitch = P['row_pitch']
    for t in [t for t in routing['tracks'] if t['net'] in P['follow_nets'] and t['layer'] in P['row_layers']]:
        a, b = t['points']
        L = math.dist(a, b)
        if L < pitch:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        off = t['width'] / 2 + P['row_offset']
        for k in range(1, int(L // pitch) + 1):
            cx, cy = a[0] + ux * k * pitch - ux * pitch / 2, a[1] + uy * k * pitch - uy * pitch / 2
            for sgn in (1, -1):
                if try_via(cx - uy * off * sgn, cy + ux * off * sgn):
                    n_row += 1
    x0, y0, x1, y1 = board['outline']
    G, m = P['grid_pitch'], P['grid_nudge']
    gx = x0 + G / 2
    while gx < x1:
        gy = y0 + G / 2
        while gy < y1:
            for dx, dy in ((0, 0), (m, 0), (-m, 0), (0, m), (0, -m)):
                if try_via(gx + dx, gy + dy):
                    n_grid += 1
                    break
            gy += G
        gx += G
    return {'stitch_layer_change': n_lc, 'stitch_rows': n_row, 'stitch_grid': n_grid}


# ------------------------------------------------------------------ IPC-2152 current check
MIL2_PER_MM2 = 1 / 0.0254 ** 2
CURRENT = {'rise_c': 10.0, 'copper_mm': {'F.Cu': 0.035, 'In1.Cu': 0.0152, 'In2.Cu': 0.0152, 'B.Cu': 0.035},
           'stack': ('F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu'), 'via_plating_mm': 0.018, 'board_mm': 1.6, 'rho': 1.72e-8 * (1 + 0.0039 * 40), 'link': 1e-6,
           'land_neck': 0.35}


def ipc2152_area_mil2(i, dt):
    """IPC-2152 generic chart (Figure 5-2) through the smps.us least-squares fit: cross-section in mil^2
    for i A at a dt C rise."""
    return (117.555 * dt ** -0.913 + 1.15) * i ** (0.84 * dt ** -0.108 + 1.159)


def ipc2152_width_mm(i, t_mm, dt):
    return ipc2152_area_mil2(i, dt) / MIL2_PER_MM2 / t_mm


def ipc2152_via_amps(drill, plating_mm, dt):
    a = math.pi * drill * plating_mm * MIL2_PER_MM2
    return (a / (117.555 * dt ** -0.913 + 1.15)) ** (1 / (0.84 * dt ** -0.108 + 1.159))


def current_checks(net, routing, pads, sources, loads, i_max, rules=None):
    """One supply net against its worst-case current, as a resistor network solved per fault case.

    sources: [(ref, pad)] lands, each a separate case (a source part's pins are one node);
    loads:   [(ref, amps)] parts that could draw a fault current (every pin of a part tied together).
    Segments are rho L / (w t), vias plated barrels, lands near-zero links to the copper they touch; a track
    crossing a land and a via on a segment's interior are joined there.  A segment or via is charged the
    largest current it carries in any (source, load) case, capped at i_max, and must meet the IPC-2152 width
    (or run less than land_neck outside its lands) / via capacity.  Returns {'segments', 'vias',
    'violations', 'unjoined', 'singular'}."""
    import numpy as np
    C = dict(CURRENT, **(rules or {}))
    T_MM, RHO, LINK, dt = C['copper_mm'], C['rho'], C['link'], C['rise_c']
    pads = prepare_pads(pads)
    k3 = lambda layer, p: (layer, round(p[0], 3), round(p[1], 3))
    edges, segs = [], []
    npads = [p for p in pads if p['net'] == net]
    raw = []
    for t in routing['tracks']:
        if t['net'] != net:
            continue
        for a, b in zip(t['points'], t['points'][1:]):
            raw.append((t, tuple(a), tuple(b)))
    for p in npads:                     # a track running across a land is joined to it where it crosses
        hit = []
        for k, (t, a, b) in enumerate(raw):
            if t['layer'] in p['layers'] and p['geom'].intersects(LineString([a, b])) and not (
                    p['geom'].covers(Point(a)) or p['geom'].covers(Point(b))):
                hit.append(k)
        for k in reversed(hit):
            t, a, b = raw[k]
            c = LineString([a, b]).interpolate(LineString([a, b]).project(Point(p['at'])))
            raw[k:k + 1] = [(t, a, (c.x, c.y)), (t, (c.x, c.y), b)]
    vias = [v for v in routing['vias'] if v['net'] == net]
    for v in vias:                      # a via on a segment's interior is joined there
        c0 = Point(v['at'])
        for k in range(len(raw) - 1, -1, -1):
            t, a, b = raw[k]
            ln = LineString([a, b])
            if ln.distance(c0) < v['diameter'] / 2 and math.dist(a, v['at']) > v['diameter'] / 2 \
                    and math.dist(b, v['at']) > v['diameter'] / 2:
                c = ln.interpolate(ln.project(c0))
                raw[k:k + 1] = [(t, a, (c.x, c.y)), (t, (c.x, c.y), b)]
    for t, a, b in raw:
        ohm = RHO * math.dist(a, b) * 1e-3 / (t['width'] * 1e-3 * T_MM[t['layer']] * 1e-3) + 1e-9
        edges.append((k3(t['layer'], a), k3(t['layer'], b), ohm, ('seg', len(segs))))
        segs.append((t['layer'], tuple(a), tuple(b), t['width']))
    pts = {n for e in edges for n in e[:2]}
    stack = list(C['stack'])
    for k, v in enumerate(vias):
        g = Point(v['at']).buffer(v['diameter'] / 2)
        barrel = RHO * C['board_mm'] * 1e-3 / (math.pi * v['drill'] * C['via_plating_mm'] * 1e-6) / (len(stack) - 1)
        chain = [('vianode', k, l) for l in stack]
        for x, y in zip(chain, chain[1:]):
            edges.append((x, y, barrel, ('via', k)))
        for n in pts:
            if g.covers(Point(n[1], n[2])):
                edges.append((('vianode', k, n[0]), n, LINK, None))
    for p in npads:
        pn = ('pad', p['ref'], p['num'])
        for n in pts:
            if n[0] in p['layers'] and p['geom'].buffer(0.001).covers(Point(n[1], n[2])):
                edges.append((pn, n, LINK, None))
        for k, v in enumerate(vias):
            if p['geom'].intersects(Point(v['at']).buffer(v['diameter'] / 2)):
                for l in p['layers']:
                    edges.append((pn, ('vianode', k, l), LINK, None))
    by_ref = defaultdict(list)
    for p in npads:
        by_ref[p['ref']].append(('pad', p['ref'], p['num']))
    for ref, pl in by_ref.items():          # pins of one part are one node inside the part
        for x in pl[1:]:
            edges.append((pl[0], x, LINK, None))
    nodes = sorted({n for e in edges for n in e[:2]}, key=str)
    ix = {n: i for i, n in enumerate(nodes)}
    Y = np.zeros((len(nodes), len(nodes)))
    for a, b, ohm, _ in edges:
        g = 1 / ohm
        i, j = ix[a], ix[b]
        Y[i, i] += g; Y[j, j] += g; Y[i, j] -= g; Y[j, i] -= g
    unjoined, cases = [], []
    for ref, amps in loads:
        if not by_ref.get(ref) or by_ref[ref][0] not in ix:
            unjoined.append(ref)
            continue
        cases.append((by_ref[ref][0], amps))
    seg_i, via_i = np.zeros(len(segs)), np.zeros(len(vias))
    singular = False
    for sref, spad in sources:
        src = ('pad', sref, spad)
        if src not in ix:
            unjoined.append(f'{sref}.{spad}')
            continue
        for ld, amps in cases:
            s, d = ix[src], ix[ld]
            keep = [k for k in range(len(nodes)) if k != d]       # ground the load node
            J = np.zeros(len(nodes)); J[s] = amps
            try:
                V = np.zeros(len(nodes))
                V[keep] = np.linalg.solve(Y[np.ix_(keep, keep)] + np.eye(len(keep)) * 1e-12, J[keep])
            except np.linalg.LinAlgError:
                singular = True
                continue
            for a, b, ohm, tag in edges:
                if tag is None:
                    continue
                cur = abs(V[ix[a]] - V[ix[b]]) / ohm
                if tag[0] == 'seg':
                    seg_i[tag[1]] = max(seg_i[tag[1]], cur)
                else:
                    via_i[tag[1]] = max(via_i[tag[1]], cur)
    lands = {}
    for p in npads:
        for l in p['layers']:
            lands.setdefault(l, []).append(p['geom'])
    rows, vrows, viol = [], [], []
    for n, (layer, a, b, w) in enumerate(segs):
        i = float(min(seg_i[n], i_max))
        need = ipc2152_width_mm(i, T_MM[layer], dt) if i > 1e-6 else 0.0
        out_len = LineString([a, b]).length
        for g in lands.get(layer, []):
            out_len -= LineString([a, b]).intersection(g).length
        ok = w >= need - 1e-6 or out_len < C['land_neck']
        rows.append({'net': net, 'layer': layer, 'from': [round(a[0], 3), round(a[1], 3)],
                     'to': [round(b[0], 3), round(b[1], 3)], 'width_mm': w, 'current_a': round(i, 4),
                     'need_mm': round(need, 3), 'status': 'PASS' if ok else 'FAIL'})
        if not ok:
            viol.append(violation('current', layer, f'{w} mm track', f'needs {need:.3f} mm at {i:.3f} A', net,
                                  round(need, 3), a))
    for k, v in enumerate(vias):
        i = float(min(via_i[k], i_max))
        cap = ipc2152_via_amps(v['drill'], C['via_plating_mm'], dt)
        ok = i <= cap + 1e-9
        vrows.append({'net': net, 'at': v['at'], 'drill_mm': v['drill'], 'current_a': round(i, 4),
                      'capacity_a': round(cap, 3), 'status': 'PASS' if ok else 'FAIL'})
        if not ok:
            viol.append(violation('current', 'via', f"{v['drill']} mm via", f'carries {cap:.3f} A, needs {i:.3f} A',
                                  net, round(i, 3), v['at']))
    return {'segments': rows, 'vias': vrows, 'violations': viol, 'unjoined': unjoined, 'singular': singular}


# ------------------------------------------------------------------ teardrops
def teardrop_checks(items):
    """items: [{'where', 'enabled'}] for every via and pad; a via or pad with teardrops disabled fails.
    (Whether the CAD tool could fit one is its own rule: no teardrop on a track wider than the land, etc.)"""
    return [{'kind': 'teardrop', 'where': it['where'] if isinstance(it['where'], str) else
             ' '.join(f'{k} {v}' for k, v in it['where'].items()), 'enabled': False}
            for it in items if not it['enabled']]
