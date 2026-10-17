#!/usr/bin/env python3
"""Bank voltage / pulse rows of the s49 datasheet ledger (ledger49.py) for each replacement candidate, plus the exact
margins of a generic 1600 V part.

    python3 -I scripts/voltage_rows.py   -> results/voltage_rows.json, results/voltage_rows.md

Stresses (unchanged by the part as long as the bank stays 0.50 uF J; F3 and the double fault scale 1 / C_min):
  V peak 28 A 566 V (c34: 268 Vrms bound x 2.113); V rms 268 V; no-pan fault 775 V peak;
  F3 = 1683 V x OCP top / 118.74 A at each s49 band reading; CT-failed double fault Z0,max x OCP top (Z0,max 12.75 ohm);
  dV/dt 345.4 V/us at the largest turn-off current (bank-ov-double-fault clamp sizing). All from data/bank-voltage-s49.json
  (byte copy of the s49 branch's c49-c34-bank/results/bank-voltage-s49.json, commit db60f2692).
Rules (ledger49.py checks): normal peak <= 0.8 VR; no-pan <= 0.8 VC(Top,max) (VC = the vendor's category-voltage
derating at its Top,max); Vrms <= 0.8 VRMS; F3 <= 0.85 VR at every R0 / R1 reading (audit.rs S49_BANK_VR) and <= VR at
every reading; Z0,max x top <= VR at every reading; dV/dt <= the vendor's rating for the pitch.
Pulse energy (k0, informational): the F3 sine taken as a repeated -Vp..+Vp swing at 35 kHz,
k0 = 2 * integral over the half-period of (dV/dt)^2 dt = pi * omega * Vp^2 (k0_sine), against the vendor's k0 where given.
In the 1600 V margin table a POSITIVE "F3 - 1360" / "F3 - 1600" is the overrun of the limit.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BV = json.loads((ROOT / "data/bank-voltage-s49.json").read_text())
V_PK, V_RMS, V_NOPAN = 566.0, 268.0, 775.0
DVDT = BV["dVdt"]["V_per_us"]
R01 = [r for r in BV["rows"] if r["reading"] in ("R0", "R1")]
F3_R01 = max(r["F3_V"] for r in R01)
F3_ALL = max(r["F3_V"] for r in BV["rows"])
Z0_ALL = max(r["Z0max_x_top_V"] for r in BV["rows"])

PARTS = [  # id, mpn, VR, VRMS, Top,max, VC rule (callable on T), dV/dt rating, k0 rating (V^2/us) or None, source
    ("c34", "B32643B8104J000", 2000, 500, 125, lambda t: 2000 if t <= 85 else 2000 * (165 - t) / 80, 3800, 15e6,
     "TDK B3264*B p.11/p.12/p.13"),
    ("knscha", "MMK104J3DF1KN208G2", 2000, 700, 105, lambda t: 2000 if t <= 85 else 2000 * (1 - 0.0125 * (t - 85)), 2200, None,
     "KNSCHA MMKP82: VR 2000 V / 700 VAC (family chart title), DC derating 1.25 %/C above 85 C (family sheet 2026.9.16), "
     "Top,max 105 C (C528962 sheet 40/105/56), dV/dt 2200 V/us at P27.5 2000 V (family sheet table)"),
    ("r75", "R75UR31004030J", 2000, 700, 105, lambda t: 2000 if t <= 85 else 2000 * (1 - 0.02 * (t - 85)), 2000, 8e6,
     "KEMET F3106_R75 p.5 (2 %/C DC derating above 85 C), p.24 row (dV/dt 2000 V/us, k0 8e6 V2/us)"),
    ("r76", "R76UR3100SE30J", 2000, 700, 110, lambda t: 2000 if t <= 85 else 2000 * (1 - 0.0125 * (t - 85)), 2500, None,
     "KEMET F3034_R76 p.5 / p.22 (c34 parts_kemet.json: 2000 V / 700 VAC, dV/dt 2500); derating 1.25 %/C ASSUMED"),
    ("wima", "MKP1U031006D00JSSD", 2000, 700, 100, lambda t: 2000 if t <= 85 else 2000 * (1 - 0.0135 * (t - 85)), None, None,
     "WIMA MKP 10 (03.26): 2000 VDC / 700 VAC, 1.35 %/K derating (p.1, from 85 C ASSUMED), 55/100/56"),
    ("1600V generic (e.g. KNSCHA MMK104J3CESKN158G2, JLC 11,383)", "1600 V class", 1600, 650, 105,
     lambda t: 1600 if t <= 85 else 1600 * (1 - 0.0125 * (t - 85)), 3000, None, "KNSCHA family sheet, 1600 V P22.5 dV/dt 3000 V/us"),
    ("fitted (reference)", "B32654A1104J000", 1600, 500, 110, lambda t: 1600 if t <= 85 else 1600 * (1 - 0.0125 * (t - 85)), 1000,
     None, "TDK B3265x p.35/p.36 (VC rule ASSUMED 1.25 %/C)"),
]


def k0_sine(vp, f):
    """k0 = 2 * integral over one rising half-period of (dV/dt)^2 dt, V = Vp sin(wt), from -Vp to +Vp: = pi * w * Vp^2."""
    w = 2 * math.pi * f
    return math.pi * w * vp * vp / 1e6          # V^2/us


def main():
    out = {"stresses": {"V_pk_28A": V_PK, "V_rms_28A": V_RMS, "V_nopan_pk": V_NOPAN, "F3_worst_R0_R1_V": F3_R01,
                        "F3_worst_any_V": F3_ALL, "Z0max_x_top_worst_V": Z0_ALL, "dVdt_V_per_us": DVDT,
                        "k0_F3_at_35kHz_V2_per_us": round(k0_sine(F3_R01, 35e3)), "k0_normal_28A_35kHz_V2_per_us": round(k0_sine(V_PK, 35e3)),
                        "source": "data/bank-voltage-s49.json (s49 OCP band, board 73702f18)"}, "parts": {}}
    for pid, mpn, vr, vrms, top, vc, dvdt, k0, src in PARTS:
        vct = vc(top)
        rows = {
            "V 28 A (<= 0.8 VR)": V_PK / vr / 0.8,
            "no-pan (<= 0.8 VC(Top,max))": V_NOPAN / vct / 0.8,
            "Vrms (<= 0.8 VRMS)": V_RMS / vrms / 0.8,
            "F3 R0/R1 (<= 0.85 VR)": F3_R01 / vr / 0.85,
            "F3 any reading (<= VR)": F3_ALL / vr,
            "double fault Z0max x top (<= VR)": Z0_ALL / vr,
            "dV/dt": DVDT / dvdt if dvdt else None,
            "k0 F3 sine (info)": k0_sine(F3_R01, 35e3) / k0 if k0 else None}
        out["parts"][pid] = {"mpn": mpn, "VR": vr, "VRMS": vrms, "Top_max_C": top, "VC_at_Top_max_V": round(vct, 1), "source": src,
                             "utilisation_of_limit": {k: (round(v, 3) if v is not None else None) for k, v in rows.items()},
                             "all_pass": all(v is None or v <= 1.0 for k, v in rows.items() if "info" not in k)}
    # exact 1600 V margins per reading
    m16 = []
    for r in BV["rows"]:
        m16.append({"network": r["network"], "reading": r["reading"], "hot5": r["hot5"], "ocp_top_A": r["ocp_top_A"], "F3_V": r["F3_V"],
                    "F3_minus_0.85x1600_V": round(r["F3_V"] - 1360.0, 1), "F3_minus_1600_V": round(r["F3_V"] - 1600.0, 1),
                    "Z0max_x_top_V": r["Z0max_x_top_V"], "1600_minus_Z0max_x_top_V": round(1600 - r["Z0max_x_top_V"], 1)})
    out["margins_1600V"] = m16
    out["top_needed_for_1600V"] = {"F3 <= 0.85 x 1600 (1360 V)": round(1360 * 118.74 / 1683, 2),
                                   "F3 <= 1600 V": round(1600 * 118.74 / 1683, 2), "Z0max x top <= 1600 V": round(1600 / BV["z0_max_ohm"], 2)}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/voltage_rows.json").write_text(json.dumps(out, indent=1) + "\n")
    keys = list(next(iter(out["parts"].values()))["utilisation_of_limit"])
    L = ["| part | VR / VRMS / Top,max / VC(Top) | " + " | ".join(keys) + " | all pass |", "|---" * (len(keys) + 3) + "|"]
    for pid, p in out["parts"].items():
        u = p["utilisation_of_limit"]
        L.append(f"| {pid} {p['mpn']} | {p['VR']} / {p['VRMS']} / {p['Top_max_C']} / {p['VC_at_Top_max_V']} | " +
                 " | ".join("-" if u[k] is None else f"{u[k]:.3f}" for k in keys) + f" | {p['all_pass']} |")
    L += ["", "Utilisation = stress / allowed (<= 1.000 passes). 1600 V per reading (V):", "",
          "| network | reading | HOT5 | top A | F3 | F3 - 1360 | F3 - 1600 | Z0max x top | 1600 - Z0max x top |", "|---|---|---|---|---|---|---|---|---|"]
    for r in m16:
        L.append(f"| {r['network']} | {r['reading']} | {r['hot5']} | {r['ocp_top_A']} | {r['F3_V']} | {r['F3_minus_0.85x1600_V']:+.1f} | "
                 f"{r['F3_minus_1600_V']:+.1f} | {r['Z0max_x_top_V']} | {r['1600_minus_Z0max_x_top_V']:+.1f} |")
    L += ["", f"OCP top a 1600 V part would need (A): {out['top_needed_for_1600V']}; s49 R0 release top is 114.575 A."]
    (ROOT / "results/voltage_rows.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
