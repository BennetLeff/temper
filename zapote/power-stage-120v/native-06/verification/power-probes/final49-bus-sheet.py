import json, numpy as np
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from shapely.prepared import prep
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve
j=json.load(open('/tmp/ps-finish/final49-copper.json'))
g=unary_union([Polygon(i['polygon']) for i in j['items'] if i['kind']=='zone' and i['net']=='bus_p' and 'In2.Cu' in i['layers']]);pg=prep(g)
h=.3;xs=np.arange(110,150.001,h);ys=np.arange(0.75,42.001,h)
valid={}; coords=[]
for i,x in enumerate(xs):
 for q,y in enumerate(ys):
  if pg.covers(Point(float(x),float(y))):valid[(i,q)]=len(coords);coords.append((i,q,x,y))
print('nodes',len(coords))
Rsheet=1.68e-8/70e-6 # ohms / square
G=1/Rsheet; n=len(coords);edges=[]
for (i,q),v in valid.items():
 for ij in ((i+1,q),(i,q+1)):
  if ij in valid:
   u=valid[ij];edges.append((v,u,G))
source={v for (i,q),v in valid.items() if i==0};sink={v for (i,q),v in valid.items() if i==len(xs)-1}
print('edges',len(edges),'source',len(source),'sink',len(sink))
for extraR in [None]:
 E=edges.copy()
 if extraR is not None:
  start=min(range(n),key=lambda k:(coords[k][2]-120)**2+(coords[k][3]-28)**2)
  end=min(range(n),key=lambda k:(coords[k][2]-144)**2+(coords[k][3]-22)**2)
  print('strap endpoints',coords[start],coords[end])
  E.append((start,end,1/extraR))
 known={v:1.0 for v in source}|{v:0.0 for v in sink}
 free=[v for v in range(n) if v not in known];inv={v:i for i,v in enumerate(free)}; A=lil_matrix((len(free),len(free)));b=np.zeros(len(free))
 for v,u,gu in E:
  if v in inv:
   k=inv[v];A[k,k]+=gu
   if u in inv:A[k,inv[u]]-=gu
   else:b[k]+=gu*known[u]
  if u in inv:
   k=inv[u];A[k,k]+=gu
   if v in inv:A[k,inv[v]]-=gu
   else:b[k]+=gu*known[v]
 V=np.zeros(n)
 for k,z in known.items():V[k]=z
 V[free]=spsolve(A.tocsr(),b)
 total=sum(gu*(V[v]-V[u]) if v in source else gu*(V[u]-V[v]) for v,u,gu in E if (v in source)^(u in source))
 cross=[]
 for v,u,gu in E[:-1] if extraR else E:
  iv,q,x,y=coords[v];iu,qu,xx,yy=coords[u]
  if x<=131.5<xx and q==qu:cross.append((y,gu*(V[v]-V[u])))
 strap=0 if extraR is None else (V[start]-V[end])/extraR
 scale=19/total
 from collections import defaultdict
 bands=defaultdict(float)
 for y,c in cross:
  bands['upper' if y<20 else 'middle' if y<34 else 'lower']+=c
 print('Rstrap_mOhm',None if extraR is None else extraR*1000,'totalconductance',round(total,1),'scaled19A: upper/middle/lower',[(k,round(v*scale,2)) for k,v in bands.items()],'strap',round(strap*scale,2),'balance',round((sum(bands.values())+strap)*scale,2))
 worst=[]
 for i in range(len(xs)-1):
  x=float((xs[i]+xs[i+1])/2)
  if not 120<=x<=149:continue
  z=g.intersection(__import__('shapely').geometry.LineString([(x,0),(x,45)]))
  strips=[s for s in (z.geoms if hasattr(z,'geoms') else [z]) if s.geom_type=='LineString' and s.length>.5]
  flow=[]
  for q,y in enumerate(ys):
   v=valid.get((i,q));u=valid.get((i+1,q))
   if v is not None and u is not None:flow.append((y,G*(V[v]-V[u])*scale))
  for s in strips:
   lo,hi=s.bounds[1],s.bounds[3];amp=sum(a for y,a in flow if lo-.2<=y<=hi+.2)
   cap=.024*20**.44*(s.length*39.3701*2*1.37)**.725
   worst.append((amp/cap,x,lo,hi,s.length,amp,cap))
 print('WORST_RATIO',sorted(worst,reverse=True)[:8])
