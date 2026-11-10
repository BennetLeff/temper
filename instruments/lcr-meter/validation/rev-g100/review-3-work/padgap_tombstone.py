"""(1) Copper gap between pads of different parts < 0.3 mm (JLC SMT spacing). (2) Tombstoning risk: two-pad
0402/0603 parts whose two pads see very different copper (sum of attached track widths, or one pad on a wide trunk)."""
import sys; sys.path.insert(0,'work')
from lib_board import *
b=load(); P=pads(b); T=[t for t in tracks(b) if t['kind']=='track']
out=["== pad-to-pad copper gap between different parts < 0.30 mm (F.Cu)"]
smd=[p for p in P if 'F.Cu' in p['layers'] and not p['ref'].startswith(('TP','FID','H'))]
for i in range(len(smd)):
    for j in range(i+1,len(smd)):
        a,c=smd[i],smd[j]
        if a['ref']==c['ref']: continue
        if dist(a['at'],c['at'])>4: continue
        sa=a['obj'].GetEffectiveShape(pcbnew.F_Cu); sc=c['obj'].GetEffectiveShape(pcbnew.F_Cu)
        r=sa.Collide(sc, int(0.30*1e6))
        if r:
            # find actual distance by bisection
            lo,hi=0.0,0.30
            for _ in range(10):
                m=(lo+hi)/2
                if sa.Collide(sc,int(m*1e6)): hi=m
                else: lo=m
            out.append(f"  {a['ref']}.{a['num']}({a['net']}) - {c['ref']}.{c['num']}({c['net']}): {hi:.2f} mm")
out.append("== tombstone: 2-pad parts, copper attached per pad (sum of track widths entering, mm) ratio > 3")
from collections import defaultdict
byref=defaultdict(list)
for p in smd: byref[p['ref']].append(p)
for ref,ps in byref.items():
    if len(ps)!=2: continue
    fp=ps[0]['fp']; name=str(fp.GetFPID().GetLibItemName())
    if not any(s in name for s in ('0402','0603','0805','SOD')): continue
    ws=[]
    for p in ps:
        bb=p['obj'].GetBoundingBox(); x1,y1,x2,y2=mm(bb.GetLeft()),mm(bb.GetTop()),mm(bb.GetRight()),mm(bb.GetBottom())
        w=0
        for t in T:
            if t['net']!=p['net'] or t['layer']!='F.Cu': continue
            for e,o in ((t['a'],t['b']),(t['b'],t['a'])):
                if x1-0.01<=e[0]<=x2+0.01 and y1-0.01<=e[1]<=y2+0.01 and not(x1-0.01<=o[0]<=x2+0.01 and y1-0.01<=o[1]<=y2+0.01):
                    w+=t['w']
        ws.append(w)
    if max(ws)>0 and (min(ws)==0 or max(ws)/max(min(ws),1e-9)>3):
        out.append(f"  {ref} {fp.GetValue()[:16]:16s} {name[:22]:22s} at ({ps[0]['fp'].GetPosition().x/1e6:.2f},{ps[0]['fp'].GetPosition().y/1e6:.2f}) pad1 {ws[0]:.2f} pad2 {ws[1]:.2f}  nets {ps[0]['net']}/{ps[1]['net']}")
open('work/padgap_tombstone.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
