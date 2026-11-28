# resistance of the routed copper between two pads on a net (shortest-resistance path; tracks only)
import sys, networkx as nx
from lib import *
RS={'F.Cu':0.49e-3,'B.Cu':0.49e-3,'In1.Cu':1.13e-3,'In2.Cu':1.13e-3,'In3.Cu':1.13e-3,'In4.Cu':1.13e-3}  # ohm/sq at 20C (35um, 15.2um)
def run(net,a,b):
    items=netitems(net); adj=graph(items)
    G=nx.Graph()
    def r(i):
        k=items[i]
        if k[0]=='trk': t=k[3]; return RS[t['layer']]*math.hypot(t['x2']-t['x1'],t['y2']-t['y1'])/t['w']
        if k[0]=='via': return 0.7e-3
        return 0
    for i in adj:
        for j in adj[i]: G.add_edge(i,j,weight=(r(i)+r(j))/2)
    pid=lambda s:[i for i,k in enumerate(items) if k[0]=='pad' and k[3]['ref']+'.'+k[3]['num']==s][0]
    p=nx.shortest_path(G,pid(a),pid(b),weight='weight')
    R=sum(r(i) for i in p); L=collections.defaultdict(float)
    for i in p:
        if items[i][0]=='trk': t=items[i][3]; L[(t['layer'],t['w'])]+=math.hypot(t['x2']-t['x1'],t['y2']-t['y1'])
    d=math.dist((items[p[0]][3]['x'],items[p[0]][3]['y']),(items[p[-1]][3]['x'],items[p[-1]][3]['y']))
    print('%s %s->%s: straight %.1f mm, routed %.1f mm %s, vias %d, R(20C) = %.0f mOhm'%(net,a,b,d,sum(L.values()),{k:round(v,1) for k,v in L.items()},sum(items[i][0]=='via' for i in p),R*1e3))
    return p,items
for a in sys.argv[1:]:
    net,x,y=a.split(','); run(net,x,y)
