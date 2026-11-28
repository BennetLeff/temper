# usage: render.py x0 y0 x1 y1 out.png layers(comma) [netfilter]
import sys
from lib import *
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MP, Circle
from matplotlib.collections import PatchCollection
x0,y0,x1,y1=map(float,sys.argv[1:5]); out=sys.argv[5]; layers=sys.argv[6].split(',')
hl=sys.argv[7].split(',') if len(sys.argv)>7 else []
view=box(x0,y0,x1,y1)
col={'F.Cu':'#c83232','In1.Cu':'#7fc87f','In2.Cu':'#c8a000','In3.Cu':'#c864c8','In4.Cu':'#00a0a0','B.Cu':'#3250c8'}
W=(x1-x0); H=(y1-y0); sc=min(16/W,11/H)
fig,ax=plt.subplots(figsize=(W*sc,H*sc),dpi=110)
def draw(g,c,a,z,ec=None):
    if g.is_empty: return
    gs=g.geoms if hasattr(g,'geoms') else [g]
    for p in gs:
        if p.geom_type!='Polygon': continue
        import numpy as np
        from matplotlib.path import Path
        from matplotlib.patches import PathPatch
        verts=[];codes=[]
        for ring in [p.exterior]+list(p.interiors):
            xy=list(ring.coords); verts+=xy; codes+=[Path.MOVETO]+[Path.LINETO]*(len(xy)-2)+[Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts,codes),fc=c,alpha=a,ec=ec,lw=0.3,zorder=z))
for li,l in enumerate(layers):
    c=col[l]
    for z in B['zones']:
        for ll,ps in z['fills'].items():
            if ll!=l: continue
            for ext,holes in ps:
                pg=Polygon(ext,holes).buffer(0)
                if pg.intersects(view): draw(pg.intersection(view), c if z['net'] not in hl else '#00ff00',0.25,1+li)
    for t in B['tracks']:
        if t['layer']==l:
            g=trackgeom(t)
            if g.intersects(view): draw(g,c if t['net'] not in hl else '#00dd00',0.75,10+li)
for p in B['pads']:
    if any(l in p['layers'] for l in layers) or True:
        g=padgeom(p)
        if g.intersects(view):
            draw(g,'#888888' if p['net'] not in hl else '#00aa00',0.6,20,ec='k')
            if p['drill']>0: ax.add_patch(Circle((p['x'],p['y']),p['drill']/2,fc='w',ec='k',lw=0.3,zorder=22))
            if W<45: ax.text(p['x'],p['y'],p['num']+'\n'+p['net'][-10:],fontsize=3.5 if W>25 else 5,ha='center',va='center',zorder=30)
for v in B['vias']:
    if x0<=v['x']<=x1 and y0<=v['y']<=y1:
        ax.add_patch(Circle((v['x'],v['y']),v['d']/2,fc='#444' if v['net'] not in hl else '#0a0',ec='k',lw=0.2,alpha=0.6,zorder=24)); ax.add_patch(Circle((v['x'],v['y']),v['drill']/2,fc='w',lw=0,zorder=25))
        if W<25: ax.text(v['x'],v['y']+0.35,v['net'][-8:],fontsize=3,ha='center',zorder=30,color='b')
for f in B['fps']:
    if x0<=f['x']<=x1 and y0<=f['y']<=y1: ax.text(f['x'],f['y'],f['ref'],fontsize=6,color='k',ha='center',va='center',zorder=40,bbox=dict(fc='w',alpha=0.5,lw=0,pad=0.2))
for d in B['drawings']:
    if d['layer']=='Edge.Cuts':
        if d.get('shape')=='Circle': ax.add_patch(Circle((d['x1'],d['y1']),d['r'],fc='none',ec='k',zorder=50))
        else: ax.plot([d['x1'],d['x2']],[d['y1'],d['y2']],'k-',lw=1,zorder=50)
ax.set_xlim(x0,x1); ax.set_ylim(y1,y0); ax.set_aspect('equal'); ax.grid(True,lw=0.2); ax.tick_params(labelsize=6)
plt.tight_layout(); plt.savefig(out); print(out)
