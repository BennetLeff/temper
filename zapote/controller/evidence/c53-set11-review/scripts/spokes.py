from lib import *
fills={}
for l in CU:
    for net in ('selv_gnd','v3v3','V15_BLW'):
        zp=[p for _,_,p in zonepolys(net,l)]
        if zp: fills[(net,l)]=unary_union(zp)
rows=[]
for p in B['pads']:
    if p['drill']<=0 or p['attr']!=0 or p['net'] not in('selv_gnd','v3v3','V15_BLW'): continue
    if p['ref']=='U4': continue
    pg=padgeom(p); hole=Point(p['x'],p['y']).buffer(p['drill']/2)
    res={}
    for l in CU:
        f=fills.get((p['net'],l))
        if f is None: continue
        outer=l in('F.Cu','B.Cu')
        base=pg if outer else hole.buffer(0.25)   # inner layers: pad may be removed; ring near the barrel
        ring=base.buffer(0.17).difference(base.buffer(0.13))
        x=f.intersection(ring)
        n=0 if x.is_empty else (len(x.geoms) if hasattr(x,'geoms') else 1)
        frac=x.area/ring.area
        # track connections on this layer
        nt=sum(1 for t in B['tracks'] if t['net']==p['net'] and t['layer']==l and trackgeom(t).intersects(pg))
        res[l]=('solid' if frac>0.95 else '%d spokes'%n)+('+%dtrk'%nt if nt else '')
    rows.append((p['ref']+'.'+p['num'],p['net'],res))
for r in rows: print(r[0],r[1],r[2])
