# independent connectivity: every net one component; netlist pads vs board pads
from lib import *
nets=sorted(set(p['net'] for p in B['pads'] if p['net']))
bad=0
# netlist compare
bp={(p['ref'],p['num']):p['net'] for p in B['pads'] if p['num']}
nl={(r,pn):n for n,nodes in N['nets'].items() for r,pn,f in nodes}
diff=[(k,bp.get(k),nl.get(k)) for k in set(bp)|set(nl) if (bp.get(k) or None)!=(nl.get(k)) and not (bp.get(k,'')=='' and k not in nl) and not str(bp.get(k,'')).startswith('unconnected')]
print('pad-net diffs vs frozen netlist:',len(diff),diff[:20])
print('board pads with no net:',sorted([k for k,v in bp.items() if not v])[:60])
for net in nets:
    items=netitems(net); adj=graph(items)
    seen=set(); comps=[]
    for i in range(len(items)):
        if i in seen: continue
        st=[i]; seen.add(i); c=[i]
        while st:
            a=st.pop()
            for b in adj[a]:
                if b not in seen: seen.add(b); st.append(b); c.append(b)
        comps.append(c)
    if len(comps)>1:
        bad+=1
        comps.sort(key=len,reverse=True)
        print(net,'components:',[len(c) for c in comps])
        for c in comps[1:6]:
            print('    ',[(items[i][0],items[i][3].get('ref',''),items[i][3].get('num',''),round(items[i][3].get('x',items[i][3].get('x1',0)),2),round(items[i][3].get('y',items[i][3].get('y1',0)),2),items[i][3].get('layer',items[i][3].get('name',''))) for i in c[:6]])
print('nets',len(nets),'split nets',bad)
