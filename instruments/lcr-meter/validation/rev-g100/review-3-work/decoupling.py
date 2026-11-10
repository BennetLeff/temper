"""Decoupling: for each IC power pin, the nearest same-net capacitor pad, its distance, and the distance from
that capacitor's GND pad to the nearest GND via (there is no F.Cu GND pour, so every F.Cu GND pad must reach In1
through a via). Output: work/decoupling.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
b=load(); P=pads(b); T=tracks(b)
gnd_vias=[t['at'] for t in T if t['kind']=='via' and t['net']=='GND']
gnd_th=[p['at'] for p in P if p['th'] and p['net']=='GND']
POWER={'3V3','3V3A','1V1','5V','12V','-12V','RAW_P','RAW_N','USB_VBUS','VRLY','LDOIN_P','LDOIN_N','SW_P','VNEG_IN','VPOS','VNEG','AVDD','DVDD','IOVDD','VREF'}
caps={}
for p in P:
    if p['ref'].startswith('C'):
        caps.setdefault(p['ref'],{})[p['net']]=p
out=[]
for p in P:
    if not p['ref'].startswith('U'): continue
    if p['net'] not in POWER and not any(k in p['net'] for k in ('V','VDD','VCC','IN','OUT')): continue
    if p['net'] in ('GND','') : continue
    best=None
    for cref,cp in caps.items():
        if p['net'] in cp and 'GND' in cp:
            d=dist(p['at'], cp[p['net']]['at'])
            if best is None or d<best[0]: best=(d,cref,cp)
    if best is None:
        out.append(f"{p['ref']}.{p['num']:>3} {p['net']:10s} at {p['at'][0]:.2f},{p['at'][1]:.2f}: NO cap to GND on this net"); continue
    d,cref,cp=best
    g=cp['GND']['at']
    dv=min(dist(g,v) for v in gnd_vias+gnd_th)
    out.append(f"{p['ref']}.{p['num']:>3} {p['net']:10s} at {p['at'][0]:.2f},{p['at'][1]:.2f}: {cref} {cp['GND']['fp'].GetValue()[:14]:14s} pin-to-cap {d:5.2f} mm; cap GND pad ({g[0]:.2f},{g[1]:.2f}) to nearest GND via {dv:4.2f} mm")
open('work/decoupling.txt','w').write('\n'.join(out)+'\n')
print('\n'.join(out))
