#!/usr/bin/env python3
"""Flicker screen for line-synchronous half-cycle bursts (DECISIONS.md 2026-10-05, low-power control).

Each burst switches the bridge from off to a power P and back, so the mains
current steps by I = P / (V * PF) twice per burst. The voltage change on the
reference impedance Z = R + jX for a near-unity-power-factor step is
dV ~= I (R cos(phi) + X sin(phi)), with d = dV / V.

IEC 61000-3-3 Annex B analytical method, for rectangular steps (form factor F = 1):
  t_f = 2.3 (F * d[%])^3.2  seconds per change,  Pst = (sum t_f / 600 s)^(1/3.2)
  limits: Pst <= 1.0, Plt <= 0.65 (steady repetition => Plt = Pst), d_c <= 3.3 %, d_max <= 4 %.
The method applies only when changes are at least 1 s apart, so the burst
period (two changes per burst) is held >= 2 s here.

Limits of this screen (state them; do not overclaim):
- IEC 61000-3-3 is written for 230/400 V systems with Zref = 0.4 + j0.25 ohm
  (phase + neutral). There is no harmonised 120 V reference impedance; the
  same Zref is used as a conservative proxy (North American residential
  service impedance is usually lower). IEEE 1453 adopts IEC 61000-4-15 with a
  120 V lamp model, which is more sensitive than the 230 V lamp at some
  frequencies; the analytical t_f formula is the 230 V curve.
- PF = 0.95 assumed for the unfiltered-bus bridge at low power (no committed PF figure).
Hence a PASS here is a screen, not compliance; a flickermeter run (IEC 61000-4-15,
120 V lamp) on the measured current is the closing evidence.

    python3 burst_flicker.py  ->  flicker.json, flicker.md
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
V, PF = 120.0, 0.95
R, X = 0.4, 0.25
POWERS = (100, 160, 200, 250, 300, 400, 500, 600)
PERIODS_S = (2, 3, 5, 10)


def d_pct(p):
    i = p / (V * PF)
    phi = math.acos(PF)
    return 100 * i * (R * math.cos(phi) + X * math.sin(phi)) / V


def pst(d, period_s):
    changes = 2 * 600 / period_s
    return (changes * 2.3 * d ** 3.2 / 600) ** (1 / 3.2)


def min_period(d):
    """Shortest burst period (>= 2 s) with Plt <= 0.65 and Pst <= 1."""
    # Plt = Pst = (2*600/T * 2.3 d^3.2 / 600)^(1/3.2) <= 0.65  =>  T >= 4.6 d^3.2 / 0.65^3.2
    return max(2.0, 4.6 * d ** 3.2 / 0.65 ** 3.2)


def main():
    rows = []
    for p in POWERS:
        d = d_pct(p)
        rows.append({"P_W": p, "step_A": round(p / (V * PF), 3), "d_pct": round(d, 3),
                     "pst_by_period": {t: round(pst(d, t), 3) for t in PERIODS_S},
                     "min_period_s_for_Plt_0p65": round(min_period(d), 2),
                     "d_within_3p3": d <= 3.3})
    res = {"method": "IEC 61000-3-3 Annex B analytical, F=1", "V": V, "PF": PF, "Zref_ohm": [R, X], "rows": rows}
    (HERE / "flicker.json").write_text(json.dumps(res, indent=1) + "\n")
    hdr = "| burst P (W) | step (A) | d (%) | " + " | ".join(f"Pst @ {t} s" for t in PERIODS_S) + " | min period for Plt ≤ 0.65 (s) |"
    lines = [hdr, "|" + " ---: |" * (4 + len(PERIODS_S))]
    for r in rows:
        lines.append(f"| {r['P_W']} | {r['step_A']} | {r['d_pct']} | " + " | ".join(str(r['pst_by_period'][t]) for t in PERIODS_S)
                     + f" | {r['min_period_s_for_Plt_0p65']} |")
    (HERE / "flicker.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
