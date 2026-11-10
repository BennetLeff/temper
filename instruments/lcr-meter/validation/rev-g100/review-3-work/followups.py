"""F.Fab references, dangling track ends, and the corridor geometry for the m0 fix (output work/followups.txt)."""
import sys; sys.path.insert(0,'work')
from lib_board import *
b=load(); P=pads(b); T=tracks(b); TR=[t for t in T if t['kind']=='track']; V=[t for t in T if t['kind']=='via']
print("== F.Fab reference text present in the board for the parts the earlier reviews named")
for fp in b.GetFootprints():
    r=fp.GetReference()
    if r in ('J3','J7','J8','J9','K1','K2','K3','K4','D4','U14','U13','J1'):
        fab=[it for it in list(fp.GraphicalItems())+[fp.Reference(),fp.Value()] if it.GetClass() in('PCB_TEXT','PCB_FIELD') and b.GetLayerName(it.GetLayer())=='F.Fab' and it.GetText() in (r,'${REFERENCE}')]
        print(f"  {r}: F.Fab ref items {len(fab)}; silk ref visible {fp.Reference().IsVisible() and b.GetLayerName(fp.Reference().GetLayer())=='F.Silkscreen'}")
print("== dangling track ends (end touches no pad, via, same-net track or filled zone)")
filler=pcbnew.ZONE_FILLER(b); filler.Fill(b.Zones())
LAY={'F.Cu':pcbnew.F_Cu,'In1.Cu':pcbnew.In1_Cu,'In2.Cu':pcbnew.In2_Cu,'B.Cu':pcbnew.B_Cu}
n=0
for t in TR:
    l=LAY[t['layer']]
    for e in (t['a'],t['b']):
        pt_=pcbnew.VECTOR2I(int(e[0]*1e6),int(e[1]*1e6)); ok=False
        for u in TR:
            if u is t or u['net']!=t['net'] or u['layer']!=t['layer']: continue
            if seg_dist(e,u['a'],u['b'])<=u['w']/2+0.001: ok=True;break
        if not ok:
            for v in V:
                if v['net']==t['net'] and dist(e,v['at'])<=v['dia']/2+0.001: ok=True;break
        if not ok:
            for p in P:
                if p['net']==t['net'] and (t['layer'] in p['layers']) and p['obj'].GetEffectiveShape(l).Collide(pt_, int(0.001*1e6)): ok=True;break
        if not ok:
            for z in b.Zones():
                if z.GetNetname()==t['net'] and not z.GetIsRuleArea() and z.IsOnLayer(l) and z.GetFilledPolysList(l).Contains(pt_): ok=True;break
        if not ok:
            n+=1; print(f"  {t['net']} {t['layer']} end ({e[0]:.3f},{e[1]:.3f}) of ({t['a'][0]:.2f},{t['a'][1]:.2f})-({t['b'][0]:.2f},{t['b'][1]:.2f}) w{t['w']}")
print(f"  {n} dangling ends")
print("== m0 corridor: J1 GND pad boxes (J1 is rotated -90) and the CC1 track beside the A4/B9 exit")
for p in P:
    if p['ref']=='J1' and p['net']=='GND':
        bb=p['obj'].GetBoundingBox(); print(f"  J1.{p['num']} GND bbox x {mm(bb.GetLeft()):.2f}-{mm(bb.GetRight()):.2f} y {mm(bb.GetTop()):.2f}-{mm(bb.GetBottom()):.2f}")
for t in TR:
    if t['net']=='CC1' and t['layer']=='F.Cu' and abs(t['a'][0]-58.86)<0.01: print(f"  CC1 F.Cu ({t['a'][0]:.2f},{t['a'][1]:.2f})-({t['b'][0]:.2f},{t['b'][1]:.2f}) w{t['w']}")
