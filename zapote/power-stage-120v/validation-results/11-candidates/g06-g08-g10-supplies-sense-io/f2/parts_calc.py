"""F2 parts check: 02153.15MXP + series limiter R.  Rerun: python3 -I parts_calc.py (stdlib; prints the tables quoted in PARTS-2026-10-13.md; writes nothing).

What it computes, for R in (0.10, 0.15, 0.22) ohm:
 1. Ik bound = V / (R_fuse_cold + R), the f2_variants.py formula (source impedance 0, so conservative), and margin on 1.5 kA.
 2. Fuse clearing I2t at that bound, as a sensitivity on the (unpublished) fuse arc voltage:
    circuit L di/dt = v_s(t) - (R + R_fuse) i - Va sgn(i) [after melt]; pre-arc ends when integral i^2 dt = 43.255 A2s
    (datasheet nominal melting I2t at 10 In; the adiabatic pre-arc I2t at 250 x In is lower, so this is an upper bound);
    then a constant arc voltage Va until the current reaches zero.  Worst case over point-on-wave (2 deg steps, 1 us time step, exact exponential update) and
    L in {2, 10} uH (the F4 study's source range).  Va = 0 is the non-current-limiting bound: the arc burns to the
    first natural current zero after melting (up to ~9.3 ms when the fault starts late in a half-cycle); higher Va = current-limiting fuse.
 3. Resistor pulse energy E = R x I2t_clear, and the ratio of the resistor's adiabatic single-pulse I2t capacity
    (Vishay AC datasheet 28730 'Pulse capability' chart, y-axis Ws/Ohm == A2s, read by eye) to the fuse I2t_clear.
Inputs read from the F4 study: V_rms (139.7 V) from 02-protection-timing/f2-coordination/result.json (read-only)."""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
F4 = json.load(open(os.path.join(HERE, '..', '..', '..', '02-protection-timing', 'f2-coordination', 'result.json')))
V = F4['V_rms']                       # 127 V + 10 %
F = 60.0
R_FUSE = 0.02825                      # f2_variants.py / f2_coord.py; Littelfuse 215 datasheet table: 0.0283 ohm nominal cold
I2T_MELT = 43.255                     # Littelfuse 215 datasheet (Revised GD. 11/30/21), 3.15 A row; "I2t test at 10x rated current"
BREAK = 1500.0                        # same table: 1500 A @ 250 VAC
L_SET = (2e-6, 10e-6)                 # F4 study source inductance range
VA_SET = (0.0, 50.0, 100.0, 150.0, 200.0, 250.0, 300.0)

# Adiabatic single-pulse I2t capacity (A2s == Ws/Ohm), Vishay AC.. Series datasheet doc 28730 Rev 07-Dec-2020 p.6
# (identical curves in Rev 13-Jan-14), read by eye from the log chart, +-25 %.  Re-read 2026-10-13 by pixel position
# calibrated on the decade gridlines (300 dpi render): AC05 153 / 124 / 76 and AC07 266 / 213 / 118 A2s at 0.10 / 0.15 / 0.22 ohm,
# AC03 27 / 18 at 0.15 / 0.22 (its 0.10 point sits on a steep edge, 90-125).  Values are per resistor at that R, not per ohm:
# the chart's Ws/Ohm is E/R = I2t, so they compare directly with the fuse I2t.
CAP = {
    'AC03_3W': {0.10: 125.0, 0.15: 30.0, 0.22: 19.0},     # LCSC C1365803 (0.15), C3490441 (0.22)
    'AC05_5W': {0.10: 160.0, 0.15: 125.0, 0.22: 75.0},    # LCSC C1364823 (0.10), C1382388 (0.15), C1364803 (0.22)
    'AC07_7W': {0.10: 280.0, 0.15: 220.0, 0.22: 120.0},   # LCSC C1366594 (0.15, 0 stock 2026-10-13)
}


def clear_i2t(R, L, Va, phi_deg, dt=1e-6):
    """Return (pre-arc time s, I2t at melt, I2t total, conduction time s) for one point-on-wave."""
    Rt = R + R_FUSE
    w = 2 * math.pi * F
    vp = math.sqrt(2) * V
    phi = math.radians(phi_deg)
    i, t, i2t, melted, t_melt = 0.0, 0.0, 0.0, False, None
    a = math.exp(-Rt * dt / L)
    while t < 3.0 / F:
        vs = vp * math.sin(w * t + phi)
        drive = vs - (Va * (1 if i > 0 else -1) if melted else 0.0)
        i_new = i * a + drive / Rt * (1 - a)          # exact step for constant drive over dt
        if melted and (i_new == 0 or (i_new > 0) != (i > 0)):  # current zero: arc extinguishes
            i2t += i * i * dt / 3
            return t_melt, I2T_MELT, i2t, t + dt
        i2t += 0.5 * (i * i + i_new * i_new) * dt
        i = i_new
        t += dt
        if not melted and i2t >= I2T_MELT:
            melted, t_melt = True, t
    return t_melt, I2T_MELT, i2t, t


def worst_i2t(R, Va):
    return max(clear_i2t(R, L, Va, ph)[2] for L in L_SET for ph in range(0, 180, 2))


def main():
    out = dict(V=V, R_fuse=R_FUSE, I2t_melt=I2T_MELT, breaking_A=BREAK, rows={})
    print(f'V = {V:.1f} V rms, R_fuse = {R_FUSE*1e3:.2f} mOhm, I2t_melt(10 In) = {I2T_MELT} A2s, breaking {BREAK:.0f} A')
    for R in (0.10, 0.15, 0.22):
        ik = V / (R_FUSE + R)
        halfcycle = ik * ik / (2 * F)                 # Ik_rms^2 x T/2: one full half-cycle (reference for Va = 0)
        row = dict(R=R, Ik_bound_A=round(ik, 1), Ik_peak_A=round(ik * math.sqrt(2), 1), margin_x=round(BREAK / ik, 2),
                   I2t_one_halfcycle_A2s=round(halfcycle, 0), E_halfcycle_J=round(R * halfcycle, 0),
                   E_prearc_only_J=round(R * I2T_MELT, 2), P_cont_W_at_1p42A=round(1.42 ** 2 * R, 3), by_Va={})
        print(f'\nR = {R:.2f} ohm: Ik <= {ik:.0f} A rms ({ik*math.sqrt(2):.0f} A pk), margin {BREAK/ik:.2f}x;'
              f' one half-cycle {halfcycle:.0f} A2s -> {R*halfcycle:.0f} J; pre-arc alone {R*I2T_MELT:.1f} J;'
              f' continuous loss {1.42**2*R:.2f} W at 1.42 A')
        print('   Va(V)  I2t_clear_max(A2s)  x_melt   E_R(J)  t_cond(ms)  worst_phi  ' + '  '.join(f'{k}_cap/I2t' for k in CAP))
        for Va in VA_SET:
            worst = (0, None)
            for L in L_SET:
                for ph in range(0, 180, 2):
                    tm, _, i2t, tc = clear_i2t(R, L, Va, ph)
                    if i2t > worst[0]:
                        worst = (i2t, (L, ph, tm, tc))
            i2t, (L, ph, tm, tc) = worst
            caps = {k: (v.get(R) / i2t if v.get(R) else None) for k, v in CAP.items()}
            row['by_Va'][str(int(Va))] = dict(I2t_clear_A2s=round(i2t, 1), x_melt=round(i2t / I2T_MELT, 2), E_R_J=round(R * i2t, 2),
                                              t_conduction_ms=round(tc * 1e3, 2), t_prearc_us=round(tm * 1e6, 1), worst_phi_deg=ph,
                                              worst_L_uH=L * 1e6, resistor_capacity_ratio={k: (round(c, 2) if c else None) for k, c in caps.items()})
            cs = '  '.join(f'{c:15.2f}' if c else '            n/a' for c in caps.values())
            print(f'   {Va:5.0f}  {i2t:18.1f}  {i2t/I2T_MELT:6.2f}  {R*i2t:7.1f}  {tc*1e3:10.2f}  {ph:9d}  {cs}')
        # smallest constant arc voltage at which each resistor's pulse capacity covers the fuse I2t (1.0x and 1.5x)
        for k, v in CAP.items():
            for need in (1.0, 1.5):
                lo, hi = 0.0, 400.0
                if v[R] / worst_i2t(R, hi) < need:
                    row[f'Va_min_{k}_{need}x'] = None
                    print(f'   {k} at R = {R:.2f} ohm: capacity {v[R]:.0f} A2s never covers {need}x I2t_clear (even Va = 400 V)')
                    continue
                for _ in range(14):
                    mid = 0.5 * (lo + hi)
                    lo, hi = (lo, mid) if v[R] / worst_i2t(R, mid) >= need else (mid, hi)
                row[f'Va_min_{k}_{need}x'] = round(hi, 0)
                print(f'   {k} at R = {R:.2f} ohm: capacity {v[R]:.0f} A2s covers {need}x I2t_clear if Va >= {hi:.0f} V')
        out['rows'][f'{R:.2f}'] = row
    out['resistor_I2t_capacity_A2s'] = CAP
    return out


if __name__ == '__main__':
    main()
