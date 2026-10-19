import math
def one_pulse(L,R,Ct,V0,f=59524.0,Cbus=9e-6,dt=2e-9):
    T=1/f; t_on=T/2; vb=V0; i=0.0; vc=0.0; t=0.0; imax=0; t_zero=None; was_pos=False
    while t<80e-6:
        if t<t_on: vbr=vb; ib=i
        else:
            if i<=0 and t>t_on: t_zero=t; break
            vbr=-vb; ib=-i
        i+=(vbr-R*i-vc)/L*dt; vc+=i/Ct*dt; vb-=ib/Cbus*dt; imax=max(imax,abs(i)); t+=dt
    return imax, (t_zero*1e6 if t_zero else float('nan'))
P={"Al240":(23.6e-6,0.24),"Al180":(30.8e-6,0.28),"cs_lo":(33e-6,2.1),"castiron":(46e-6,4.3),"430hi":(63e-6,6.2),"priors1":(55e-6,1.0),"nopan":(77e-6,0.13)}
for n,(L,R) in P.items():
    out=[]
    for C in (0.475e-6,0.525e-6):
        for V in (153.0,187.0):
            im,tz=one_pulse(L,R,C,V); out.append(f"{tz:5.2f}us/{im:4.1f}A")
    print(f"{n:9s} first current zero after a 1-pulse burst (C-5% 108V, C-5% 132V, C+5% 108V, C+5% 132V): {'  '.join(out)}")
