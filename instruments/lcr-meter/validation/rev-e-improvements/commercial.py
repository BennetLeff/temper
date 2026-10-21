#!/usr/bin/env python3
"""Published accuracy of two bench LCR meters, evaluated at the Temper targets (README section 5).

GW Instek LCR-6100: LCR-6000 Series User Manual v1.07, ch. 12 p.131 (conditions), ch. 13 sections 13.1-13.2
  (printed pp.136-142).  https://www.gwinstek.com/en-US/products/downloadSeriesDownNew/10211/757
  Ae = +/-[A*Ar + (Ka + Kb + Kf)*100 + KL] * Kc  [%]
  - A from Fig. 13-1 (a region map; edges digitized, see A_GW below - READ FROM A GRAPH);
  - Ar = 1 at 1 Vrms; Kc = 1 at 18-28 degC; Kb ignored below 500 Ohm;
  - Ka = (1e-3/|Zm|)(1 + 200/Vs[mV]) for slow/med, 100 Hz-100 kHz;
  - Kf = 0 at an open/short trim frequency, else 0.0003 (+0.03 %); LCR-6100 trim points include
    30/40/50/60/80/100 kHz; 1 kHz is ASSUMED to be a trim point;
  - KL (Vs <= 1.5 Vrms): 0 m -> 0; 1 m -> 2.5e-2 (1 + 0.5 f[kHz]) %;
  - L, C x sqrt(1 + D^2) when D > 0.1; De = Ae/100 (x (1 + D) when D > 0.1); Rs error = X * De.
B&K Precision 891: User Manual section 8 (printed pp.75-81),
  https://bkpmedia.s3.amazonaws.com/downloads/manuals/en-us/891_manual.pdf
  Zae from the |Z| x frequency table (+1 displayed digit, ignored here); 1 Vrms, slow (800 ms);
  Lae = Cae = Zae (x sqrt(1+D^2) when D > 0.1); Dae = Zae (x (1 + D^2)); Rae = X * Zae.
Network targets (tank f0, Q at resonance, |Z| ~ R): |Z| and phase errors |Z|*Ae on each component,
f0 error = dX / (dX/df * f), Q error = Ae (R accuracy, Q_x ~ 0).
    commercial.py -> results/commercial.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study as s  # noqa: E402

vm = s.vm
GW_TRIM_HZ = {1e3, 30e3, 40e3, 50e3, 60e3, 80e3, 100e3}


def A_GW(f, z):
    """Fig. 13-1 regions, slow/medium speed (digitized at 400 dpi; inner box top edge not modelled)."""
    if 100 <= f <= 30e3 and 15 <= z <= 312e3:
        return 0.05
    if 50 <= f <= 100e3 and 1.5 <= z <= 1.5e6:
        return 0.1
    if z >= 0.2 and f <= 200e3:
        return 0.25
    return 0.65


def gw_ae(f, z, lead_m=0.0, vs_mv=1000.0):
    ka = (1e-3 / z) * (1 + 200 / vs_mv) * 100
    kf = 0.0 if f in GW_TRIM_HZ else 0.03
    kl = 2.5e-2 * lead_m * (1 + 0.5 * f / 1e3)
    return (A_GW(f, z) + ka + kf + kl) / 100       # fraction


BK_ROWS = [(0.1, 1, [1, 1, 2, 5, 10]), (1, 100, [0.5, 0.5, 1, 2, 4]), (100, 1e3, [0.2, 0.2, 0.5, 0.5, 1]),
           (1e3, 1e4, [0.05, 0.2, 0.5, 1, 2]), (1e4, 1e5, [0.2, 0.2, 1, 1, 2]),
           (1e5, 1e6, [0.5, 0.5, 2, 3, 4]), (1e6, 1e7, [2, 2, 5, 5, 10])]


def bk_ae(f, z):
    col = 0 if f <= 1e3 else 1 if f <= 10e3 else 2 if f <= 100e3 else 3 if f <= 200e3 else 4
    for lo, hi, v in BK_ROWS:
        if lo <= z < hi:
            return v[col] / 100
    return 0.1   # outside the table (below 0.1 Ohm): no specification; flag as 10 %


def target_error(meter, t, f):
    tid, dn, fl, q, tol, unit, _ = t
    d = vm.DUTS[dn]
    z = complex(d.z(f))
    za = abs(z)
    D = abs(z.real / z.imag) if z.imag else float("inf")
    ae = meter(f, za)
    gw = meter is not bk_ae
    if q in ("f0", "Q"):
        dz = za * ae
        if q == "f0":
            dxdf = (d.z(f * 1.0001).imag - d.z(f * 0.9999).imag) / (f * 0.0002)
            return dz / dxdf / f
        return ae
    lc = ae * (math.sqrt(1 + D * D) if D > 0.1 else 1.0)
    de = ae * ((1 + D) if gw else (1 + D * D)) if D > 0.1 else ae
    if q in ("L", "C"):
        return lc
    if q == "tand":
        return de
    if q == "R":
        rs = abs(z.imag) * de
        return rs if unit == "ohm" else rs / z.real
    raise KeyError(q)


METERS = {
    "LCR-6100 direct fixture (0 m)": lambda f, z: gw_ae(f, z, 0.0),
    "LCR-6100 with 1 m leads": lambda f, z: gw_ae(f, z, 1.0),
    "B&K 891": bk_ae,
}


def main():
    out = {}
    for name, m in METERS.items():
        res = {}
        for t in s.TARGETS:
            res[t[0]] = max(target_error(m, t, f) for f in t[2])
        out[name] = res
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/commercial.json").write_text(json.dumps(out, indent=1))
    print("| Target | T | " + " | ".join(out) + " |")
    print("|---|---|" + "---|" * len(out))
    for t in s.TARGETS:
        print(f"| {t[0]} | {s.tol_str(t[0])} | " + " | ".join(s.fmt(t[0], out[n][t[0]]) for n in out) + " |")


if __name__ == "__main__":
    main()
