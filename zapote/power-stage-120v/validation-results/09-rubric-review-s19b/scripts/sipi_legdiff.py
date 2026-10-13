#!/usr/bin/env python3
"""usage: sipi_legdiff.py OLD_copper.json.gz NEW_copper.json.gz  (leg boxes A21,B21 +20 mm)"""
import gzip,json,sys
from shapely.geometry import Polygon,box
from shapely.ops import unary_union
load=lambda f: json.load(gzip.open(f))['primitives']
LEG={"A21":(37.865,4.215,89.58,46.125),"B21":(2.4,4.215,42.58,46.125)}
def rec(p):
    k=p['kind']
    if k=='track': return (k,p['net'],p['layer'],tuple(round(x,3) for x in p['start']),tuple(round(x,3) for x in p['end']),p['width_mm'])
    if k=='via': return (k,p['net'],tuple(round(x,3) for x in p['centre']),p['diameter_mm'])
    return (k,p['ref'],p['net'],p['layer'],tuple(round(x,3) for x in p['centre']))
pt=lambda p:p['start'] if p['kind']=='track' else p['centre']
def zones(prims,b):
    o={}
    for p in prims:
        if p['kind']=='zone': o.setdefault((p['net'],p['layer']),[]).append(Polygon(p['shell'],p.get('holes') or []).buffer(0).intersection(b))
    return {k:unary_union(v) for k,v in o.items()}
old,new=load(sys.argv[1]),load(sys.argv[2])
for leg,(x0,y0,x1,y1) in LEG.items():
    m=20;b=box(x0-m,y0-m,x1+m,y1+m)
    ins=lambda p:(x0-m<=pt(p)[0]<=x1+m and y0-m<=pt(p)[1]<=y1+m)
    A={rec(p) for p in old if p['kind']!='zone' and ins(p)};B={rec(p) for p in new if p['kind']!='zone' and ins(p)}
    print(leg,'removed',len(A-B),'added',len(B-A))
    for r in sorted(A|B):
        if r[0]=='pad' and r[1].startswith('R5.'): print('  R5 pad',('old' if r in A else 'new'),r[1],r[2],r[4])
    zo,zn=zones(old,b),zones(new,b)
    for k in sorted(set(zo)|set(zn)):
        d=zo.get(k,Polygon()).symmetric_difference(zn.get(k,Polygon())).area
        if k in(('bus_p','In2.Cu'),('hv_ret','In1.Cu')): print('  zone',k,'symdiff mm2',round(d,2))
