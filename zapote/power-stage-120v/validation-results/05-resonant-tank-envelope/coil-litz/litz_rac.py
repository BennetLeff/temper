"""Litz R_ac screen for the R36 hand-wound coil (estimate, not a measurement).

R_dc from copper area, lay factor and temperature. Proximity loss per strand per metre, low-frequency
round-wire form (d << skin depth): P' = pi * w^2 * B^2 * d^4 / (128 * rho), with B the peak field the
strand sees (external winding field + the bundle's own field). B is swept, because the winding field
needs the R32/R36 FEM map: the band below brackets it.
"""
import math
RHO20, ALPHA, T = 1.724e-8, 0.00393, 100.0
rho = RHO20 * (1 + ALPHA * (T - 20))
import sys
f, I_rms = 40e3, float(sys.argv[1]) if len(sys.argv) > 1 else 22.0
w = 2 * math.pi * f
delta = math.sqrt(rho / (math.pi * f * 4e-7 * math.pi))
print(f"skin depth at {f/1e3:.0f} kHz, {T:.0f} C: {delta*1e3:.3f} mm")
for n, d, turns, length in ((270, 0.10e-3, 21.9, 10.0), (420, 0.08e-3, 21.9, 10.0)):
    area = n * math.pi * d * d / 4
    rdc = rho * length * 1.03 / area          # 3 % lay (twist) factor
    rbund = math.sqrt(area / 0.55 / math.pi)  # bundle radius at a 0.55 copper fill
    b_self = 4e-7 * math.pi * I_rms * math.sqrt(2) / (2 * math.pi * rbund) / 2   # mean over the bundle
    row = [f"{n} x {d*1e3:.2f} mm, {turns} t, {length} m: Cu {area*1e6:.2f} mm2, R_dc100 {rdc*1e3:.0f} mOhm"]
    for b_ext in (11.5e-3, 15e-3, 25.4e-3, 33e-3):
        b = math.hypot(b_ext, b_self)
        p_per_m = math.pi * w**2 * b**2 * d**4 / (128 * rho)
        r_prox = n * length * p_per_m / I_rms**2
        row.append(f"B_ext {b_ext*1e3:.0f} mT: R_ac {(rdc + r_prox)*1e3:.0f} mOhm")
    print("; ".join(row))
