import json, sys
from shapely.geometry import LineString, Point, Polygon
d = json.load(open(sys.argv[1])); net = sys.argv[2]
drop = [tuple(map(float, s.split(','))) for s in sys.argv[3:]]  # x1,y1,x2,y2,layer-index? simple: a,b match
items = []
for t in d['tracks']:
    if t['net'] != net: continue
    if any((abs(t['a'][0]-a)<.01 and abs(t['a'][1]-b)<.01 and abs(t['b'][0]-c)<.01 and abs(t['b'][1]-e)<.01) or
           (abs(t['b'][0]-a)<.01 and abs(t['b'][1]-b)<.01 and abs(t['a'][0]-c)<.01 and abs(t['a'][1]-e)<.01) for a,b,c,e in drop):
        continue
    g = LineString([t['a'], t['b']]).buffer(t['w']/2) if t['a'] != t['b'] else Point(t['a']).buffer(t['w']/2)
    items.append(('T', {t['layer']}, g, t))
for v in d['vias']:
    if v['net'] == net: items.append(('V', {'F.Cu','In1.Cu','In2.Cu','B.Cu'}, Point(v['at']).buffer(v['d']/2), v))
for p in d['pads']:
    if p['net'] == net:
        L = {'F.Cu','In1.Cu','In2.Cu','B.Cu'} if p.get('tht') else set(p.get('layers', ['F.Cu']))
        items.append(('P', L, Polygon(p['pts']).buffer(0), p))
for z in d['zones']:
    if z['net'] == net and len(z['pts']) > 2:
        items.append(('Z', {z['layer']}, Polygon(z['pts'], [h for h in z['holes'] if len(h) > 2]).buffer(0), z))
n = len(items); par = list(range(n))
def f(i):
    while par[i] != i: par[i] = par[par[i]]; i = par[i]
    return i
from shapely.strtree import STRtree
tree = STRtree([it[2] for it in items])
for i, it in enumerate(items):
    for j in tree.query(it[2]):
        j = int(j)
        if j > i and it[1] & items[j][1] and it[2].intersects(items[j][2]):
            par[f(i)] = f(j)
comps = {}
for i in range(n): comps.setdefault(f(i), []).append(i)
print(net, 'components', len(comps))
for c in comps.values():
    pads = sorted({items[i][3]['ref']+'' for i in c if items[i][0]=='P'})
    print(' ', len(c), 'items; pads', pads[:20])
