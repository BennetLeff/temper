from lib import *
import heapq,sys
net=sys.argv[1]; srcref=sys.argv[2].split('.'); targets=sys.argv[3].split(',') if len(sys.argv)>3 else None
verbose=len(sys.argv)>4
items=netitems(net); adj=graph(items)
src=[i for i,k in enumerate(items) if k[0]=='pad' and k[3]['ref']==srcref[0] and k[3]['num']==srcref[1]][0]
def wid(i):
    k=items[i]
    return k[3]['w'] if k[0]=='trk' else (0.94 if k[0]=='via' else 99)
best={src:99}; prev={}; h=[(-99,src)]
while h:
    b,i=heapq.heappop(h); b=-b
    if b<best.get(i,0): continue
    for j in adj[i]:
        nb=min(b,wid(j))
        if nb>best.get(j,0): best[j]=nb; prev[j]=i; heapq.heappush(h,(-nb,j))
def reach(skip):
    seen={src}; st=[src]
    while st:
        i=st.pop()
        for j in adj[i]:
            if j not in seen and j not in skip: seen.add(j); st.append(j)
    return seen
def desc(i):
    k=items[i]
    if k[0]=='pad': return 'pad %s.%s'%(k[3]['ref'],k[3]['num'])
    if k[0]=='trk': return 'trk %s w%.2f (%.1f,%.1f)-(%.1f,%.1f)'%(k[3]['layer'],k[3]['w'],k[3]['x1'],k[3]['y1'],k[3]['x2'],k[3]['y2'])
    if k[0]=='via': return 'via (%.1f,%.1f)'%(k[3]['x'],k[3]['y'])
    return 'zone %s %s %.0fmm2'%(k[3]['name'],k[3]['layer'],k[2].area)
# articulation: for each target, single items whose removal disconnects (non-zone-main)
for i,k in enumerate(items):
    if k[0]!='pad' or i==src: continue
    name=k[3]['ref']+'.'+k[3]['num']
    if targets and name not in targets and k[3]['ref'] not in targets: continue
    path=[i]
    while path[-1]!=src: path.append(prev[path[-1]])
    path=path[::-1]
    arts=[j for j in path[1:-1] if i not in reach({j})]
    tl=collections.defaultdict(float)
    for j in path:
        if items[j][0]=='trk': t=items[j][3]; tl[(t['layer'],t['w'])]+=math.hypot(t['x2']-t['x1'],t['y2']-t['y1'])
    print('%s bottleneck %.2f | path trk %s vias %d | single points of failure/constriction: %s'%(name,best[i],{k:round(v,1) for k,v in tl.items()},sum(items[j][0]=='via' for j in path),[desc(j) for j in arts if items[j][0]!='zone' or items[j][2].area<2000][:8]))
    if verbose:
        for j in path: print('      ',desc(j))
