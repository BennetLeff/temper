import json, math, heapq, sys
B='/Users/bennet/Desktop/temper/worktrees/lcr-rev-g/instruments/lcr-meter/'
r=json.load(open(B+'cad/routing.json')); p=json.load(open(B+'build/pad-coordinates.json'))
net=sys.argv[1]; src=sys.argv[2]; dsts=sys.argv[3:]
rho=1.72e-8*(1+0.00393*40)
th={'F.Cu':35e-6,'B.Cu':35e-6,'In1.Cu':17.5e-6,'In2.Cu':17.5e-6}
G={}
def key(x,y,l): return (round(x,3),round(y,3),l)
nodes=[]
def add(a,b,R,info):
    G.setdefault(a,[]).append((b,R,info)); G.setdefault(b,[]).append((a,R,info))
tr=[t for t in r['tracks'] if t['net']==net]
cand=set()
for t in tr:
    for q in t['points']: cand.add((q[0],q[1]))
for v in r['vias']:
    if v['net']==net: cand.add(tuple(v['at']))
for ref in p:
    for pin,(x,y,n) in p[ref].items():
        if n==net: cand.add((x,y))
def split(pts):
    out=[pts[0]]
    for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
        L=math.hypot(x2-x1,y2-y1)
        mids=[]
        for (cx,cy) in cand:
            if L==0: break
            t_=((cx-x1)*(x2-x1)+(cy-y1)*(y2-y1))/L**2
            if 0.001<t_<0.999:
                d=abs((cx-x1)*(y2-y1)-(cy-y1)*(x2-x1))/L
                if d<0.05: mids.append((t_,x1+t_*(x2-x1),y1+t_*(y2-y1)))
        for _,mx,my in sorted(mids): out.append([mx,my])
        out.append([x2,y2])
    return out
for t in tr:
    pts=split(t['points'])
    for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
        L=math.hypot(x2-x1,y2-y1)*1e-3
        add(key(x1,y1,t['layer']),key(x2,y2,t['layer']),rho*L/(t['width']*1e-3*th[t['layer']]),(t['layer'],t['width'],round(L*1e3,2)))
allnodes=list(G.keys())
# vias connect all layers at a point
for v in r['vias']:
    if v['net']!=net: continue
    x,y=v['at']; ks=[k for k in allnodes if abs(k[0]-x)<0.02 and abs(k[1]-y)<0.02]
    for a in ks:
        for b in ks:
            if a!=b: add(a,b,0.001,('via',))
# join coincident / touching endpoints on same layer, and pads (SMD outer) 
def near(x,y,layer,tol):
    return [k for k in allnodes if k[2]==layer and abs(k[0]-x)<=tol and abs(k[1]-y)<=tol]
for a in allnodes:
    for b in near(a[0],a[1],a[2],0.01):
        if a!=b: add(a,b,0.0,('join',))
def padnode(ref,pin):
    x,y,n=p[ref][pin]; k=('PAD',ref,pin)
    for l in ('F.Cu','B.Cu'):
        for b in near(x,y,l,0.6): add(k,b,0.0,('pad',))
    return k
s=padnode(*src.split('.'))
ds=[(float(d.split(',')[0]),float(d.split(',')[1]),'B.Cu') if ',' in d else padnode(*d.split('.')) for d in dsts]
dist={s:0}; prev={}; pq=[(0,str(s),s)]
while pq:
    d,_,u=heapq.heappop(pq)
    if d>dist.get(u,1e9): continue
    for v,R,info in G.get(u,[]):
        nd=d+R
        if nd<dist.get(v,1e9): dist[v]=nd; prev[v]=(u,info); heapq.heappush(pq,(nd,str(v),v))
for d,name in zip(ds,dsts):
    print(name, 'R=%.1f mOhm'%(dist.get(d,float('nan'))*1e3))
    # path summary
    path=[];u=d
    while u in prev: u,info=prev[u]; path.append((u,info))
    segs=[i for _,i in path if i[0] not in ('join','pad','via')]
    print('  segments',len(segs),'length mm',round(sum(i[2] for i in segs),1), 'widths', sorted(set((i[0],i[1]) for i in segs)))
