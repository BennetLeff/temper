import math, sys
def sim(L, R, Ct, Vline, t_on_ms, T_on_us, f=59524.0, Cbus=9e-6, Rsrc=0.5, dt=2e-8):
    """Bridge starts at t_on (ms after a line zero) with the bus charged to the line peak.
    Returns max |i| while on, bus at end, max |i| after off."""
    Vpk = Vline*math.sqrt(2); w = 2*math.pi*60
    vb = Vpk; i = 0.0; vc = 0.0; t = t_on_ms*1e-3; t_end = t + T_on_us*1e-6
    imax = 0; T = 1/f; vbmin = vb
    while t < t_end:
        s = 1.0 if ((t - t_on_ms*1e-3) % T) < T/2 else -1.0
        vl = abs(Vpk*math.sin(w*t))
        irect = (vl - vb)/Rsrc if vl > vb else 0.0
        vbr = s*vb
        di = (vbr - R*i - vc)/L
        i += di*dt; vc += i/Ct*dt
        vb += (irect - s*i)/Cbus*dt
        imax = max(imax, abs(i)); vbmin = min(vbmin, vb)
        t += dt
    return imax, vb, vbmin
plants = {"Al240": (23.6e-6, 0.24), "Al180": (30.8e-6, 0.28), "castiron": (46e-6, 4.3), "cs_lo": (33e-6, 2.1), "nopan": (77e-6, 0.13)}
for name,(L,R) in plants.items():
    for V in (132,):
        for t_on in (0.0, 1.0, 4.17):
            for Ton in (50, 200, 625, 1250):
                im, vb, vbmin = sim(L, R, 0.475e-6, V, t_on, Ton)
                print(f"{name:8s} {V}V start {t_on:4.2f} ms after zero, on {Ton:5d} us: max|i| {im:6.1f} A, bus end {vb:6.1f} V (min {vbmin:6.1f})")
