"""Intent-specific checks: TVS D21-D24 two GND vias; LDO pin-4 to EP bridge on F.Cu; D29 at C100 with two vias;
5V leaves U16 through two vias; no USB_VBUS copper under J1 shell beyond pin exits; C15 at U16; L2 GND return;
FB node tracks vs SW nodes; QSPI_CLK_FLASH; R13 placement. Output work/intent_items.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
b=load(); P=pads(b); T=tracks(b); V=[t for t in T if t['kind']=='via']; TR=[t for t in T if t['kind']=='track']
out=[]
def padof(r,n): return next(p for p in P if p['ref']==r and p['num']==n)
def gnd_vias_within(pt,r): return [v for v in V if v['net']=='GND' and dist(v['at'],pt)<r]
out.append("== TVS D21-D24 GND return: GND vias within 2.5 mm of the GND pad, and the connecting F.Cu GND tracks")
for r in ('D21','D22','D23','D24','D25','D26','D27','D28'):
    for p in P:
        if p['ref']==r and p['net']=='GND':
            vs=gnd_vias_within(p['at'],2.5)
            out.append(f"  {r}.{p['num']} GND pad ({p['at'][0]:.2f},{p['at'][1]:.2f}): {len(vs)} GND vias within 2.5 mm: "+", ".join(f"({v['at'][0]:.2f},{v['at'][1]:.2f})" for v in vs))
out.append("== LDO pin 4 (GND) to EP bridge on F.Cu")
for r in ('U11','U12'):
    p4=padof(r,'4'); ep=padof(r,'9')
    br=[t for t in TR if t['net']=='GND' and t['layer']=='F.Cu' and (seg_dist(p4['at'],t['a'],t['b'])<0.6 ) and (seg_dist(ep['at'],t['a'],t['b'])<1.4)]
    out.append(f"  {r}: pin4 ({p4['at'][0]:.2f},{p4['at'][1]:.2f}) EP ({ep['at'][0]:.2f},{ep['at'][1]:.2f}); F.Cu GND tracks touching both: {[(round(t['a'][0],2),round(t['a'][1],2),round(t['b'][0],2),round(t['b'][1],2),t['w']) for t in br]}")
out.append("== D29 (SS14) at C100: pads, vias on its nets within 3 mm")
for p in P:
    if p['ref'] in ('D29','C100'): out.append(f"  {p['ref']}.{p['num']} {p['net']} ({p['at'][0]:.2f},{p['at'][1]:.2f})")
for p in P:
    if p['ref']=='D29':
        vs=[v for v in V if v['net']==p['net'] and dist(v['at'],p['at'])<3.5]
        out.append(f"  D29.{p['num']} {p['net']}: vias within 3.5 mm: {[(round(v['at'][0],2),round(v['at'][1],2)) for v in vs]}")
out.append("== 5V leaving U16.6: 5V vias within 3 mm of U16.6")
p=padof('U16','6'); out.append(f"  U16.6 ({p['at'][0]:.2f},{p['at'][1]:.2f}): {[(round(v['at'][0],2),round(v['at'][1],2)) for v in V if v['net']=='5V' and dist(v['at'],p['at'])<3.5]}")
out.append("== USB_VBUS copper under J1 shell region (x 49.8-59.3, y 126.7-137.3), per layer")
for t in TR:
    if t['net']=='USB_VBUS':
        for q in (t['a'],t['b']):
            if 49.8<=q[0]<=59.3 and 126.7<=q[1]<=137.3:
                out.append(f"  {t['layer']} ({t['a'][0]:.2f},{t['a'][1]:.2f})-({t['b'][0]:.2f},{t['b'][1]:.2f}) w{t['w']}"); break
for v in V:
    if v['net']=='USB_VBUS' and 49.8<=v['at'][0]<=59.3 and 126.7<=v['at'][1]<=137.3: out.append(f"  via ({v['at'][0]:.2f},{v['at'][1]:.2f})")
out.append("== C15 / C113 / R121 / U16 geometry")
for r in ('C15','C113','R121','U16','R110','C16','U3','C17'):
    for p in P:
        if p['ref']==r: out.append(f"  {r}.{p['num']} {p['net']:10s} ({p['at'][0]:.2f},{p['at'][1]:.2f})")
out.append("== L2.2 GND return path tracks (F.Cu GND tracks touching L2.2)")
p=padof('L2','2')
for t in TR:
    if t['net']=='GND' and seg_dist(p['at'],t['a'],t['b'])<2.2: out.append(f"  {t['layer']} ({t['a'][0]:.2f},{t['a'][1]:.2f})-({t['b'][0]:.2f},{t['b'][1]:.2f}) w{t['w']}")
out.append("== feedback nets vs switch nodes: min distance of CONV_FBP/CONV_FBN/CONV_REF/CONV_CP/CONV_CN tracks to SW_P/SW_N tracks + L1/L2 pads (same or any layer, centreline)")
sw=[t for t in TR if t['net'] in ('SW_P','SW_N')]+[]
swp=[p for p in P if p['ref'] in ('L1','L2','D2','D3') and p['net'] in('SW_P','SW_N')]
for n in ('CONV_FBP','CONV_FBN','CONV_FBN_MID','CONV_REF','CONV_CP','CONV_CN'):
    best=None
    for t in TR:
        if t['net']!=n: continue
        for s in sw:
            for q in (t['a'],t['b']):
                d=seg_dist(q,s['a'],s['b'])
                if best is None or d<best[0]: best=(d,t['layer'],q,s['net'],s['layer'])
        for q in (t['a'],t['b']):
            for sp in swp:
                d=dist(q,sp['at'])-max(sp['size'])/2
                if best is None or d<best[0]: best=(d,t['layer'],q,sp['ref']+'.'+sp['num'],'pad')
    if best: out.append(f"  {n:13s}: {best[0]:.2f} mm ({best[1]} at ({best[2][0]:.2f},{best[2][1]:.2f}) to {best[3]} {best[4]})")
out.append("== QSPI: R13 placement and net lengths")
for n in ('QSPI_CLK','QSPI_CLK_FLASH'):
    L=sum(dist(t['a'],t['b']) for t in TR if t['net']==n); out.append(f"  {n}: {L:.1f} mm")
for r in ('R13','R3','R4','U2'):
    for p in P:
        if p['ref']==r and p['num'] in('1','2','6','8'): out.append(f"  {r}.{p['num']} {p['net']} ({p['at'][0]:.2f},{p['at'][1]:.2f})")
out.append("== U1 pins 56 (QSPI_CS?) and 51-55 nets")
for p in P:
    if p['ref']=='U1' and p['num'] in ('51','52','53','54','55','56'): out.append(f"  U1.{p['num']} {p['net']} ({p['at'][0]:.2f},{p['at'][1]:.2f})")
open('work/intent_items.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
