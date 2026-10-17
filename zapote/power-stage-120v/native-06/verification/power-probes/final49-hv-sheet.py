import json,collections
import numpy as np
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union
from shapely.prepared import prep
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve
j=json.load(open('/tmp/ps-finish/final49-copper.json'))
g=unary_union([Polygon(i['polygon']) for i in j['items'] if i['kind']=='zone' and i['net']=='hv_ret' and 'In1.Cu' in i['layers']]);pg=prep(g)
h=.25;xs=np.arange(76,100.0001,h);ys=np.arange(10,42.0001,h)
valid={};coords=[]
for i,x in enumerate(xs):
 for q,y in enumerate(ys):
  if pg.covers(Point(float(x),float(y))):valid[(i,q)]=len(coords);coords.append((i,q,x,y))
print('nodes',len(coords))
parent=list(range(len(coords)))
def find(x):
 while parent[x]!=x:
  parent[x]=parent[parent[x]];x=parent[x]
 return x
def union(a,b):
 ra,rb=find(a),find(b)
 if ra!=rb:parent[rb]=ra
edges=[];G=1/(1.68e-8/70e-6)
for (i,q),v in valid.items():
 for k in [(i+1,q),(i,q+1)]:
  if k in valid:
   u=valid[k];edges.append((v,u,G));union(v,u)
cc=collections.defaultdict(set)
for i,v in enumerate(coords):cc[find(i)].add(i)
active=set();summ=[]
for key,vs in cc.items():
 a={v for v in vs if coords[v][0]==0};b={v for v in vs if coords[v][0]==len(xs)-1}
 if a and b:active|=vs;summ.append((len(vs),len(a),len(b)))
print('source-sink-components',summ,'active',len(active),'edges',len(edges))
source={v for v in active if coords[v][0]==0};sink={v for v in active if coords[v][0]==len(xs)-1};known={v:1.0 for v in source}|{v:0.0 for v in sink}
free=[v for v in active if v not in known];idx={v:i for i,v in enumerate(free)};A=lil_matrix((len(free),len(free)));rhs=np.zeros(len(free))
for v,u,gu in edges:
 if v not in active or u not in active:continue
 for a,b in [(v,u),(u,v)]:
  if a not in idx:continue
  k=idx[a];A[k,k]+=gu
  if b in idx:A[k,idx[b]]-=gu
  else:rhs[k]+=gu*known[b]
V=np.zeros(len(coords))
for k,z in known.items():V[k]=z
V[free]=spsolve(A.tocsr(),rhs)
total=sum(gu*(V[v]-V[u]) if v in source else gu*(V[u]-V[v]) for v,u,gu in edges if v in active and u in active and ((v in source)^(u in source)))
print('conductance',total,'scale to15A',15/total)
flow=collections.defaultdict(list)
for v,u,gu in edges:
 if v not in active or u not in active:continue
 i,q,x,y=coords[v];ii,qq,xx,yy=coords[u]
 if ii==i+1 and q==qq:flow[round((x+xx)/2,3)].append((y,gu*(V[v]-V[u])*15/total))
worst=[]
for x in sorted(flow):
 line=g.intersection(LineString([(x,10),(x,42)]));segs=[z for z in (line.geoms if hasattr(line,'geoms') else [line]) if z.geom_type=='LineString' and z.length>.5]
 for s in segs:
  lo,hi=s.bounds[1],s.bounds[3];amp=sum(c for y,c in flow[x] if lo-.13<=y<=hi+.13)
  cap=.024*20**.44*(s.length*39.3701*2*1.37)**.725
  if abs(amp)>.1:worst.append((amp/cap,x,lo,hi,s.length,amp,cap))
for x in [76.125,80.125,84.125,86.125,88.125,90.125,92.125,96.125,99.125]:
 print('X',x,[tuple(round(v,2) for v in z) for z in worst if abs(z[1]-x)<.001])
print('WORST',sorted(worst,reverse=True)[:12])
