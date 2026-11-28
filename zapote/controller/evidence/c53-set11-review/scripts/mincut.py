# min-cut (sum of copper width, mm of 1-oz-equivalent) between a source pad and target pads on a net.
# node capacity: track = width * (1.0 outer | 0.43 inner 0.5oz); via = 0.55 (pi*0.3*0.02/0.035); zone/pad = inf
import sys, networkx as nx
from lib import *
net=sys.argv[1]; s=sys.argv[2].split('.'); targets=sys.argv[3].split(',')
items=netitems(net); adj=graph(items)
def cap(k):
    if k[0]=='trk': return k[3]['w']*(1.0 if k[3]['layer'] in('F.Cu','B.Cu') else 0.43)
    if k[0]=='via': return 0.55
    return 1e9
G=nx.DiGraph()
for i,k in enumerate(items): G.add_edge(('i',i),('o',i),capacity=cap(k))
for i in adj:
    for j in adj[i]: G.add_edge(('o',i),('i',j),capacity=1e9)
def pid(ref,num): return [i for i,k in enumerate(items) if k[0]=='pad' and k[3]['ref']==ref and k[3]['num']==num][0]
src=pid(*s)
def desc(i):
    k=items[i]
    if k[0]=='trk': return 'trk %s w%.2f (%.1f,%.1f)-(%.1f,%.1f)'%(k[3]['layer'],k[3]['w'],k[3]['x1'],k[3]['y1'],k[3]['x2'],k[3]['y2'])
    if k[0]=='via': return 'via (%.1f,%.1f)'%(k[3]['x'],k[3]['y'])
    return k[0]
for t in targets:
    r,n=t.split('.'); ti=pid(r,n)
    val,(S,T)=nx.minimum_cut(G,('o',src),('i',ti))
    cut=[i for i in range(len(items)) if ('i',i) in S and ('o',i) in T]
    print('%s: min cut %.2f mm 1oz-equivalent through %d items: %s'%(t,val,len(cut),[desc(i) for i in cut][:8]))
