"""Jack band clearance: smallest copper gap, on every copper layer, between each jack-side net (the nets that can sit
at +-50 V from a charged DUT: JK_*, JACK_*, the TVS/BAV99 and the photoMOS jack-side pins) and any other net.
Uses KiCad effective shapes (pads, tracks, vias, filled zones). Output work/jackband.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
b=load(); filler=pcbnew.ZONE_FILLER(b); filler.Fill(b.Zones())
nets=set(n for n in b.GetNetInfo().NetsByName()) 
jack=[n for n in map(str,nets) if n.startswith(('JK_','JACK_')) or n in ('HCUR','HPOT','LPOT','LCUR')]
print('jack nets:', jack)
items=[]
for t in b.GetTracks(): items.append(t)
for fp in b.GetFootprints():
    for pd in fp.Pads(): items.append(pd)
for z in b.Zones():
    if not z.GetIsRuleArea(): items.append(z)
LAY={'F.Cu':pcbnew.F_Cu,'In1.Cu':pcbnew.In1_Cu,'In2.Cu':pcbnew.In2_Cu,'B.Cu':pcbnew.B_Cu}
def shape(it,l):
    if it.GetClass()=='ZONE':
        if not it.IsOnLayer(l): return None
        return it.GetFilledPolysList(l) if it.GetFilledPolysList(l).OutlineCount() else None
    if not it.IsOnLayer(l): return None
    return it.GetEffectiveShape(l)
def desc(it):
    c=it.GetClass()
    if c=='PAD': return f"{it.GetParentFootprint().GetReference()}.{it.GetNumber()}"
    if c=='ZONE': return "zone"
    if c=='PCB_VIA': return f"via({mm(it.GetPosition().x):.2f},{mm(it.GetPosition().y):.2f})"
    return f"track({mm(it.GetStart().x):.2f},{mm(it.GetStart().y):.2f})-({mm(it.GetEnd().x):.2f},{mm(it.GetEnd().y):.2f})"
out=[]
LIM=0.6
for jn in sorted(jack):
    ji=[it for it in items if it.GetNetname()==jn]
    best={}
    for ln,l in LAY.items():
        for a in ji:
            sa=shape(a,l)
            if sa is None: continue
            bba=a.GetBoundingBox()
            for c in items:
                if c.GetNetname()==jn: continue
                if c.GetClass()!='ZONE':
                    bbc=c.GetBoundingBox()
                    if bbc.GetLeft()>bba.GetRight()+LIM*1e6 or bbc.GetRight()<bba.GetLeft()-LIM*1e6 or bbc.GetTop()>bba.GetBottom()+LIM*1e6 or bbc.GetBottom()<bba.GetTop()-LIM*1e6: continue
                sc=shape(c,l)
                if sc is None: continue
                if c.GetClass()=='ZONE':
                    if a.GetClass()=='ZONE': continue
                    coll = sc.Collide(sa, int(LIM*1e6))
                else:
                    coll = sa.Collide(sc, int(LIM*1e6)) if a.GetClass()!='ZONE' else sc.Collide(sa,int(LIM*1e6))
                if coll:
                    lo,hi=0.0,LIM
                    for _ in range(9):
                        m=(lo+hi)/2
                        cm = (sc.Collide(sa,int(m*1e6)) if (c.GetClass()=='ZONE' or a.GetClass()=='ZONE') else sa.Collide(sc,int(m*1e6)))
                        if cm: hi=m
                        else: lo=m
                    k=(ln,c.GetNetname())
                    if k not in best or hi<best[k][0]: best[k]=(hi,desc(a),desc(c))
    for (ln,on),(d,da,dc) in sorted(best.items(), key=lambda kv: kv[1][0]):
        if d<0.45: out.append(f"{jn:10s} {ln:7s} to {on:14s} {d:.2f} mm  {da} <-> {dc}")
open('work/jackband.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
