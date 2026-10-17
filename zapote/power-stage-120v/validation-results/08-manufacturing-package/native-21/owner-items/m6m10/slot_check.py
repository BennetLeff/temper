"""Copper (any net, any layer) inside candidate barrier-slot keep-outs between J5 and J2,
and free-area check for candidate J5 relocation sites. Usage: slot_check.py copper-dump.json"""
import json, sys
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
d = json.load(open(sys.argv[1]))
items=[]
for z in d['zones']:
    if len(z['pts'])>=3: items.append((z['net'], z['layer'], Polygon(z['pts']).buffer(0)))
for t in d['tracks']: items.append((t['net'], t['layer'], LineString([t['a'],t['b']]).buffer(t['w']/2)))
for v in d['vias']: items.append((v['net'], 'via', Point(v['at']).buffer(v['d']/2)))
for p in d['pads']: items.append((p['net'], 'pad'+('-tht' if p['tht'] else ''), Polygon(p['pts']).buffer(0)))
def report(name, region):
    hits={}
    for n,L,g in items:
        if g.intersects(region):
            k=(n,L); hits[k]=hits.get(k,0)+g.intersection(region).area
    print(f"{name}: bounds {[round(v,2) for v in region.bounds]}  ->", 'CLEAR' if not hits else {f'{k[0]}@{k[1]}':round(a,2) for k,a in hits.items()})
# slot: 2.0 mm wide centred on y 77.6 (midway between the 75.1 / 80.1 pour edges), x 122-152,
# plus 0.5 mm copper setback each side (fab rule for milled edges; insulation distance unaffected)
report('slot 2.0 mm, y76.6-78.6, x122-152', box(122,76.6,152,78.6))
report('slot + 0.5 mm setback', box(121.5,76.1,152.5,79.1))
# strip between pours
report('whole inter-stud strip y75.1-80.1, x115-153', box(115,75.1,153,80.1))
# J5 relocation candidates: 10.2 mm REDCUBE courtyard square + 5 mm tank rule ring to other nets
for c in [(147.0,58.0),(146.0,57.0),(145.0,55.0),(132.0,55.5)]:
    report(f'J5 at {c} courtyard', box(c[0]-5.1,c[1]-5.1,c[0]+5.1,c[1]+5.1))
