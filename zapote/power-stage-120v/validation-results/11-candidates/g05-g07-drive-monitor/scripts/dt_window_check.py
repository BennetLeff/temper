#!/usr/bin/env python3
"""Dead-time window check for a UCC21550 -> NCP51561 swap (F6 candidate).

    python3 -I validation-results/11-candidates/g05-g07-drive-monitor/scripts/dt_window_check.py
The board's D2 grid passes the hot off-gate screen only for driver dead times in [391, 498] ns (audit.rs DT_WINDOW_NS,
DECISIONS 2026-10-03). Same estimator as audit.rs dead_time_window_ns: linear interpolation of the datasheet min and max
columns between the two tabulated resistor values, then resistor tolerance and TCR over 125 K.
  UCC21550 SLUSE89C: tDT = 8.6*R+13 ns, rows R=20k: 167/185/203 ns, R=50k: 399/443/487 ns.
  NCP51561 (onsemi, datasheet text 'DEAD-TIME AND OVERLAP SECTION'): tDT = 10 ns/kohm * R,
           R=20k: 145/200/255 ns, R=100k: 800/1000/1200 ns.
"""
import sys
sys.dont_write_bytecode = True
WIN = (391.0, 498.0)

def window(rows, r, tol, tcr):
    (r1, lo1, hi1), (r2, lo2, hi2) = rows
    drift = tcr * 1e-6 * 125.0
    rmin, rmax = r * (1 - tol) * (1 - drift), r * (1 + tol) * (1 + drift)
    return (lo1 + (rmin - r1) * (lo2 - lo1) / (r2 - r1), hi1 + (rmax - r1) * (hi2 - hi1) / (r2 - r1))

UCC = ((20.0, 167.0, 203.0), (50.0, 399.0, 487.0))
NCP = ((20.0, 145.0, 255.0), (100.0, 800.0, 1200.0))
lo, hi = window(UCC, 49.9, 0.001, 25.0)
print(f"UCC21550 @ 49.9k 0.1%: {lo:.1f}..{hi:.1f} ns  (audit.rs: 396.6..488.0)")
assert abs(lo - 396.6) < 0.2 and abs(hi - 488.0) < 0.2
print(f"window ratio hi/lo allowed = {WIN[1]/WIN[0]:.3f}  -> max symmetric tolerance of the driver's own DT = {(WIN[1]-WIN[0])/(WIN[1]+WIN[0])*100:.1f} %")
best = None
for r in [x / 10 for x in range(300, 1000)]:
    lo, hi = window(NCP, r, 0.001, 25.0)
    fit_lo = lo >= WIN[0]
    fit_hi = hi <= WIN[1]
    if fit_lo and fit_hi:
        best = (r, lo, hi)
        break
print("NCP51561: any R in 30..100k whose min..max sits inside 391..498 ns:", best if best else "NONE")
for r in (40.0, 44.2, 49.9, 54.9, 60.4):
    lo, hi = window(NCP, r, 0.001, 25.0)
    print(f"  NCP51561 R={r:5.1f}k 0.1%: {lo:6.1f}..{hi:6.1f} ns  lower edge {'OK' if lo >= WIN[0] else 'below 391'}, upper edge {'OK' if hi <= WIN[1] else 'above 498 by %.0f ns' % (hi - WIN[1])}")
# Infineon 2EDR8259H (research/driver-isolator-alternatives.md: 85..115 ns at 10 k, tDT = 10 ns/kohm; NOT independently read here)
for r in (44.2, 46.0, 47.0):
    nom = 10.0 * r
    lo, hi = nom * 0.85, nom * 1.15
    print(f"  2EDR8259H R={r:5.1f}k (+-15 % from the research note): {lo:6.1f}..{hi:6.1f} ns  lower edge {'OK' if lo >= WIN[0] else 'below 391'}, upper edge {'OK' if hi <= WIN[1] else 'above 498 by %.0f ns' % (hi - WIN[1])}")
print("=> any driver whose DT spread exceeds +-12 % (all three candidates do) cannot sit inside the 391..498 ns window: re-run the D2 grid over a wider band first.")
sys.exit(0 if best is None else 1)   # exit 0 documents: no NCP resistor fits both edges
