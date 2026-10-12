#!/usr/bin/env python3
"""Plot a copper-dump window per layer (RES_A red, SELV green, PE lime, other HOT orange; pads drawn on every panel).

    python3 plot_window18.py COPPER_DUMP.json OUT.png X0 Y0 X1 Y1 B.Cu[,F.Cu]
"""
import json,sys
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from shapely.geometry import Polygon,LineString,Point
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'native-21/layout'))
import rules21
d=json.load(open(sys.argv[1])); x0,y0,x1,y1=map(float,sys.argv[3:7]); lays=sys.argv[7].split(',')
fig,axs=plt.subplots(1,len(lays),figsize=(9*len(lays),9*(y1-y0)/(x1-x0)+1))
if len(lays)==1: axs=[axs]
def col(n):
    if n=='res_a': return 'red'
    dm=rules21.domain(n)
    return {'SELV':'green','PE':'lime','HOT':'orange'}.get(dm,'gray')
for ax,lay in zip(axs,lays):
    for z in d['zones']:
        if z['layer']!=lay: continue
        p=Polygon(z['pts'],z['holes'])
        if not p.intersects(Polygon([(x0,y0),(x1,y0),(x1,y1),(x0,y1)])): continue
        xs,ys=p.exterior.xy; ax.fill(xs,ys,color=col(z['net']),alpha=.35,lw=0)
        c=p.intersection(Polygon([(x0,y0),(x1,y0),(x1,y1),(x0,y1)])).representative_point(); ax.text(c.x,c.y,z['net'],fontsize=6)
    for t in d['tracks']:
        if t['layer']!=lay: continue
        ax.plot([t['a'][0],t['b'][0]],[t['a'][1],t['b'][1]],color=col(t['net']),lw=max(.5,t['w']*3))
    for v in d['vias']:
        ax.add_patch(plt.Circle(v['at'],v['d']/2,color=col(v['net'])))
    for p in d['pads']:
        xs=[q[0] for q in p['pts']]; ys=[q[1] for q in p['pts']]
        if min(xs)>x1 or max(xs)<x0 or min(ys)>y1 or max(ys)<y0: continue
        ax.fill(xs,ys,color=col(p['net']) if p['net'] else 'k',alpha=.7 if (p['tht'] or True) else .3)
        ax.text(sum(xs)/len(xs),sum(ys)/len(ys),p['ref'],fontsize=5)
    ax.set_xlim(x0,x1); ax.set_ylim(y1,y0); ax.set_aspect('equal'); ax.set_title(lay); ax.grid(lw=.3)
plt.savefig(sys.argv[2],dpi=110,bbox_inches='tight')
