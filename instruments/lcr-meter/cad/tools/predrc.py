"""Fast pre-DRC for hand routing: clearance, keepouts, edge, holes, via-on-land and connectivity, no KiCad.

python3 cad/tools/predrc.py [--design D.json] [--routing R.json] [--render all|block,...] [--out DIR]

It reads the placement (design.json), the hand routes (routing.json) and the footprint geometry dumped
once by cad/tools/pad_library.py, and checks with shapely what KiCad's DRC would flag on the copper:
  clearance   copper of different nets on one layer closer than 0.15 mm (pads, tracks, vias)
  edge        copper closer than 0.3 mm to the board outline
  hole        a drill closer than 0.2 mm to other-net copper; drills closer than 0.25 mm edge to edge
  keepout     a track or via inside a rule area on that layer (tracks and vias are both forbidden)
  via_land    a via ring on an SMD land other than the five exposed-pad thermal sets (audit_dfm rule)
  width       track < 0.15 mm, via < 0.45 mm, drill < 0.3 mm
  courtyard   F.CrtYd overlap between footprints
  unconnected pads of one net in more than one copper island (union-find over pads, track anchors,
              vias; In1.Cu is the GND plane, so GND vias and GND through-hole pads join it)
  dangling    a via joining copper on fewer than two layers (a GND via in the In1 plane is joined), or
              a track end touching no other item of its net (KiCad's via_dangling / track_dangling)
It is a fast screen, not a sign-off: the KiCad rebuild and DRC run at block and commit boundaries.
Silkscreen, solder-mask bridges, zone-fill islands and schematic parity are KiCad-only.
Calibration (--kicad DRC.json prints both tallies): Rev E 48b012771 gives 0/0 in both; the first Rev F
placement gives the same clearance 9, courtyard 12, edge 3, PTH-in-courtyard 2 and unconnected 209
in both, KiCad's one extra dangling via being a GND via on an In1 fill island.

The static part (pads, courtyards, pad-pad and courtyard checks) is cached in build/predrc-cache.pkl,
keyed on a hash of the placement and the pad library.  Tracks and vias may carry a 'src' key (the
rev_f_routes.py line that made them); violations quote it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

from shapely import STRtree
from shapely.affinity import rotate as srotate, translate
from shapely.geometry import LineString, Point, Polygon, box

CAD = Path(__file__).resolve().parents[1]
LIB = json.loads((CAD / 'tools' / 'pad_library.json').read_text())
CU = ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']
CLEAR, EDGE, HOLE, HOLE2HOLE = 0.15, 0.3, 0.2, 0.25
EPS = 1e-4
EXPOSED = {('U1', '57'), ('U11', '9'), ('U12', '9'), ('U13', '25'), ('U14', '25')}
DEFAULT_OUTLINE = [50, 45, 190, 150]
DEFAULT_HOLES = [[54, 54], [186, 54], [54, 146], [186, 146]]


def rot(x, y, t):
    """KiCad convention: local (x, y) at orientation t -> board offset."""
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return x * c + y * s, -x * s + y * c


def place_geom(g, at, t):
    """Local shapely geometry -> board frame (KiCad rotation is clockwise-positive in y-down)."""
    return translate(srotate(g, -t, origin=(0, 0), use_radians=False), at[0], at[1])


def pad_local(p):
    w, h = p['size']
    if p['shape'] == 'custom' and p['poly']:
        return Polygon(p['poly']), True          # already in the footprint frame
    if p['shape'] == 'circle':
        g = Point(0, 0).buffer(w / 2, 32)
    elif p['shape'] == 'oval':
        r = min(w, h) / 2
        d = max(w, h) / 2 - r
        g = (LineString([(-d, 0), (d, 0)]) if w >= h else LineString([(0, -d), (0, d)])).buffer(r, 16)
    elif p['shape'] == 'roundrect':
        r = p['rr'] * min(w, h)
        g = box(-w / 2 + r, -h / 2 + r, w / 2 - r, h / 2 - r).buffer(r, 8) if r > 0 else box(-w / 2, -h / 2, w / 2, h / 2)
    else:
        g = box(-w / 2, -h / 2, w / 2, h / 2)
    return g, False


def fp_name(part):
    return part['footprint'].split(':', 1)[1]


def static_items(design):
    """Pads (board frame), drills and courtyards for every placed part plus the mounting holes."""
    board = design.get('board', {})
    pads, drills, courts = [], [], []
    parts = list(design['parts'])
    for i, (x, y) in enumerate(board.get('holes', DEFAULT_HOLES), 1):
        parts.append({'ref': f'H{i}', 'footprint': 'x:MountingHole_3.2mm_M3', 'pins': {}, 'pcb': [x, y, 0]})
    for part in parts:
        ref, (x, y, t) = part['ref'], part['pcb']
        fp = LIB[fp_name(part)]
        for k, p in enumerate(fp['pads']):
            g, framed = pad_local(p)
            if not framed:
                g = translate(srotate(g, -p['rot'], origin=(0, 0)), *p['at'])
            g = place_geom(g, (x, y), t)
            cx, cy = rot(*p['at'], t)
            centre = (x + cx, y + cy)
            num = p['num']
            net = part['pins'].get(num) if num else None
            if p['attr'] == 'npth':
                drills.append({'geom': Point(centre).buffer(p['drill'][0] / 2, 32), 'net': None,
                               'who': f'{ref} hole', 'at': centre})
                continue
            net = net or f'~{ref}.{num or k}'
            layers = CU if p['copper'] == 'all' else p['copper']
            if not layers:
                continue            # paste-only aperture (exposed-pad windows): no copper
            pads.append({'geom': g, 'net': net, 'layers': layers, 'ref': ref, 'num': num, 'at': centre,
                         'smd': p['attr'] == 'smd', 'who': f'{ref}.{num}', 'kind': 'pad',
                         'exposed': (ref, num) in EXPOSED})
            if p['attr'] == 'pth':
                dw, dh = p['drill']
                r = min(dw, dh) / 2
                dd = max(dw, dh) / 2 - r
                dg = (LineString([(-dd, 0), (dd, 0)]) if dw >= dh else LineString([(0, -dd), (0, dd)])).buffer(r, 16) \
                    if dd > 1e-6 else Point(0, 0).buffer(r, 32)
                dg = place_geom(translate(srotate(dg, -p['rot'], origin=(0, 0)), *p['at']), (x, y), t)
                drills.append({'geom': dg, 'net': net, 'who': f'{ref}.{num} drill', 'at': centre})
        for poly in fp['courtyard']:
            if len(poly) >= 3:
                courts.append({'ref': ref, 'geom': place_geom(Polygon(poly).buffer(0), (x, y), t)})
    return pads, drills, courts


def pair_checks(items, kind, limit, same_net_ok=True):
    tree = STRtree([it['geom'] for it in items])
    out = []
    for i, it in enumerate(items):
        for j in tree.query(it['geom'].buffer(limit)):
            j = int(j)
            if j <= i:
                continue
            o = items[j]
            if same_net_ok and it['net'] == o['net']:
                continue
            d = it['geom'].distance(o['geom'])
            if d < limit - EPS:
                out.append((kind, it, o, d))
    return out


def static_checks(pads, drills, courts):
    v = []
    for layer in CU:
        layer_pads = [p for p in pads if layer in p['layers']]
        for kind, a, b, d in pair_checks(layer_pads, 'clearance', CLEAR):
            if a['ref'] == b['ref']:
                continue  # footprint-internal pitch is the footprint's own business (KiCad agrees)
            v.append({'kind': 'clearance', 'layer': layer, 'a': a['who'], 'b': b['who'], 'mm': round(d, 3),
                      'at': mid(a, b), 'src': 'placement'})
    tree = STRtree([c['geom'] for c in courts])
    for d in drills:
        ref = d['who'].split('.')[0].split(' ')[0]
        for j in tree.query(d['geom']):
            c = courts[int(j)]
            if c['ref'] != ref and c['geom'].intersects(d['geom']):
                v.append({'kind': 'pth_courtyard', 'layer': 'F.CrtYd', 'a': d['who'], 'b': c['ref'], 'mm': 0.0,
                          'at': list(d['at']), 'src': 'placement'})
    for i, c in enumerate(courts):
        for j in tree.query(c['geom']):
            j = int(j)
            if j <= i or courts[j]['ref'] == c['ref']:
                continue
            inter = c['geom'].intersection(courts[j]['geom'])
            if inter.area > 1e-4 or c['geom'].distance(courts[j]['geom']) < 1e-3:   # KiCad: touching counts
                v.append({'kind': 'courtyard', 'layer': 'F.CrtYd', 'a': c['ref'], 'b': courts[j]['ref'],
                          'mm': round(inter.area, 3), 'at': list((inter if not inter.is_empty else c['geom'].boundary.intersection(courts[j]['geom'].boundary)).centroid.coords[0]) if not (inter.is_empty and c['geom'].boundary.intersection(courts[j]['geom'].boundary).is_empty) else list(c['geom'].centroid.coords[0]),
                          'src': 'placement'})
    return v


def mid(a, b):
    pa, pb = nearest(a['geom'], b['geom'])
    return [round((pa[0] + pb[0]) / 2, 3), round((pa[1] + pb[1]) / 2, 3)]


def nearest(ga, gb):
    from shapely.ops import nearest_points
    p, q = nearest_points(ga, gb)
    return (p.x, p.y), (q.x, q.y)


def dyn_items(routing):
    tracks, vias = [], []
    for i, t in enumerate(routing['tracks']):
        pts = [tuple(p) for p in t['points']]
        w = t.get('width', 0.2)
        src = t.get('src', f'routing.json tracks[{i}]')
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            g = LineString([a, b]).buffer(w / 2, 8)
            tracks.append({'geom': g, 'net': t['net'], 'layers': [t['layer']], 'layer': t['layer'], 'a': a, 'idx': i,
                           'b': b, 'w': w, 'src': src, 'who': f"{t['net']} track", 'kind': 'track'})
    for i, v in enumerate(routing['vias']):
        at = tuple(v['at'])
        vias.append({'geom': Point(at).buffer(v.get('diameter', 0.6) / 2, 16), 'net': v['net'], 'layers': CU, 'idx': i,
                     'at': at, 'd': v.get('diameter', 0.6), 'drill': v.get('drill', 0.3),
                     'src': v.get('src', f'routing.json vias[{i}]'), 'who': f"{v['net']} via", 'kind': 'via'})
    return tracks, vias


def check(design, routing, cache=True):
    t0 = time.time()
    h = hashlib.sha256(Path(__file__).read_bytes() + json.dumps([[p['ref'], p['footprint'], p['pcb'], p['pins']] for p in design['parts']]
                                  + [design.get('board', {})], sort_keys=True).encode()
                       + (CAD / 'tools' / 'pad_library.json').read_bytes()).hexdigest()
    cpath = CAD.parent / 'build' / 'predrc-cache.pkl'
    st = None
    if cache and cpath.exists():
        try:
            st = pickle.loads(cpath.read_bytes())
            if st.get('hash') != h:
                st = None
        except Exception:
            st = None
    if st is None:
        pads, drills, courts = static_items(design)
        st = {'hash': h, 'pads': pads, 'drills': drills, 'courts': courts,
              'static_v': static_checks(pads, drills, courts)}
        if cache:
            cpath.parent.mkdir(exist_ok=True)
            cpath.write_bytes(pickle.dumps(st))
    pads, drills, courts = st['pads'], st['drills'], st['courts']
    viol = list(st['static_v'])
    tracks, vias = dyn_items(routing)
    board = design.get('board', {})
    x0, y0, x1, y1 = board.get('outline', DEFAULT_OUTLINE)
    edge = box(x0, y0, x1, y1).exterior

    def add(kind, layer, a, b, d, at):
        viol.append({'kind': kind, 'layer': layer, 'a': a.get('src', a['who']) if isinstance(a, dict) else a,
                     'b': b.get('src', b['who']) if isinstance(b, dict) else b,
                     'nets': [a.get('net') if isinstance(a, dict) else None, b.get('net') if isinstance(b, dict) else None],
                     'mm': round(d, 3), 'at': at, 'src': a.get('src', '') if isinstance(a, dict) else ''})

    # clearance: dynamic items against everything on the layer
    for layer in CU:
        stat = [p for p in pads if layer in p['layers']]
        dyn = [t for t in tracks if t['layer'] == layer] + vias
        allit = stat + dyn
        tree = STRtree([it['geom'] for it in allit])
        ns = len(stat)
        for i, it in enumerate(dyn):
            gi = it['geom']
            for j in tree.query(gi.buffer(CLEAR)):
                j = int(j)
                if j >= ns and j - ns <= i:
                    continue            # dyn-dyn pair counted once
                o = allit[j]
                if o['net'] == it['net']:
                    continue
                d = gi.distance(o['geom'])
                if d < CLEAR - EPS:
                    add('clearance', layer, it, o, d, mid(it, o))
    # edge
    for it in pads + tracks + vias:
        d = it['geom'].distance(edge)
        if d < EDGE - EPS or not it['geom'].within(box(x0, y0, x1, y1)):
            if it['kind'] == 'pad' and it['ref'].startswith('J'):
                continue            # the connectors overhang the edge by design (KiCad: Rev E passes)
            add('edge', it['layers'][0], it, {'who': 'board edge'}, d, list(it['geom'].centroid.coords[0]))
    # holes: via and pad drills against other-net copper, and hole to hole
    vdr = [{'geom': Point(v['at']).buffer(v['drill'] / 2, 16), 'net': v['net'], 'who': v['who'], 'src': v['src'],
            'at': v['at']} for v in vias]
    alld = drills + vdr
    copper = pads + tracks + vias
    ctree = STRtree([c['geom'] for c in copper])
    for dr in vdr:      # pad drills vs pads are footprint geometry; check the vias' drills
        for j in ctree.query(dr['geom'].buffer(HOLE)):
            o = copper[int(j)]
            if o['net'] == dr['net'] or (o['kind'] == 'via' and o['at'] == dr['at']):
                continue
            d = dr['geom'].distance(o['geom'])
            if d < HOLE - EPS:
                add('hole', 'drill', dr, o, d, list(dr['at']))
    for dr in drills:   # pad and NPTH drills vs tracks and vias
        for j in ctree.query(dr['geom'].buffer(HOLE)):
            o = copper[int(j)]
            if o['kind'] == 'pad' or (dr['net'] is not None and o['net'] == dr['net']):
                continue
            d = dr['geom'].distance(o['geom'])
            if d < HOLE - EPS:
                add('hole', 'drill', o, dr, d, list(dr['at']))
    dtree = STRtree([d['geom'] for d in alld])
    for i, dr in enumerate(vdr):
        for j in dtree.query(dr['geom'].buffer(HOLE2HOLE)):
            o = alld[int(j)]
            if o is dr:
                continue
            d = dr['geom'].distance(o['geom'])
            if d < HOLE2HOLE - EPS:
                add('hole2hole', 'drill', dr, o, d, list(dr['at']))
    # keepouts
    for ko in routing.get('keepouts', []):
        poly = Polygon(ko['points'])
        for it in tracks + vias:
            if any(l in ko['layers'] for l in it['layers']) and it['geom'].intersects(poly):
                add('keepout', ko['layers'][0], it, {'who': ko['name']}, 0.0,
                    list(it['geom'].intersection(poly).centroid.coords[0]))
    # via ring on an SMD land (only the exposed-pad thermal sets may)
    smd = [p for p in pads if p['smd']]
    stree = STRtree([p['geom'] for p in smd])
    for v in vias:
        for j in stree.query(v['geom']):
            p = smd[int(j)]
            if not p['exposed'] and v['geom'].intersects(p['geom']):
                add('via_land', 'F.Cu', v, p, 0.0, list(v['at']))
    # widths
    for t in tracks:
        if t['w'] < 0.15 - EPS:
            add('width', t['layer'], t, {'who': 'min track 0.15'}, t['w'], list(t['a']))
    for v in vias:
        if v['d'] < 0.45 - EPS or v['drill'] < 0.3 - EPS or (v['d'] - v['drill']) / 2 < 0.075 - EPS:
            add('width', 'via', v, {'who': 'via 0.45/0.3'}, v['d'], list(v['at']))
    zones = [Polygon(z['points']).buffer(-0.3) for z in routing.get('zones', []) if z['net'] == 'GND' and z['layer'] == 'In1.Cu']
    def plane_ok(at):
        return not zones or any(z.contains(Point(at)) for z in zones)
    unconnected, dangling = connectivity(pads, tracks, vias, plane_ok)
    viol += dangling
    return {'violations': viol, 'unconnected': unconnected, 'seconds': round(time.time() - t0, 2),
            'counts': {'pads': len(pads), 'tracks': len(tracks), 'vias': len(vias)}}


def connectivity(pads, tracks, vias, plane_ok=lambda at: True):
    items = pads + tracks + vias
    parent = list(range(len(items) + 1))
    plane = len(items)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[a] = b

    nb = defaultdict(set)
    by_net = defaultdict(list)
    for i, it in enumerate(items):
        by_net[it['net']].append(i)
    for net, idx in by_net.items():
        geoms = [items[i]['geom'] for i in idx]
        tree = STRtree(geoms)
        for a_pos, i in enumerate(idx):
            it = items[i]
            if net == 'GND' and (it['kind'] == 'via' or (it['kind'] == 'pad' and 'In1.Cu' in it['layers'])) \
                    and plane_ok(it['at']):
                union(i, plane)
            # KiCad 10 joins same-net copper whose shapes collide (a track over a pad connects), so
            # union on shape intersection; track ends are tested separately for the dangling report.
            for j in tree.query(it['geom']):
                j = idx[int(j)]
                if j != i and set(it['layers']) & set(items[j]['layers']) and it['geom'].intersects(items[j]['geom']):
                    union(i, j)
                    nb[i].add(j)
    # dangling, KiCad's way: a via must join copper on two layers (a GND via in the In1 plane counts
    # as joined); a track end must touch some other item of its net that is not itself a dangling via.
    dangling = []
    dvia = set()
    for i, it in enumerate(items):
        if it['kind'] != 'via':
            continue
        layers = set()
        for j in nb[i]:
            o = items[j]
            layers |= set(o['layers']) if o['kind'] == 'pad' else {o['layer']} if o['kind'] == 'track' else set()
        if it['net'] == 'GND' and plane_ok(it['at']):
            layers.add('In1.Cu')
        if len(layers) < 2 and not (it['net'] == 'GND' and 'In1.Cu' in layers):
            dvia.add(i)
            dangling.append({'kind': 'dangling', 'layer': 'via', 'a': it['src'], 'b': '', 'nets': [it['net'], None],
                             'mm': 0.0, 'at': list(it['at']), 'src': it['src'], 'item': ('via', it['idx'])})
    for i, it in enumerate(items):
        if it['kind'] != 'track':
            continue
        touched = []
        for e, pt in enumerate((it['a'], it['b'])):
            # the end disc (KiCad accepts an end within half a width of a land edge)
            E = Point(pt).buffer(it['w'] / 2 - 0.001, 8)
            # pads and vias: the end disc touches the land; tracks: the end lies on the other track's
            # centre line (hand routes and the copied Rev E copper join at shared points), so a short
            # segment cannot count its own neighbour twice
            other = Point(it['b'] if e == 0 else it['a'])

            def joins(j):
                o = items[j]
                if o['kind'] != 'track':
                    return o['geom'].intersects(E)
                cl = LineString([o['a'], o['b']])
                if cl.distance(Point(pt)) < 0.002:
                    return True
                # inside a wider neighbour's copper counts, unless that neighbour is the one this
                # (short) segment already joins at its other end
                return o['geom'].contains(Point(pt)) and cl.distance(other) >= 0.002
            near = [j for j in nb[i] if joins(j)]
            touched.append(set(near))
            if any(j in dvia for j in near):
                touched = None
                break           # the dangling via is reported; its stub goes with it
            if not near:
                dangling.append({'kind': 'dangling', 'layer': it['layer'], 'a': it['src'], 'b': '',
                                 'nets': [it['net'], None], 'mm': 0.0, 'at': list(pt), 'src': it['src'],
                                 'item': ('track', it['idx'])})
                touched = None
                break
    unconnected = []
    for net, idx in by_net.items():
        if net.startswith('~'):
            continue
        groups = defaultdict(list)
        for i in idx:
            if items[i]['kind'] == 'pad':
                groups[find(i)].append(i)
        if len(groups) <= 1:
            continue
        comps = sorted(groups.values(), key=len, reverse=True)
        main = comps[0]
        for comp in comps[1:]:
            best = min(((math.dist(items[a]['at'], items[b]['at']), a, b) for a in comp for b in main))
            unconnected.append({'net': net, 'pads': [items[i]['who'] for i in comp],
                                'nearest': [items[best[1]]['who'], items[best[2]]['who']],
                                'from': list(items[best[1]]['at']), 'to': list(items[best[2]]['at']),
                                'mm': round(best[0], 2)})
    # a track end that lands on another track's body is connected (KiCad: anchor inside the item);
    # the pass above tested both directions, so remaining danglers are real.
    return unconnected, dangling


def render(design, routing, res, rect, out, title='', layers=('B.Cu', 'In2.Cu', 'F.Cu')):
    """layers: the copper layers whose tracks are drawn (vias and pads always; SMD lands faint when F.Cu
    is not drawn, so a single inner/back layer can be read for free space)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PatchCollection
    from matplotlib.patches import Polygon as MPoly
    x0, y0, x1, y1 = rect
    fig, ax = plt.subplots(figsize=(12, 12 * (y1 - y0) / (x1 - x0) + 0.6))
    view = box(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
    pads, drills, courts = static_items(design)
    tracks, vias = dyn_items(routing)
    col = {'F.Cu': '#c83737', 'In2.Cu': '#c8a037', 'B.Cu': '#3771c8', 'In1.Cu': '#888888'}

    def polys(g):
        return list(g.geoms) if hasattr(g, 'geoms') else [g]

    for ko in routing.get('keepouts', []):
        poly = Polygon(ko['points'])
        if poly.intersects(view):
            ax.add_patch(MPoly(list(poly.exterior.coords), closed=True, fc='none', ec='#666', ls=':', lw=0.8))
    for c in courts:
        if c['geom'].intersects(view):
            for g in polys(c['geom']):
                ax.add_patch(MPoly(list(g.exterior.coords), closed=True, fc='none', ec='#b0b', lw=0.4))
            if c['geom'].centroid.within(view):
                ax.text(c['geom'].centroid.x, c['geom'].bounds[1] - 0.15, c['ref'], fontsize=6, ha='center',
                        va='bottom', color='#606')
    for layer in [l for l in ('B.Cu', 'In2.Cu', 'F.Cu') if l in layers]:
        patches = []
        for t in tracks:
            if t['layer'] == layer and t['geom'].intersects(view):
                patches.append(MPoly(list(t['geom'].exterior.coords), closed=True))
        ax.add_collection(PatchCollection(patches, fc=col[layer], ec='none', alpha=0.75 if layer == 'F.Cu' else 0.6))
    for p in pads:
        if p['geom'].intersects(view):
            ax.add_patch(MPoly(list(p['geom'].exterior.coords), closed=True,
                               fc='#d99' if p['smd'] else '#cc9', ec='#733', lw=0.3,
                               alpha=0.9 if ('F.Cu' in layers or not p['smd']) else 0.15))
            if p['net'] and not p['net'].startswith('~'):
                ax.text(p['at'][0], p['at'][1], p['net'][:9], fontsize=3.2, ha='center', va='center')
    for v in vias:
        if v['geom'].intersects(view):
            ax.add_patch(MPoly(list(v['geom'].exterior.coords), closed=True, fc='#333' if v['net'] == 'GND' else '#2a2',
                               ec='none'))
    for d in drills:
        if d['geom'].intersects(view) and d['net'] is None:
            ax.add_patch(MPoly(list(d['geom'].exterior.coords), closed=True, fc='white', ec='k', lw=0.5))
    for t in tracks:
        if t['geom'].intersects(view) and t['net'] != 'GND' and t['layer'] in layers:
            mx, my = (t['a'][0] + t['b'][0]) / 2, (t['a'][1] + t['b'][1]) / 2
            if x0 <= mx <= x1 and y0 <= my <= y1 and math.dist(t['a'], t['b']) > 3:
                ax.text(mx, my, t['net'], fontsize=3.5, color='#004', ha='center', va='center')
    n_v = n_u = 0
    for v in res['violations']:
        x, y = v['at']
        if x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1:
            n_v += 1
            ax.plot(x, y, 'x', color='red', ms=9, mew=2)
            ax.text(x + 0.3, y - 0.3, f"{v['kind']} {v['src'].split(':')[-1]}", fontsize=5, color='red')
    for u in res['unconnected']:
        (a, b), (c, d) = u['from'], u['to']
        if (x0 <= a <= x1 and y0 <= b <= y1) or (x0 <= c <= x1 and y0 <= d <= y1):
            n_u += 1
            ax.plot([a, c], [b, d], color='#0a0', lw=0.8, ls='--')
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.set_aspect('equal')
    ax.grid(True, lw=0.2)
    ax.set_title(f'{title} [{"+".join(l.split(".")[0] for l in layers)}]  violations {n_v}  unconnected {n_u}  (F red, In2 gold, B blue; green dashed = unrouted)',
                 fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def summary(res, limit=40):
    lines = [f"pre-DRC {res['seconds']} s: {len(res['violations'])} violations, {len(res['unconnected'])} unconnected "
             f"({res['counts']['pads']} pads, {res['counts']['tracks']} segments, {res['counts']['vias']} vias)"]
    by = defaultdict(int)
    for v in res['violations']:
        by[v['kind']] += 1
    if by:
        lines.append('  ' + ', '.join(f'{k} {n}' for k, n in sorted(by.items())))
    for v in res['violations'][:limit]:
        lines.append(f"  {v['kind']:10s} {v['layer']:7s} {str(v['a'])[:38]:38s} vs {str(v['b'])[:30]:30s} "
                     f"{v['mm']:.3f} @ ({v['at'][0]:.2f}, {v['at'][1]:.2f})")
    for u in res['unconnected'][:limit]:
        lines.append(f"  unconnected {u['net']}: {','.join(u['pads'][:6])} -> {u['nearest'][1]} ({u['mm']} mm)")
    return '\n'.join(lines)


KICAD_KIND = {'shorting_items': 'clearance', 'clearance': 'clearance', 'courtyards_overlap': 'courtyard',
              'copper_edge_clearance': 'edge', 'hole_clearance': 'hole', 'hole_to_hole': 'hole2hole',
              'pth_inside_courtyard': 'pth_courtyard', 'via_dangling': 'dangling', 'track_dangling': 'dangling',
              'items_not_allowed': 'keepout', 'track_width': 'width', 'via_diameter': 'width',
              'annular_width': 'width', 'drill_out_of_range': 'width'}


def compare(res, drc):
    """Calibration tally: KiCad DRC categories against the pre-DRC's (silk, mask and zone-fill checks are
    KiCad-only; solder_mask_bridge between different-net lands implies a clearance violation here)."""
    from collections import Counter
    k = Counter(KICAD_KIND.get(v['type'], 'kicad-only:' + v['type']) for v in drc['violations'])
    m = Counter(v['kind'] for v in res['violations'])
    print(f"{'category':28s} {'KiCad':>6s} {'pre-DRC':>8s}")
    for c in sorted(set(k) | set(m)):
        print(f'{c:28s} {k.get(c, 0):6d} {m.get(c, 0):8d}')
    print(f"{'unconnected':28s} {len(drc['unconnected_items']):6d} {len(res['unconnected']):8d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--design', default=str(CAD / 'design.json'))
    ap.add_argument('--routing', default=str(CAD / 'routing.json'))
    ap.add_argument('--json', help='write the full result here')
    ap.add_argument('--render', help='x0,y0,x1,y1 window to render')
    ap.add_argument('--out', default='predrc.png')
    ap.add_argument('--kicad', help='a kicad-cli DRC json of the same board: print both tallies side by side')
    a = ap.parse_args()
    design = json.loads(Path(a.design).read_text())
    routing = json.loads(Path(a.routing).read_text())
    res = check(design, routing)
    print(summary(res))
    if a.kicad:
        compare(res, json.loads(Path(a.kicad).read_text()))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1) + '\n')
    if a.render:
        render(design, routing, res, [float(v) for v in a.render.split(',')], a.out)
    return 0 if not res['violations'] and not res['unconnected'] else 1


if __name__ == '__main__':
    sys.exit(main())
