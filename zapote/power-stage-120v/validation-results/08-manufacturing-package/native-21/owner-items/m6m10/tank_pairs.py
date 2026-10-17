"""Plan-view and per-layer minimum copper gaps for the pairs that carry coil / capacitor voltage,
and the length of facing edge under 5.5 mm. Usage: tank_pairs.py copper-dump.json"""
import json, sys
from collections import defaultdict
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union, nearest_points
d=json.load(open(sys.argv[1])); LY=('F.Cu','In1.Cu','In2.Cu','B.Cu')
g=defaultdict(list)
for z in d['zones']:
    if len(z['pts'])>=3: g[(z['net'],z['layer'])].append(Polygon(z['pts']).buffer(0))
for t in d['tracks']: g[(t['net'],t['layer'])].append(LineString([t['a'],t['b']]).buffer(t['w']/2))
for v in d['vias']:
    for L in LY: g[(v['net'],L)].append(Point(v['at']).buffer(v['d']/2))
for p in d['pads']:
    for L in (LY if p['tht'] else ('F.Cu',)): g[(p['net'],L)].append(Polygon(p['pts']).buffer(0))
U={k:unary_union(v) for k,v in g.items()}
def allL(n): return unary_union([U[(n,L)] for L in LY if (n,L) in U])
for a,b,what in (('res_a','coil_feed','coil voltage (J5-J2)'),('res_a','sw_a','coil voltage (+T1 1-turn drop)'),('res_a','sw_b','resonant-capacitor voltage'),('coil_feed','sw_b','bridge output'),('res_a','n_ls','res_a to LOW group'),('res_a','hv_ret','res_a to bus return'),('res_a','bus_p','res_a to bus +')):
    A,B=allL(a),allL(b); dmin=A.distance(B); p,q=nearest_points(A,B)
    per={L:round(U[(a,L)].distance(U[(b,L)]),3) for L in LY if (a,L) in U and (b,L) in U}
    # facing length: boundary of A within 5.5 mm of B
    near=A.boundary.intersection(B.buffer(5.5))
    print(f"{a:9s}-{b:9s} plan {dmin:6.3f} mm at ({p.x:.1f},{p.y:.1f}) per-layer {per}  A-edge within 5.5 mm: {near.length:.0f} mm   [{what}]")
