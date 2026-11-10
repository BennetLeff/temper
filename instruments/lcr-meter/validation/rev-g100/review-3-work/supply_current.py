"""Supply copper vs worst-case fault current, re-derived.
IPC-2221 (eq. 6-1 / 6-2): I = k * dT^0.44 * A^0.725, A in mil^2, k = 0.048 external, 0.024 internal.
IPC-2152 generic chart fit (smps.us): A = (117.555*dT^-0.913 + 1.15) * I^(0.84*dT^-0.108 + 1.159)  (any layer).
Copper: outer 35 um = 1.378 mil, inner 17.5 um (0.5 oz) = 0.689 mil. Via barrel: pi*drill*18 um (IPC-6012 class 2 min);
for a via, A_barrel compared to the same A requirement.
Lists, for each power net: min width per layer, the narrowest segment, every segment under the IPC-2152 width
and the via count on each layer-change cluster. Output work/supply_current.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
from collections import defaultdict
b=load(); T=tracks(b)
I={'USB_VBUS':1.17,'5V':1.17,'RAW_P':0.5,'12V':0.5,'RAW_N':0.5,'-12V':0.5,'3V3':0.6,'LDOIN_P':0.5,'LDOIN_N':0.5,'5VA':0.6,'3V3A':0.6,'VRLY':0.3}
dT=10.0
def a2152(i): return (117.555*dT**-0.913+1.15)*i**(0.84*dT**-0.108+1.159)
def a2221(i,ext): return (i/((0.048 if ext else 0.024)*dT**0.44))**(1/0.725)
def i2221(A,ext): return (0.048 if ext else 0.024)*dT**0.44*A**0.725
thk={'F.Cu':1.378,'B.Cu':1.378,'In1.Cu':0.689,'In2.Cu':0.689}
out=[]
for net,i in I.items():
    segs=[t for t in T if t['kind']=='track' and t['net']==net]
    vias=[t for t in T if t['kind']=='via' and t['net']==net]
    if not segs: out.append(f"{net}: no tracks"); continue
    out.append(f"== {net}: I_fault {i} A; IPC-2152 A={a2152(i):.1f} mil2 -> outer {a2152(i)/1.378/39.37:.2f} mm, inner {a2152(i)/0.689/39.37:.2f} mm; IPC-2221 outer {a2221(i,True)/1.378/39.37:.2f} mm, inner {a2221(i,False)/0.689/39.37:.2f} mm")
    byl=defaultdict(list)
    for s in segs: byl[s['layer']].append(s)
    for l,ss in sorted(byl.items()):
        L=sum(dist(s['a'],s['b']) for s in ss)
        wmin=min(s['w'] for s in ss)
        ext=l in('F.Cu','B.Cu')
        out.append(f"   {l}: {len(ss)} segs, {L:.1f} mm, widths {sorted(set(round(s['w'],2) for s in ss))}; narrowest {wmin:.2f} mm carries (IPC-2221, 10C) {i2221(wmin*39.37*thk[l],ext):.2f} A")
        need=a2152(i)/thk[l]/39.37
        for s in ss:
            if s['w']<need-1e-6 and dist(s['a'],s['b'])>0.05:
                out.append(f"      UNDER 2152: {s['w']:.2f} mm ({s['a'][0]:.2f},{s['a'][1]:.2f})-({s['b'][0]:.2f},{s['b'][1]:.2f}) len {dist(s['a'],s['b']):.2f}")
    # vias: A_barrel in mil2
    for v in vias:
        Ab=math.pi*v['drill']*0.018*1e6/645.16  # mm2 -> mil2
        pass
    if vias:
        d=vias[0]['drill']; Ab=math.pi*d*0.018/0.00064516
        out.append(f"   {len(vias)} vias drill {sorted(set(round(v['drill'],2) for v in vias))}: one barrel A={Ab:.1f} mil2 -> IPC-2221 int {i2221(Ab,False):.2f} A, IPC-2152 need {a2152(i):.1f} mil2 => {math.ceil(a2152(i)/Ab)} vias per crossing by 2152, {math.ceil(a2221(i,False)/Ab)} by 2221-internal")
        # cluster vias (within 1.5 mm) to count per crossing
        cl=[]
        for v in vias:
            for c in cl:
                if any(dist(v['at'],u['at'])<1.6 for u in c): c.append(v); break
            else: cl.append([v])
        for c in cl:
            out.append(f"      via cluster x{len(c)} at ({c[0]['at'][0]:.2f},{c[0]['at'][1]:.2f})")
open('work/supply_current.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
