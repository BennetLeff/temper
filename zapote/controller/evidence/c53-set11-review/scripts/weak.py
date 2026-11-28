# board-wide: does any net depend on a copper overlap narrower than TH (grazing contact)?
from lib import *
TH=0.10
def neck_ge(a,b,th):
    x=a.intersection(b)
    return (not x.is_empty) and (not x.buffer(-th/2).is_empty)
nets=sorted(set(p['net'] for p in B['pads'] if p['net']))
bad=[]
for net in nets:
    items=netitems(net); adj=graph(items)
    strong=collections.defaultdict(set); weak=[]
    for i in adj:
        for j in adj[i]:
            if j<i: continue
            if items[i][0]=='zone' or items[j][0]=='zone' or neck_ge(items[i][2],items[j][2],TH):
                strong[i].add(j); strong[j].add(i)
            else: weak.append((i,j))
    # components using strong edges only
    comp={}
    for s in range(len(items)):
        if s in comp: continue
        st=[s]; comp[s]=s
        while st:
            a=st.pop()
            for b in strong[a]:
                if b not in comp: comp[b]=s; st.append(b)
    ncomp=len(set(comp.values()))
    if ncomp>1:
        # which weak edges bridge different components
        br=[(i,j) for i,j in weak if comp[i]!=comp[j]]
        # ignore components that contain no pad and are pure leftovers? report all
        def d(i):
            k=items[i]
            return (k[0],k[3].get('ref','')+'.'+k[3].get('num','') if k[0]=='pad' else k[3].get('layer',''),round(k[3].get('x',k[3].get('x1',0)),2),round(k[3].get('y',k[3].get('y1',0)),2))
        sizes=collections.Counter(comp.values())
        bad.append((net,ncomp,[(d(i),d(j),sizes[comp[i]],sizes[comp[j]]) for i,j in br][:6]))
print('nets depending on a contact narrower than %.2f mm: %d of %d'%(TH,len(bad),len(nets)))
for b in bad: print(b)
