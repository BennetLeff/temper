# power path analysis: per net, source pad -> each sink pad: bottleneck width, bridge vias, layers
import sys,heapq
from lib import *
def analyse(net,src):
    items=netitems(net); adj=graph(items)
    def wid(i):
        k=items[i]
        if k[0]=='trk': return k[3]['w']
        if k[0]=='via': return 0.94  # circumference of 0.3 drill barrel (plating ~18-25um)
        return 99
    sidx=[i for i,k in enumerate(items) if k[0]=='pad' and (k[3]['ref'],k[3]['num'])==src]
    if not sidx: print('no src',src); return
    s=sidx[0]
    # widest path
    best={s:99}; prev={}; h=[(-99,s)]
    while h:
        b,i=heapq.heappop(h); b=-b
        if b<best.get(i,0): continue
        for j in adj[i]:
            nb=min(b,wid(j))
            if nb>best.get(j,0): best[j]=nb; prev[j]=i; heapq.heappush(h,(-nb,j))
    def reach(skip):
        seen={s}; st=[s]
        while st:
            i=st.pop()
            for j in adj[i]:
                if j not in seen and j not in skip: seen.add(j); st.append(j)
        return seen
    print('=== %s from %s.%s: %d items (%d trk, %d via, %d zonepoly)'%(net,src[0],src[1],len(items),sum(k[0]=='trk' for k in items),sum(k[0]=='via' for k in items),sum(k[0]=='zone' for k in items)))
    allr=reach(set())
    un=[k for i,k in enumerate(items) if i not in allr]
    if un: print('  NOT REACHED from src:',[(k[0],k[3].get('ref'),k[3].get('num'),k[3].get('x'),k[3].get('y'),k[3].get('name')) for k in un][:20])
    for i,k in enumerate(items):
        if k[0]!='pad' or i==s: continue
        path=[i]
        while path[-1]!=s and path[-1] in prev: path.append(prev[path[-1]])
        kinds=collections.Counter(items[j][0] for j in path)
        length=sum(math.hypot(items[j][3]['x2']-items[j][3]['x1'],items[j][3]['y2']-items[j][3]['y1']) for j in path if items[j][0]=='trk')
        narrow=[(items[j][3]['w'],items[j][3]['layer'],round(items[j][3]['x1'],2),round(items[j][3]['y1'],2)) for j in path if items[j][0]=='trk' and items[j][3]['w']<=best.get(i,0)+1e-6]
        # bridge vias: vias whose removal disconnects
        br=[]
        for j in path:
            if items[j][0]=='via' and i not in reach({j}): br.append((items[j][3]['x'],items[j][3]['y']))
        brt=[]
        for j in path:
            if items[j][0]=='trk' and i not in reach({j}): brt.append(items[j][3]['w'])
        print('  -> %s.%s (%.1f,%.1f) bottleneck %.2f; widest path: %s trkLen %.1f; single-via bridges %s; min bridging-track w %s; narrow@%s'%(k[3]['ref'],k[3]['num'],k[3]['x'],k[3]['y'],best.get(i,0),dict(kinds),length,br,min(brt) if brt else None,narrow[:2]))
if __name__=='__main__':
    for net,src in [('V15_BLW',('J13','1')),('v15_selv',('D9','1')),('V_BLOWER',('L2','2')),('V12_FAN2',('L3','2')),('sw_12',('U2','5')),('sw_3v3',('U1','5')),('sw_fan2',('U51','5'))]:
        analyse(net,src)
