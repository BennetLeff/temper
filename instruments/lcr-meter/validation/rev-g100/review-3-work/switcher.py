"""TPS65131 block geometry: U13 pin nets/positions, the hot-loop parts, SW node copper, loop sizes and the
distance from the switcher to the analog victims. Output work/switcher.txt"""
import sys, json; sys.path.insert(0,'work')
from lib_board import *
b=load(); P=pads(b); T=tracks(b)
d=json.load(open('cad/design.json'))
out=[]
out.append("TPS65131 pinout (design.json): "+json.dumps(d['pinouts']['TPS65131']))
out.append("== U13 pads")
for p in P:
    if p['ref']=='U13': out.append(f"  {p['num']:>3} {p['net']:12s} ({p['at'][0]:.2f},{p['at'][1]:.2f}) {p['size']}")
out.append("== hot-loop parts: pads")
for r in ('L1','L2','D2','D3','C80','C82','C83','C81','C89','C90','C91','C92','C117','R81','R82','R83','R84','R111','C84','C85','C86','C87','C88','R120','U17'):
    for p in P:
        if p['ref']==r: out.append(f"  {r}.{p['num']} {p['net']:10s} ({p['at'][0]:.2f},{p['at'][1]:.2f}) {p['size']}")
out.append("== SW_P / SW_N / RAW_P / RAW_N / 5V copper near U13 (F.Cu tracks, with width)")
for t in T:
    if t['kind']=='track' and t['net'] in ('SW_P','SW_N') : out.append(f"  {t['net']} {t['layer']} ({t['a'][0]:.2f},{t['a'][1]:.2f})-({t['b'][0]:.2f},{t['b'][1]:.2f}) w{t['w']}")
# zone SW_P
for z in b.Zones():
    if z.GetNetname()=='SW_P':
        o=z.Outline().Outline(0); pts=[(mm(o.CPoint(i).x),mm(o.CPoint(i).y)) for i in range(o.PointCount())]
        out.append(f"  SW_P zone F.Cu points {pts}")
out.append("== GND return for the hot loops: GND vias near U13 (within 6 mm) and GND pads of the hot-loop caps -> nearest GND via")
gv=[t for t in T if t['kind']=='via' and t['net']=='GND']
near=[v for v in gv if dist(v['at'],(137.5,135.0))<6]
out.append(f"  GND vias within 6 mm of U13 centre: {len(near)}: "+", ".join(f"({v['at'][0]:.1f},{v['at'][1]:.1f})" for v in near))
for r in ('C80','C82','C89','C90','C91','C92','L2','C83','C81'):
    for p in P:
        if p['ref']==r and p['net']=='GND':
            dv=min(dist(p['at'],v['at']) for v in gv); out.append(f"  {r}.{p['num']} GND pad ({p['at'][0]:.2f},{p['at'][1]:.2f}) nearest GND via {dv:.2f} mm")
out.append("== distances: switcher parts to analog victims (part centres)")
vic={'U7 TIA':(114.5,80),'U6':(86.5,76),'U14 codec':(64,98.5),'U5':(70.5,75.5),'K4':(138,76),'U11':(130,110),'U12':(143,110),'R43/R44/R45 range R':(109.5,86)}
agg={'U13':(137.5,135),'L1':(131.5,141.2),'L2':(146.5,130),'D2':(130.5,136),'D3':(140.5,128)}
for an,ap in agg.items():
    out.append("  "+an+": "+", ".join(f"{vn} {dist(ap,vp):.1f} mm" for vn,vp in vic.items()))
open('work/switcher.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
