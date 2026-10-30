"""Fast pre-DRC for hand routing: clearance, keepouts, edge, holes, via-on-land and connectivity, no KiCad.

It takes the placement (a design dict: parts + board), the hand routes (a routing dict, model.py) and the
footprint geometry of a pad library (model.py), and checks with shapely what KiCad's DRC would flag:
  clearance   copper of different nets on one layer closer than rules.clearance (pads, tracks, vias)
  edge        copper closer than rules.edge to the board outline (pads of refs in edge_exempt are skipped)
  hole        a drill closer than rules.hole to other-net copper; drills closer than rules.hole2hole
  keepout     a track or via inside a rule area on that layer (keepouts with tracks False are fill-only)
  via_land    a via ring on an SMD land other than the exposed (thermal) pads
  width       track < min_track, via < min_via, drill < min_drill, ring < min_ring
  courtyard   F.CrtYd overlap between footprints; pth_courtyard a drill in another part's courtyard
  angle       inner angle under min_angle between two segments meeting at an end point (craft.angle_checks)
  craft       (design.board.craft) craft.checks: T-junctions, land entries, 90-degree corners, via pads
  unconnected pads of one net in more than one copper island (union-find over pads, track anchors, vias;
              a plane (net, layer) joins that net's vias and through-hole pads inside its zones)
  dangling    a via joining copper on fewer than two layers, or a track end touching nothing of its net
It is a fast screen, not a sign-off: KiCad's DRC is.  Silk, mask, zone-fill islands and schematic parity
are KiCad-only.  Calibration on the LCR meter (Rev E, first Rev F placement): instruments/lcr-meter/cad/tools/
predrc.py.

Usage:
    drc = PreDRC(lib, exposed={('U1', '57')}, plane=('GND', 'In1.Cu'), edge_exempt=('J',),
                 cache_path='build/predrc-cache.pkl')
    res = drc.check(design, routing)       # {'violations', 'unconnected', 'seconds', 'counts'}
    print(summary(res))
"""
from __future__ import annotations

import hashlib
import json
import math
import pickle
import time
from collections import defaultdict
from pathlib import Path

from shapely import STRtree
from shapely.affinity import rotate as srotate, translate
from shapely.geometry import LineString, Point, Polygon, box

from . import craft
from .model import fp_name, rot

CU = ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']
RULES = {'layers': CU, 'clearance': 0.15, 'edge': 0.3, 'hole': 0.2, 'hole2hole': 0.25, 'min_angle': 45.0,
         'angle_tol': 0.1, 'angle_join': 0.002, 'eps': 1e-4}
MIN = {'track': 0.15, 'via': 0.45, 'drill': 0.3, 'ring': 0.075}      # width rule
KICAD_KIND = {'shorting_items': 'clearance', 'clearance': 'clearance', 'courtyards_overlap': 'courtyard',
              'copper_edge_clearance': 'edge', 'hole_clearance': 'hole', 'hole_to_hole': 'hole2hole',
              'pth_inside_courtyard': 'pth_courtyard', 'via_dangling': 'dangling', 'track_dangling': 'dangling',
              'items_not_allowed': 'keepout', 'track_width': 'width', 'via_diameter': 'width',
              'annular_width': 'width', 'drill_out_of_range': 'width'}


def place_geom(g, at, t):
    """Local shapely geometry -> board frame (KiCad rotation is clockwise-positive in y-down)."""
    return translate(srotate(g, -t, origin=(0, 0), use_radians=False), at[0], at[1])


def pad_local(p):
    """A pad-library pad -> (shapely geometry in the pad frame, or footprint frame if custom; framed?)."""
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


def nearest(ga, gb):
    from shapely.ops import nearest_points
    p, q = nearest_points(ga, gb)
    return (p.x, p.y), (q.x, q.y)


def mid(a, b):
    pa, pb = nearest(a['geom'], b['geom'])
    return [round((pa[0] + pb[0]) / 2, 3), round((pa[1] + pb[1]) / 2, 3)]


def pair_checks(items, kind, limit, same_net_ok=True, eps=RULES['eps']):
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
            if d < limit - eps:
                out.append((kind, it, o, d))
    return out


def dyn_items(routing, layers=CU):
    """Tracks (one item per segment) and vias as shapely items."""
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
        vias.append({'geom': Point(at).buffer(v.get('diameter', 0.6) / 2, 16), 'net': v['net'], 'layers': layers,
                     'idx': i, 'at': at, 'd': v.get('diameter', 0.6), 'drill': v.get('drill', 0.3),
                     'src': v.get('src', f'routing.json vias[{i}]'), 'who': f"{v['net']} via", 'kind': 'via'})
    return tracks, vias


class PreDRC:
    """One board's pre-DRC configuration.

    lib              pad library (model.py)
    exposed          {(ref, pad)} thermal pads: plane lands, allowed under vias, exempt from the entry rule
    default_outline  board outline when design.board has none; default_holes likewise (mounting holes)
    plane            (net, layer) of a solid plane joined by that net's vias and through-hole pads, or None
    edge_exempt      reference prefixes whose pads may overhang the edge (connectors by design)
    rules, mins      overrides of RULES and MIN
    cache_path       pickle of the static part (pads, courtyards, pad-pad checks), keyed on a hash, or None
    hole_footprint / fiducial_footprint / testpoint_footprint   footprints placed for design.board holes,
                     fiducials and testpoints (testpoint: a format string taking the diameter d)
    """

    def __init__(self, lib, exposed=(), default_outline=None, default_holes=(), plane=None, edge_exempt=(),
                 rules=None, mins=None, cache_path=None, hole_footprint='MountingHole_3.2mm_M3',
                 fiducial_footprint='Fiducial_1mm_Mask2mm', testpoint_footprint='TestPoint_Pad_D{d:.1f}mm'):
        self.lib = lib
        self.exposed = set(exposed)
        self.default_outline = default_outline
        self.default_holes = [list(h) for h in default_holes]
        self.plane = plane
        self.edge_exempt = tuple(edge_exempt)
        self.rules = dict(RULES, **(rules or {}))
        self.mins = dict(MIN, **(mins or {}))
        self.layers = self.rules['layers']
        self.cache_path = Path(cache_path) if cache_path else None
        self.hole_fp, self.fid_fp, self.tp_fp = hole_footprint, fiducial_footprint, testpoint_footprint
        self._lib_bytes = json.dumps(lib, sort_keys=True).encode()

    # ---------------------------------------------------------------- static items
    def board_parts(self, design):
        """The design's parts plus the board-only footprints: mounting holes, fiducials, test points."""
        board = design.get('board', {})
        parts = list(design['parts'])
        for i, (x, y) in enumerate(board.get('holes', self.default_holes), 1):
            parts.append({'ref': f'H{i}', 'footprint': 'x:' + self.hole_fp, 'pins': {}, 'pcb': [x, y, 0]})
        for i, (x, y) in enumerate(board.get('fiducials', []), 1):
            parts.append({'ref': f'FID{i}', 'footprint': 'x:' + self.fid_fp, 'pins': {}, 'pcb': [x, y, 0]})
        for i, (_, net, x, y, d) in enumerate(board.get('testpoints', []), 1):
            parts.append({'ref': f'TP{i}', 'footprint': 'x:' + self.tp_fp.format(d=d), 'pins': {'1': net},
                          'pcb': [x, y, 0]})
        return parts

    def static_items(self, design):
        """Pads (board frame), drills and courtyards for every placed part plus the board-only footprints."""
        pads, drills, courts = [], [], []
        for part in self.board_parts(design):
            ref, (x, y, t) = part['ref'], part['pcb']
            fp = self.lib[fp_name(part)]
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
                layers = self.layers if p['copper'] == 'all' else p['copper']
                if not layers:
                    continue            # paste-only aperture (exposed-pad windows): no copper
                pads.append({'geom': g, 'net': net, 'layers': layers, 'ref': ref, 'num': num, 'at': centre,
                             'smd': p['attr'] == 'smd', 'who': f'{ref}.{num}', 'kind': 'pad', 'shape': p['shape'],
                             'exposed': (ref, num) in self.exposed})
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

    def static_checks(self, pads, drills, courts):
        v = []
        for layer in self.layers:
            layer_pads = [p for p in pads if layer in p['layers']]
            for kind, a, b, d in pair_checks(layer_pads, 'clearance', self.rules['clearance'], eps=self.rules['eps']):
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
                    touch = c['geom'].boundary.intersection(courts[j]['geom'].boundary)
                    at = (list(inter.centroid.coords[0]) if not inter.is_empty else list(touch.centroid.coords[0])) \
                        if not (inter.is_empty and touch.is_empty) else list(c['geom'].centroid.coords[0])
                    v.append({'kind': 'courtyard', 'layer': 'F.CrtYd', 'a': c['ref'], 'b': courts[j]['ref'],
                              'mm': round(inter.area, 3), 'at': at, 'src': 'placement'})
        return v

    def outline(self, design):
        return design.get('board', {}).get('outline', self.default_outline)

    def dyn_items(self, routing):
        return dyn_items(routing, self.layers)

    def angle_checks(self, routing):
        """Inner angles at shared segment end points, per net and layer (craft.angle_checks)."""
        return craft.angle_checks(routing, self.rules)

    def craft_inputs(self, design):
        """The placement as craft.py's plain data: pads (exact land outlines), drills, board."""
        pads, drills, _ = self.static_items(design)
        plain = [{'ref': p['ref'], 'pad': p['num'], 'net': p['net'], 'at': list(p['at']), 'shape': p['shape'],
                  'layers': list(p['layers']), 'smd': p['smd'], 'exposed': p['exposed'],
                  'size': [round(b - a, 4) for a, b in zip(p['geom'].bounds[:2], p['geom'].bounds[2:])],
                  'outline': [list(c) for c in p['geom'].exterior.coords]} for p in pads]
        dr = [{'at': list(d['at']), 'net': d['net'], 'who': d['who'],
               'outline': [list(c) for c in d['geom'].exterior.coords]} for d in drills]
        return plain, dr, {'outline': self.outline(design)}

    # ---------------------------------------------------------------- the check
    def _static(self, design, cache):
        h = hashlib.sha256(Path(__file__).read_bytes()
                           + json.dumps([[p['ref'], p['footprint'], p['pcb'], p['pins']] for p in design['parts']]
                                        + [design.get('board', {}), sorted(map(list, self.exposed)),
                                           self.default_holes, self.layers], sort_keys=True).encode()
                           + self._lib_bytes).hexdigest()
        cpath = self.cache_path if cache else None
        st = None
        if cpath and cpath.exists():
            try:
                st = pickle.loads(cpath.read_bytes())
                if st.get('hash') != h:
                    st = None
            except Exception:
                st = None
        if st is None:
            pads, drills, courts = self.static_items(design)
            st = {'hash': h, 'pads': pads, 'drills': drills, 'courts': courts,
                  'static_v': self.static_checks(pads, drills, courts)}
            if cpath:
                cpath.parent.mkdir(parents=True, exist_ok=True)
                cpath.write_bytes(pickle.dumps(st))
        return st

    def check(self, design, routing, cache=True):
        R, M = self.rules, self.mins
        CLEAR, EDGE, HOLE, HOLE2HOLE, EPS = R['clearance'], R['edge'], R['hole'], R['hole2hole'], R['eps']
        t0 = time.time()
        st = self._static(design, cache)
        pads, drills = st['pads'], st['drills']
        viol = list(st['static_v'])
        tracks, vias = self.dyn_items(routing)
        board = design.get('board', {})
        x0, y0, x1, y1 = self.outline(design)
        edge = box(x0, y0, x1, y1).exterior

        def add(kind, layer, a, b, d, at):
            viol.append({'kind': kind, 'layer': layer, 'a': a.get('src', a['who']) if isinstance(a, dict) else a,
                         'b': b.get('src', b['who']) if isinstance(b, dict) else b,
                         'nets': [a.get('net') if isinstance(a, dict) else None,
                                  b.get('net') if isinstance(b, dict) else None],
                         'mm': round(d, 3), 'at': at, 'src': a.get('src', '') if isinstance(a, dict) else ''})

        # clearance: dynamic items against everything on the layer
        for layer in self.layers:
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
                if it['kind'] == 'pad' and it['ref'].startswith(self.edge_exempt):
                    continue            # parts that overhang the edge by design
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
        for dr in vdr:
            for j in dtree.query(dr['geom'].buffer(HOLE2HOLE)):
                o = alld[int(j)]
                if o is dr:
                    continue
                d = dr['geom'].distance(o['geom'])
                if d < HOLE2HOLE - EPS:
                    add('hole2hole', 'drill', dr, o, d, list(dr['at']))
        # keepouts
        for ko in routing.get('keepouts', []):
            if not ko.get('tracks', True):
                continue                # a zone-fill-only rule area: copper may cross it
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
            if t['w'] < M['track'] - EPS:
                add('width', t['layer'], t, {'who': f"min track {M['track']}"}, t['w'], list(t['a']))
        for v in vias:
            if v['d'] < M['via'] - EPS or v['drill'] < M['drill'] - EPS or (v['d'] - v['drill']) / 2 < M['ring'] - EPS:
                add('width', 'via', v, {'who': f"via {M['via']}/{M['drill']}"}, v['d'], list(v['at']))
        for a in self.angle_checks(routing):
            viol.append(a)
        if board.get('craft'):          # craft rules: T-junctions, land entries, corners, via pads
            viol += craft.checks(routing, *self.craft_inputs(design), self.rules)
        if self.plane:
            zones = [Polygon(z['points']).buffer(-0.3) for z in routing.get('zones', [])
                     if z['net'] == self.plane[0] and z['layer'] == self.plane[1]]
        else:
            zones = []

        def plane_ok(at):
            return not zones or any(z.contains(Point(at)) for z in zones)
        unconnected, dangling = self.connectivity(pads, tracks, vias, plane_ok)
        viol += dangling
        return {'violations': viol, 'unconnected': unconnected, 'seconds': round(time.time() - t0, 2),
                'counts': {'pads': len(pads), 'tracks': len(tracks), 'vias': len(vias)}}

    def connectivity(self, pads, tracks, vias, plane_ok=lambda at: True):
        pnet, player = self.plane or (None, None)
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
            for i in idx:
                it = items[i]
                if pnet is not None and net == pnet \
                        and (it['kind'] == 'via' or (it['kind'] == 'pad' and player in it['layers'])) \
                        and plane_ok(it['at']):
                    union(i, plane)
                # KiCad 10 joins same-net copper whose shapes collide (a track over a pad connects), so
                # union on shape intersection; track ends are tested separately for the dangling report.
                for j in tree.query(it['geom']):
                    j = idx[int(j)]
                    if j != i and set(it['layers']) & set(items[j]['layers']) and it['geom'].intersects(items[j]['geom']):
                        union(i, j)
                        nb[i].add(j)
        # dangling, KiCad's way: a via must join copper on two layers (a plane-net via inside the plane
        # counts as joined); a track end must touch some other item of its net that is not a dangling via.
        dangling = []
        dvia = set()
        for i, it in enumerate(items):
            if it['kind'] != 'via':
                continue
            layers = set()
            for j in nb[i]:
                o = items[j]
                layers |= set(o['layers']) if o['kind'] == 'pad' else {o['layer']} if o['kind'] == 'track' else set()
            if pnet is not None and it['net'] == pnet and plane_ok(it['at']):
                layers.add(player)
            if len(layers) < 2 and not (pnet is not None and it['net'] == pnet and player in layers):
                dvia.add(i)
                dangling.append({'kind': 'dangling', 'layer': 'via', 'a': it['src'], 'b': '', 'nets': [it['net'], None],
                                 'mm': 0.0, 'at': list(it['at']), 'src': it['src'], 'item': ('via', it['idx'])})
        for i, it in enumerate(items):
            if it['kind'] != 'track':
                continue
            for e, pt in enumerate((it['a'], it['b'])):
                # the end disc (KiCad accepts an end within half a width of a land edge)
                E = Point(pt).buffer(it['w'] / 2 - 0.001, 8)
                # pads and vias: the end disc touches the land; tracks: the end lies on the other track's
                # centre line (joined routes share points), so a short segment cannot count its own
                # neighbour twice
                other = Point(it['b'] if e == 0 else it['a'])

                def joins(j, E=E, pt=pt, other=other):
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
                if any(j in dvia for j in near):
                    break           # the dangling via is reported; its stub goes with it
                if not near:
                    dangling.append({'kind': 'dangling', 'layer': it['layer'], 'a': it['src'], 'b': '',
                                     'nets': [it['net'], None], 'mm': 0.0, 'at': list(pt), 'src': it['src'],
                                     'item': ('track', it['idx'])})
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
        return unconnected, dangling

    # ---------------------------------------------------------------- picture
    def render(self, design, routing, res, rect, out, title='', layers=('B.Cu', 'In2.Cu', 'F.Cu')):
        """A window of the board with violations (red x) and unrouted pairs (green dashed).  layers: the
        copper layers whose tracks are drawn (vias and pads always; SMD lands faint when F.Cu is not drawn)."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.collections import PatchCollection
        from matplotlib.patches import Polygon as MPoly
        x0, y0, x1, y1 = rect
        fig, ax = plt.subplots(figsize=(12, 12 * (y1 - y0) / (x1 - x0) + 0.6))
        view = box(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
        pads, drills, courts = self.static_items(design)
        tracks, vias = self.dyn_items(routing)
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
        pnet = self.plane[0] if self.plane else None
        for v in vias:
            if v['geom'].intersects(view):
                ax.add_patch(MPoly(list(v['geom'].exterior.coords), closed=True,
                                   fc='#333' if v['net'] == pnet else '#2a2', ec='none'))
        for d in drills:
            if d['geom'].intersects(view) and d['net'] is None:
                ax.add_patch(MPoly(list(d['geom'].exterior.coords), closed=True, fc='white', ec='k', lw=0.5))
        for t in tracks:
            if t['geom'].intersects(view) and t['net'] != pnet and t['layer'] in layers:
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
        ax.set_title(f'{title} [{"+".join(l.split(".")[0] for l in layers)}]  violations {n_v}  unconnected {n_u}  '
                     '(F red, In2 gold, B blue; green dashed = unrouted)', fontsize=9)
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


def compare(res, drc):
    """Calibration tally: KiCad DRC categories against the pre-DRC's (silk, mask and zone-fill checks are
    KiCad-only; solder_mask_bridge between different-net lands implies a clearance violation here)."""
    from collections import Counter
    k = Counter(KICAD_KIND.get(v['type'], 'kicad-only:' + v['type']) for v in drc['violations'])
    m = Counter(v['kind'] for v in res['violations'])
    lines = [f"{'category':28s} {'KiCad':>6s} {'pre-DRC':>8s}"]
    for c in sorted(set(k) | set(m)):
        lines.append(f'{c:28s} {k.get(c, 0):6d} {m.get(c, 0):8d}')
    lines.append(f"{'unconnected':28s} {len(drc['unconnected_items']):6d} {len(res['unconnected']):8d}")
    return '\n'.join(lines)
