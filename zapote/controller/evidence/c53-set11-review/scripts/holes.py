from lib import *
import itertools
holes=[]
for v in B['vias']: holes.append((v['x'],v['y'],v['drill'],'via',v['net'],''))
for p in B['pads']:
    if p['drill']>0: holes.append((p['x'],p['y'],p['drill'],'pad' if p['attr']==0 else 'npth',p['net'],p['ref']+'.'+p['num']))
mh=[(d['x1'],d['y1'],d['r']*2) for d in B['drawings'] if d['layer']=='Edge.Cuts' and d.get('shape')=='Circle']
for m in mh: holes.append((m[0],m[1],m[2],'mount','',''))
print(len(holes),'holes;',collections.Counter(h[3] for h in holes))
import numpy as np
from scipy.spatial import cKDTree
P=np.array([(h[0],h[1]) for h in holes]); T=cKDTree(P)
res=[]
for i,j in T.query_pairs(4.0):
    d=math.dist(P[i],P[j])-holes[i][2]/2-holes[j][2]/2
    res.append((d,holes[i],holes[j]))
res.sort(key=lambda r:r[0])
print('closest hole wall-to-wall:')
for r in res[:12]: print('  %.3f'%r[0],r[1],r[2])
print('pairs <0.5:',sum(r[0]<0.5-1e-6 for r in res),' via-via <0.25:',sum(r[0]<0.25 for r in res))
# different-net close vias
dn=[r for r in res if r[1][4]!=r[2][4]]
print('closest different-net hole pairs:'); 
for r in dn[:6]: print('  %.3f'%r[0],r[1],r[2])
# edge distance
ed=sorted((min(h[0]-20,226-h[0],h[1]-20,96-h[1])-h[2]/2,h) for h in holes)
print('hole wall to board edge min:',ed[:6])
# mount holes: nearest copper
for m in mh:
    c=Point(m[0],m[1]); best=[]
    for t in B['tracks']:
        d=trackgeom(t).distance(c)
        best.append((d,'trk',t['net'],t['layer']))
    for v in B['vias']: best.append((math.dist((v['x'],v['y']),m[:2])-v['d']/2,'via',v['net'],''))
    for p in B['pads']: best.append((padgeom(p).distance(c),'pad',p['ref']+'.'+p['num'],p['net']))
    for nm,l,pg in zonepolys(): best.append((pg.distance(c),'zone',nm,l))
    best.sort()
    fp=sorted((box(*f['cy']).distance(c),f['ref']) for f in B['fps'] if f['cy'])
    print('mount (%.0f,%.0f) world (%.0f,%.0f): nearest copper %.2f mm from centre %s; nearest courtyard %.2f %s; edge dist %.1f'%(m[0],m[1],m[0]-58,110-m[1],best[0][0],best[0][1:],fp[0][0],fp[0][1],min(m[0]-20,226-m[0],m[1]-20,96-m[1])))
