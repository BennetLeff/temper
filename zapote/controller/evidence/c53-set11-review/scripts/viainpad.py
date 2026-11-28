# M2: vias whose drilled hole touches an SMD pad, and via rings within 0.1 mm of one
from lib import *
from shapely.strtree import STRtree
smd=[p for p in B['pads'] if p['drill']==0 and p['attr']==1]
g=[padgeom(p) for p in smd]; tree=STRtree(g); inpad=0; near=0
for v in B['vias']:
    c=Point(v['x'],v['y']); ds=[g[int(j)].distance(c) for j in tree.query(c.buffer(0.6))]
    if not ds: continue
    d=min(ds)
    if d<0.15: inpad+=1
    elif d-0.3<0.1: near+=1
print('vias',len(B['vias']),'| drill (r 0.15) touching an SMD pad:',inpad,'| ring within 0.1 mm of an SMD pad:',near)
