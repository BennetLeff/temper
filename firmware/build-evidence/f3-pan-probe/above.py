import math
def run(L,R,Ct,V0,f=80e6/1334,Cbus=9e-6,dt=5e-9,T_us=400,thr=40.975):
    T=1/f; vb=V0; i=0.0; vc=0.0; t=0.0; imax=0; above=0.0; lobes=0; prev=False; tlast=0
    while t<T_us*1e-6:
        s=1.0 if (t%T)<T/2 else -1.0
        i+=(s*vb-R*i-vc)/L*dt; vc+=i/Ct*dt; vb-=s*i/Cbus*dt
        a=abs(i)>thr
        if a: above+=dt; tlast=t
        if a and not prev: lobes+=1
        prev=a; imax=max(imax,abs(i)); t+=dt
    return imax, above*1e6, lobes, tlast*1e6
for name,(L,R) in {"cs_lo 33uH/2.1":(33e-6,2.1),"priors 55uH/1.0":(55e-6,1.0),"cast iron":(46e-6,4.3)}.items():
    for V in (120,132):
        for C in (0.475e-6,0.525e-6):
            im,ab,lo,tl=run(L,R,C,V*math.sqrt(2))
            print(f"{name:16s} {V}V C{C*1e6:.3f}: start peak {im:5.1f} A; above 40.975 A for {ab:5.1f} us in {lo} lobes, last at {tl:5.1f} us")
