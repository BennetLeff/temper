import math
def sim(L, R, Ct, V0, npulse=None, T_on_us=None, f=59524.0, Cbus=9e-6, dt=5e-9, t_total_us=200):
    """Bus charged to V0 (no line recharge: near a line zero), bridge on for npulse half-periods
    (or T_on_us), then all switches off: body diodes clamp the tank to -sign(i) x bus."""
    T = 1/f; t_on = npulse*T/2 if npulse is not None else T_on_us*1e-6
    vb=V0; i=0.0; vc=0.0; t=0.0; imax=0; tmax=0; imax_after=0
    while t < t_total_us*1e-6:
        if t < t_on:
            s = 1.0 if (t % T) < T/2 else -1.0
            vbr = s*vb; ib = s*i
        else:
            if abs(i) < 1e-3 and abs(vc) <= vb: i = 0.0; vbr = vc; ib = 0.0  # diodes block
            else:
                s = -1.0 if i > 0 else 1.0; vbr = s*vb; ib = s*i
        i += (vbr - R*i - vc)/L*dt; vc += i/Ct*dt; vb -= ib/Cbus*dt
        if abs(i) > imax: imax, tmax = abs(i), t
        if t >= t_on and abs(i) > imax_after: imax_after = abs(i)
        t += dt
    return imax, tmax*1e6
P = {"Al240": (23.6e-6, 0.24), "Al180": (30.8e-6, 0.28), "cs_lo": (33e-6, 2.1), "castiron": (46e-6, 4.3),
     "430hi": (63e-6, 6.2), "priors1": (55e-6, 1.0), "nopan": (77e-6, 0.13)}
print("continuous start from a 187 V bus (C 0.475 uF): peak and its time")
for n,(L,R) in P.items():
    im,tm = sim(L,R,0.475e-6,187.0,T_on_us=200)
    print(f"  {n:9s} peak {im:6.1f} A at {tm:5.1f} us")
for npl in (1,2,3,4):
    print(f"burst of {npl} pulse(s) at 59.5 kHz from 187 V, then off:")
    for n,(L,R) in P.items():
        row=[]
        for C in (0.475e-6,0.5e-6,0.525e-6):
            im,tm = sim(L,R,C,187.0,npulse=npl,t_total_us=120); row.append(f"{im:5.1f}")
        print(f"  {n:9s} peak A over C -5/0/+5 %: {' '.join(row)}")
