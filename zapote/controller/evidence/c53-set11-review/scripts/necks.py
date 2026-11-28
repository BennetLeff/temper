# widest continuous F.Cu copper between two pads of a net (morphological opening); EN cap and buck pin gaps
from lib import *
def width(net,a,b):
    its=[k for k in netitems(net) if 'F.Cu' in k[1] and k[0] in('zone','pad','trk')]
    u=unary_union([k[2] for k in its]); P=lambda s:[k[2] for k in its if k[0]=='pad' and k[3]['ref']+'.'+k[3]['num']==s][0].centroid
    last=None
    for w in [0.3,0.5,0.8,1.0,1.2,1.4,1.6,1.7,1.9,2.0]:
        e=u.buffer(-w/2+1e-6).buffer(w/2-2e-6); parts=list(e.geoms) if hasattr(e,'geoms') else [e]
        ca=[i for i,p in enumerate(parts) if p.buffer(0.05).contains(P(a))]; cb=[i for i,p in enumerate(parts) if p.buffer(0.05).contains(P(b))]
        if not(ca and cb and ca[0]==cb[0]): break
        last=w
    print(net,a,'->',b,'continuous width >=',last,'mm')
for b in ('C9.1','C13.1','C14.1','C15.1'): width('V15_BLW','R15.1',b)
for n,a,b in [('V15_BLW','C14.1','U2.3'),('sw_12','U2.5','L2.1'),('sw_fan2','U51.5','L3.1'),('sw_3v3','U1.5','L1.1')]: width(n,a,b)
q=lambda r,n:[p for p in B['pads'] if p['ref']==r and p['num']==n][0]
for r,n,t in [('C91','1','3'),('R109','2','3'),('C89','1','2'),('C90','1','2')]:
    a=q(r,n); u=q('U4',t); print(r,a['net'],'to U4.%s: %.1f mm'%(t,math.dist((a['x'],a['y']),(u['x'],u['y']))))
