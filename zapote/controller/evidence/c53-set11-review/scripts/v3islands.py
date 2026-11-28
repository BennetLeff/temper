from lib import *
net='v3v3'
items=netitems(net); adj=graph(items)
src=[i for i,k in enumerate(items) if k[0]=='pad' and k[3]['ref']=='L1'][0]
def reach(skip,start=src):
    seen={start}; st=[start]
    while st:
        i=st.pop()
        for j in adj[i]:
            if j not in seen and j not in skip: seen.add(j); st.append(j)
    return seen
full=reach(set())
zs=[i for i,k in enumerate(items) if k[0]=='zone']
zs.sort(key=lambda i:-items[i][2].area)
main=zs[0]
print('L1.2 on main plane?', main in adj[src], 'L1 pad neighbors:',[(items[j][0],items[j][3].get('w'),items[j][3].get('layer')) for j in adj[src]])
def desc(i):
    k=items[i]
    if k[0]=='pad': return 'pad %s.%s'%(k[3]['ref'],k[3]['num'])
    if k[0]=='trk': return 'trk %s w%.2f (%.1f,%.1f)-(%.1f,%.1f)'%(k[3]['layer'],k[3]['w'],k[3]['x1'],k[3]['y1'],k[3]['x2'],k[3]['y2'])
    if k[0]=='via': return 'via (%.1f,%.1f)'%(k[3]['x'],k[3]['y'])
    return 'zone %s %.0fmm2'%(k[3]['layer'],k[2].area)
for z in zs[1:]:
    k=items[z]; b=k[2].bounds
    r=reach({z})
    lost=[i for i in full if i not in r and i!=z]
    lostpads=[desc(i) for i in lost if items[i][0]=='pad']
    # feeders: island vias from which source reachable without island
    feeders=[j for j in adj[z] if j in r]
    # is main reachable w/o island? yes (src). bottleneck of feed: for each feeder via, tracks attached
    print('ISLAND %s %.1fmm2 bbox(%.1f,%.1f,%.1f,%.1f): %d attached items, %d feeders (connect onward to source without island); loads only via island: %s'%(k[3]['layer'],k[2].area,*b,len(adj[z]),len(feeders),lostpads))
    for f in feeders:
        print('      feeder',desc(f),'->',[desc(j) for j in adj[f] if j!=z][:4])
