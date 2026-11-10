"""Crystal, USB pair, ESD diode placement, pour islands, acute junctions. Output work/signals.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
from collections import defaultdict
b=load(); P=pads(b); T=tracks(b); TR=[t for t in T if t['kind']=='track']; V=[t for t in T if t['kind']=='via']
out=[]
def near_nets(net, lim=0.6):
    res={}
    for t in TR:
        if t['net']!=net: continue
        for u in TR:
            if u['net']==net or u['layer']!=t['layer'] or u['net']=='GND': continue
            d=min(seg_dist(t['a'],u['a'],u['b']),seg_dist(t['b'],u['a'],u['b']),seg_dist(u['a'],t['a'],t['b']),seg_dist(u['b'],t['a'],t['b']))-(t['w']+u['w'])/2
            if d<lim:
                k=(u['net'],u['layer'])
                if k not in res or d<res[k][0]: res[k]=(d,t['a'])
    return res
out.append("== crystal: XIN / XOUT tracks and nearby nets (edge gap < 0.6 mm, same layer)")
for n in ('XIN','XOUT'):
    for t in TR:
        if t['net']==n: out.append(f"  {n} {t['layer']} ({t['a'][0]:.2f},{t['a'][1]:.2f})-({t['b'][0]:.2f},{t['b'][1]:.2f}) w{t['w']}")
    for v in V:
        if v['net']==n: out.append(f"  {n} via ({v['at'][0]:.2f},{v['at'][1]:.2f})")
    for k,(d,a) in sorted(near_nets(n).items(), key=lambda kv: kv[1][0]): out.append(f"     near {k[0]} on {k[1]}: {d:.2f} mm at ({a[0]:.2f},{a[1]:.2f})")
for r in ('Y1','C12','C13','R5'):
    for p in P:
        if p['ref']==r: out.append(f"  {r}.{p['num']} {p['net']} ({p['at'][0]:.2f},{p['at'][1]:.2f})")
out.append("== USB D+/D-: the pair's own gap and nearby nets per layer (edge gap < 0.6)")
for n in ('USB_DP','USB_DM','USB_DP_MCU','USB_DM_MCU'):
    for k,(d,a) in sorted(near_nets(n).items(), key=lambda kv: kv[1][0])[:8]: out.append(f"  {n} near {k[0]} on {k[1]}: {d:.2f} mm at ({a[0]:.2f},{a[1]:.2f})")
    for t in TR:
        if t['net']==n: out.append(f"     {n} {t['layer']} ({t['a'][0]:.2f},{t['a'][1]:.2f})-({t['b'][0]:.2f},{t['b'][1]:.2f}) w{t['w']}")
out.append("== D1 (SRV05-4) pads")
for p in P:
    if p['ref']=='D1': out.append(f"  D1.{p['num']} {p['net']} ({p['at'][0]:.2f},{p['at'][1]:.2f})")
out.append("== GND pour islands (B.Cu / In2.Cu): area and whether a GND via or pad lies inside")
filler=pcbnew.ZONE_FILLER(b); filler.Fill(b.Zones())
gv=[v['at'] for v in V if v['net']=='GND']+[p['at'] for p in P if p['net']=='GND' and p['th']]
for z in b.Zones():
    if z.GetIsRuleArea() or z.GetNetname()!='GND': continue
    for l in z.GetLayerSet().Seq():
        ln=b.GetLayerName(l)
        if ln not in ('B.Cu','In2.Cu'): continue
        poly=z.GetFilledPolysList(l)
        for i in range(poly.OutlineCount()):
            o=poly.Outline(i); area=abs(o.Area())/1e12; bb=o.BBox()
            cnt=sum(1 for g in gv if o.PointInside(pcbnew.VECTOR2I(int(g[0]*1e6),int(g[1]*1e6))))
            if area<50 or cnt==0: out.append(f"  {ln} island {area:.1f} mm2 bbox {mm(bb.GetLeft()):.1f},{mm(bb.GetTop()):.1f}-{mm(bb.GetRight()):.1f},{mm(bb.GetBottom()):.1f}: GND vias/pads inside {cnt}")
out.append("== acute junction angles (< 85 deg) between two same-net tracks outside pads (acid-trap / sliver candidates)")
byln=defaultdict(list)
for t in TR: byln[(t['layer'],t['net'])].append(t)
def inpad(p, layer):
    for pd in P:
        if layer in pd['layers'] or pd['th']:
            bb=pd['obj'].GetBoundingBox()
            if mm(bb.GetLeft())-0.01<=p[0]<=mm(bb.GetRight())+0.01 and mm(bb.GetTop())-0.01<=p[1]<=mm(bb.GetBottom())+0.01: return pd
    return None
for (l,n),ts in byln.items():
    ends=defaultdict(list)
    for t in ts:
        ends[(round(t['a'][0],3),round(t['a'][1],3))].append(t['b']); ends[(round(t['b'][0],3),round(t['b'][1],3))].append(t['a'])
    for k,lst in ends.items():
        if len(lst)<2: continue
        for i in range(len(lst)):
            for j in range(i+1,len(lst)):
                o1,o2=lst[i],lst[j]
                if dist(o1,k)<0.1 or dist(o2,k)<0.1: continue
                a1=math.atan2(o1[1]-k[1],o1[0]-k[0]); a2=math.atan2(o2[1]-k[1],o2[0]-k[0])
                d=abs((math.degrees(a1-a2)+180)%360-180)
                if d<85 and not inpad(k,l): out.append(f"  {n:12s} {l:7s} ({k[0]:.2f},{k[1]:.2f}) {d:.0f} deg")
open('work/signals.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
