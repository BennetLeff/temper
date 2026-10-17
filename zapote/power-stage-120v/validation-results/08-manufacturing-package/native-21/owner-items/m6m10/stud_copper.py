"""M6 measurements on the stage-11 board copper dump: J2 (coil_feed) / J5 (res_a) copper gaps,
neighbour nets around the studs. Usage: stud_copper.py copper-dump.json"""
import json, sys
from collections import defaultdict
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
d = json.load(open(sys.argv[1]))
geo = defaultdict(list)  # (net, layer) -> geoms
for z in d['zones']:
    if len(z['pts']) >= 3: geo[(z['net'], z['layer'])].append(Polygon(z['pts']).buffer(0))
for t in d['tracks']:
    geo[(t['net'], t['layer'])].append(LineString([t['a'], t['b']]).buffer(t['w']/2))
for v in d['vias']:
    for L in ('F.Cu','In1.Cu','In2.Cu','B.Cu'):
        geo[(v['net'], L)].append(Point(v['at']).buffer(v['d']/2))
padinfo=[]
for p in d['pads']:
    g = Polygon(p['pts']).buffer(0)
    layers = p.get('layers') or (['F.Cu','In1.Cu','In2.Cu','B.Cu'] if p['tht'] else ['F.Cu'])
    for L in layers: geo[(p['net'], L)].append(g)
    padinfo.append((p['ref'], p['net'], g))
print('pad keys', list(d['pads'][0].keys()))
U = {k: unary_union(v) for k, v in geo.items()}
layers = ('F.Cu','In1.Cu','In2.Cu','B.Cu')
def net_all(n): return unary_union([U[(n,L)] for L in layers if (n,L) in U])
ra, cf = net_all('res_a'), net_all('coil_feed')
print('res_a vs coil_feed plan-view min gap: %.3f mm' % ra.distance(cf))
for L in layers:
    if ('res_a',L) in U and ('coil_feed',L) in U:
        print('  %s: %.3f mm' % (L, U[('res_a',L)].distance(U[('coil_feed',L)])))
# where is that gap
from shapely.ops import nearest_points
a,b = nearest_points(ra, cf); print('  at', [round(c,2) for c in a.coords[0]], [round(c,2) for c in b.coords[0]])
# copper of each stud's net near the studs (bbox) per layer
for n,(cx,cy) in (('res_a',(132,70.5)),('coil_feed',(132,85.5))):
    for L in layers:
        if (n,L) in U:
            g = U[(n,L)].intersection(Point(cx,cy).buffer(20))
            if not g.is_empty: print(n, L, 'bounds within 20 mm of stud', [round(x,1) for x in g.bounds], 'area %.0f' % g.area)
# nearest other nets to each stud body (7x7 square) and lug envelope
cats = {}
for n in {k[0] for k in U}:
    cats[n] = net_all(n)
for name, (cx,cy) in (('J5',(132,70.5)),('J2',(132,85.5))):
    sq = Polygon([(cx-3.5,cy-3.5),(cx+3.5,cy-3.5),(cx+3.5,cy+3.5),(cx-3.5,cy+3.5)])
    ds = sorted((sq.distance(g), n) for n, g in cats.items() if n not in ('res_a','coil_feed') and n)
    print(name, 'nearest other-net copper to the 7 mm body (plan view):', [(n, round(x,2)) for x,n in ds[:8]])
