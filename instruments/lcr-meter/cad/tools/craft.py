"""Deterministic craft passes over the hand routes, and the checks that keep them (Rev F, 2026-10-29).

Called by cad/tools/rev_f.py after the hand routes are built; the checks run inside predrc.check() for
any board whose design.board.craft is true.  No path search: every pass edits the existing copper in place,
with fixed candidate geometries tried in order and a local clearance test (the predrc rules) for each.

Passes, in order:
  split      a track end (or polyline vertex) landing inside another segment of its net and layer splits
             that segment there, so every junction is a shared end point (no T-junction onto a segment).
  entry      a track leaving an SMD land must lie on the land centre's horizontal or vertical line (a radial
             line for a round land).  An offending end is replaced by centre -> straight stub out of the land
             along the axis nearest the route -> the rest of the route, at 45 degrees where it fits, else
             straight on from the stub end.  Exposed pads are exempt (they are planes).
  chamfer    a 90-degree corner between two segments of one net and layer becomes a 45-degree chamfer,
             cut back 3x the track width along each leg (2x, 1.5x, 1x, 0.5x if clearance fails; never more
             than 45 % of a leg).  Corners at a via or inside a land are joints, not bends, and are left.
  vias       every via grows to a 0.6 mm pad on its 0.3 mm drill where the predrc rules clear; the
             exposed-pad thermal vias keep their size.
Corners and entries that no candidate fits are listed in routing['craft_exceptions'] with the reason; the
checks flag anything else.
"""
from __future__ import annotations

import math
from collections import defaultdict

from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon, box

import predrc

Q = 0.002                       # mm: end points closer than this are one point
ON_LINE = 0.01                  # mm: a land centre within this of a segment's line is "on" it
CHAMFER_STEPS = (3.0, 2.0, 1.5, 1.0, 0.5)
VIA_PAD = 0.6


def key(p):
    return (round(p[0] / Q), round(p[1] / Q))


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


# ------------------------------------------------------------------ local clearance (the predrc rules)
class Index:
    def __init__(self, design, routing):
        self.pads, self.drills, _ = predrc.static_items(design)
        x0, y0, x1, y1 = design['board']['outline']
        self.outline = box(x0, y0, x1, y1)
        self.edge = self.outline.exterior
        self.kos = [(Polygon(k['points']), set(k['layers'])) for k in routing.get('keepouts', []) if k.get('tracks')]
        self.rebuild(routing)

    def rebuild(self, routing):
        tracks, vias = predrc.dyn_items(routing)
        self.vias = vias
        self.layer = {}
        for layer in predrc.CU:
            items = [p for p in self.pads if layer in p['layers']] + [t for t in tracks if t['layer'] == layer] + vias
            self.layer[layer] = (items, STRtree([i['geom'] for i in items]))
        self.added = []                       # (geom, net, layers) accepted since the last rebuild
        smd = [p for p in self.pads if p['smd'] and not p['exposed']]
        self.smd = (smd, STRtree([p['geom'] for p in smd]))
        self.dr = (self.drills, STRtree([d['geom'] for d in self.drills])) if self.drills else ([], None)

    def ok(self, g, net, layers, ignore=()):
        """True if copper g of net on these layers keeps every predrc rule against other-net copper."""
        if not g.within(self.outline) or g.distance(self.edge) < predrc.EDGE - predrc.EPS:
            return False
        for poly, kl in self.kos:
            if kl & set(layers) and g.intersects(poly):
                return False
        for layer in layers:
            items, tree = self.layer[layer]
            for j in tree.query(g.buffer(predrc.CLEAR)):
                o = items[int(j)]
                if o['net'] != net and id(o) not in ignore and g.distance(o['geom']) < predrc.CLEAR - predrc.EPS:
                    return False
        for ag, an, al in self.added:
            if an != net and set(al) & set(layers) and g.distance(ag) < predrc.CLEAR - predrc.EPS:
                return False
        drills, tree = self.dr
        if tree is not None:
            for j in tree.query(g.buffer(predrc.HOLE)):
                d = drills[int(j)]
                if (d['net'] is None or d['net'] != net) and g.distance(d['geom']) < predrc.HOLE - predrc.EPS:
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
                    out.append({'kind': 'tjunction', 'layer': t['layer'], 'a': t.get('src', t['net']), 'b': 'segment interior',
                                'nets': [t['net'], t['net']], 'mm': 0.0, 'at': [round(p[0], 4), round(p[1], 4)],
                                'src': t.get('src', '')})
                    break
    return out


# ------------------------------------------------------------------ pass: pad entries
AXES = ((1, 0), (-1, 0), (0, 1), (0, -1))


_LAND_TREE = {}


def lands_at(pads, net, layer, p):
    if id(pads) not in _LAND_TREE:
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
        if abs(b) < 0.005 and (pa['shape'] != 'circle' or True):
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


def angles_ok(routing, net, layer, path, skip):
    """No new inner angle under 45 degrees (predrc's angle rule) at any vertex of a candidate path."""
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
                if 0.1 <= ang < predrc.MIN_ANGLE - predrc.ANGLE_TOL:
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
                            angles_ok(routing, t['net'], t['layer'], cd, {i}):
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


def entry_checks(routing, pads, exceptions):
    allowed = {(x['net'], x['layer'], key(x['at'])) for x in exceptions if x['kind'] == 'pad_entry'}
    out = []
    for i, end, pd in entry_violations(routing, pads):
        t = routing['tracks'][i]
        p = t['points'][0] if end == 0 else t['points'][-1]
        if (t['net'], t['layer'], key(p)) in allowed:
            continue
        out.append({'kind': 'pad_entry', 'layer': t['layer'], 'a': t.get('src', t['net']), 'b': pd['who'],
                    'nets': [t['net'], t['net']], 'mm': 0.0, 'at': [round(p[0], 4), round(p[1], 4)], 'src': t.get('src', '')})
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
                for m in CHAMFER_STEPS:
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


def corner_checks(routing, pads, exceptions):
    allowed = {(x['net'], x['layer'], key(x['at'])) for x in exceptions if x['kind'] == 'corner90'}
    out = []
    for p, (i, _), (j, _) in corners(routing, pads):
        t = routing['tracks'][i]
        if (t['net'], t['layer'], key(p)) not in allowed:
            out.append({'kind': 'corner90', 'layer': t['layer'], 'a': t.get('src', t['net']),
                        'b': routing['tracks'][j].get('src', ''), 'nets': [t['net'], t['net']], 'mm': 90.0,
                        'at': [round(p[0], 4), round(p[1], 4)], 'src': t.get('src', '')})
    return out


# ------------------------------------------------------------------ pass: via pads
def thermal(v, pads):
    pt = Point(v['at'])
    return any(pd['exposed'] and pd['geom'].covers(pt) for pd in pads)


def via_fits(v, idx, d=VIA_PAD):
    g = Point(v['at']).buffer(d / 2, 16)
    me = [o for o in idx.vias if o['at'] == tuple(v['at']) and o['net'] == v['net']]
    if not idx.ok(g, v['net'], predrc.CU, ignore={id(o) for o in me}):
        return False
    smd, tree = idx.smd
    return not any(g.intersects(smd[int(j)]['geom']) for j in tree.query(g))


def grow_vias(routing, idx, deny=frozenset()):
    grown, kept = 0, 0
    for v in routing['vias']:
        if v.get('diameter', 0.6) >= VIA_PAD - 1e-9 or thermal(v, idx.pads):
            continue
        if ('via', v['net'], key(v['at'])) not in deny and via_fits(v, idx):
            v['diameter'] = VIA_PAD
            idx.accept(Point(v['at']).buffer(VIA_PAD / 2, 16), v['net'], predrc.CU)
            grown += 1
        else:
            kept += 1
    idx.rebuild(routing)
    return grown, kept


def via_checks(routing, idx):
    out = []
    for v in routing['vias']:
        if v.get('diameter', 0.6) < VIA_PAD - 1e-9 and not thermal(v, idx.pads) and via_fits(v, idx):
            out.append({'kind': 'via_ring', 'layer': 'via', 'a': v.get('src', v['net']), 'b': '0.6 mm pad fits',
                        'nets': [v['net'], v['net']], 'mm': v['diameter'], 'at': list(v['at']), 'src': v.get('src', '')})
    return out


# ------------------------------------------------------------------ driver and checks
def run(design, routing, deny=frozenset()):
    """All passes in order.  Mutates routing; returns a report dict."""
    seg_list(routing)
    n_split = split_tjunctions(routing)
    idx = Index(design, routing)
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


def checks(design, routing, pads):
    """The permanent craft rules (predrc kinds tjunction, pad_entry, corner90, via_ring)."""
    exc = routing.get('craft_exceptions', [])
    idx = Index(design, routing)
    return (tjunction_checks(routing) + entry_checks(routing, pads, exc) + corner_checks(routing, pads, exc)
            + via_checks(routing, idx))
