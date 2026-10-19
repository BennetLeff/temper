import math
def ring(L,R,Ct,V0,f=80e6/1334,dt=5e-9,win_us=200,thr=1.0):
    """One bridge pulse (T/2) from the held bus, then both low sides on: the series RLC rings
    freely. Count CT_ZC-like zero crossings with |i| having exceeded thr since the last one."""
    T=1/f; i=0.0; vc=0.0; t=0.0; imax=0; edges=0; sign=0; armed=False; first=None; last=None
    while t < T/2 + win_us*1e-6:
        v = V0 if t < T/2 else 0.0
        i += (v - R*i - vc)/L*dt; vc += i/Ct*dt; imax=max(imax,abs(i))
        if abs(i) > thr: armed=True
        s = 1 if i>0 else -1
        if t >= T/2 and armed and sign and s != sign:
            edges += 1; armed=False; last=t
            if first is None: first=t
        sign = s; t += dt
    fr = (edges-1)/2/(last-first) if edges>=3 else float('nan')
    return edges, imax, fr
P={"Al240":(23.6e-6,0.24),"Al180":(30.8e-6,0.28),"cs_lo":(33e-6,2.1),"castiron":(46e-6,4.3),"430hi":(63e-6,6.2),"priors1":(55e-6,1.0),"nopan":(77e-6,0.13)}
for n,(L,R) in P.items():
    out=[]
    for C in (0.475e-6,0.525e-6):
        for V in (153.0,187.0):
            e,im,fr=ring(L,R,C,V); out.append(f"{e:2d} edges/{im:4.1f}A/{fr/1e3:4.1f}kHz")
    print(f"{n:9s} {' | '.join(out)}")
