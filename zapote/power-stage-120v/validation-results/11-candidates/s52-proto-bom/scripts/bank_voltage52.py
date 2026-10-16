#!/usr/bin/env python3
"""Stage 52: the bank's voltage rows against the fitted TDK B32643H8104J000 rating, with the s52 OCP band
(c51-bank-source/stage51/scripts/bank_voltage51.py's method and stresses; the KNSCHA MMK104J3DF1KN208G2 fallback and the
TDK B32643B8104J000 28 A part are listed beside it on the same stresses).

    python3 -I validation-results/11-candidates/s52-proto-bom/scripts/bank_voltage52.py
        -> s52-proto-bom/results/bank-voltage-s52.json, bank-voltage-s52.md

Run after s52-proto-bom/scripts/bands52.py (results/bands-s52.json, this board's solve). Inputs:
  * TDK B32643H8104J000 (B3264*H, June 2026, owner-supplied, sha256 69b56e62c56032229f60dd419c301ba16028da245fcbd56dc440abcf4f8ad663,
    not committed): p.14 'VR, DC = 2000 V DC; VRMS (f <= 1 kHz) VR, AC = 700 V AC'; p.15 VR,DC 2000 V at 105 C, 1.25 %/C of
    Vop derating for 105 C < T <= 125 C (VC(125 C) = 1500 V), Top,max 125 C (operating Top = ambient + self-heating);
    p.16 dV/dt 3800 V/us at 22.5 mm / 2000 V. These are c51-bank-source/scripts/b32643h.py's voltage rows.
  * KNSCHA MMK104J3DF1KN208G2 and TDK B32643B8104J000: bank_voltage51.py's ratings.
  * F3, the CT-failed double fault, dV/dt and the normal / no-pan stresses: as bank_voltage51.py (same 0.50 uF J bank).
Acceptance (ledger rules, as c49 / s51): normal peak <= 0.8 VR; no-pan <= 0.8 VC(Top,max); Vrms <= 0.8 VRMS; F3 <= 0.85 VR
at every R0 / R1 reading (audit.rs S49_BANK_VR) and <= VR at every reading; Z0,max x top <= VR; dV/dt <= the vendor value.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
VR_DIR = PS / "validation-results"
OUT = HERE.parent / "results"
F3_J, F3_TOP = 1683.0, 118.74
L_MAX, C_MIN = 66.5e-6 * 1.1, 0.50e-6 * 0.9
Z0_MAX = math.sqrt(L_MAX / C_MIN)
V_PK, V_RMS, V_NOPAN = 566.0, 268.0, 775.0
PARTS = {
    "B32643H8104J000": dict(role="fitted (stage 52 prototype lot)", VR=2000.0, VRMS=700.0, top_max=125.0, dvdt=3800.0,
                            vc=lambda t: 2000.0 if t <= 105 else 2000.0 * (1 - 0.0125 * (t - 105)),
                            source="TDK B3264*H June 2026 p.14 (VR, VRMS), p.15 (VR at 105 C, 1.25 %/C to 125 C, Top,max), "
                                   "p.16 (dV/dt 22.5 mm 2000 V)"),
    "MMK104J3DF1KN208G2": dict(role="in-stock fallback (not fitted)", VR=2000.0, VRMS=700.0, top_max=105.0, dvdt=2200.0,
                               vc=lambda t: 2000.0 if t <= 85 else 2000.0 * (1 - 0.0125 * (t - 85)),
                               source="KNSCHA KNS20200505002 p.1 / p.4 (VR, 40/105/56, 1.6 UR 5 s); MMKP82 family sheet "
                                      "2026.9.16 (700 VAC, 1.25 %/C above 85 C, 2200 V/us at P27.5)"),
    "B32643B8104J000": dict(role="28 A part (not fitted)", VR=2000.0, VRMS=500.0, top_max=125.0, dvdt=3800.0,
                            vc=lambda t: 2000.0 if t <= 85 else 2000.0 * (165 - t) / 80,
                            source="TDK B3264*B June 2026 p.11 (VR, VRMS), p.12 (VC, Top,max), p.13 (dV/dt 22.5 mm)"),
}


def main():
    bands = json.loads((OUT / "bands-s52.json").read_text())
    df = json.loads((VR_DIR / "02-protection-timing/bank-ov-double-fault/results.json").read_text())
    assert df["controls"]["shunt_band_R34_12k6_A"] == [66.3, F3_TOP] and df["governing_Vc_pk_V"] == 1702.4, df["controls"]
    assert abs(df["controls"]["z0_max_ohm"] - round(Z0_MAX, 2)) < 0.01, (df["controls"]["z0_max_ohm"], Z0_MAX)
    dvdt = df["clamp_sizing"]["dVdt_at_I_off_V_per_us"]
    rows = []
    for r in bands["tlv3201_readings"]:
        top = r["ocp_top_A"]
        f3 = F3_J * top / F3_TOP
        rows.append({"network": r["network"], "reading": r["reading"], "hot5": r["hot5"], "ocp_top_A": top,
                     "F3_V": round(f3, 1), "Z0max_x_top_V": round(Z0_MAX * top, 1)})
    gated = [x for x in rows if x["reading"] in ("R0", "R1")]
    worst = max(gated, key=lambda x: x["ocp_top_A"])
    worst_all = max(rows, key=lambda x: x["ocp_top_A"])
    parts = {}
    for mpn, p in PARTS.items():
        vct = p["vc"](p["top_max"])
        lim = {"V 28 A": 0.8 * p["VR"], "no-pan": 0.8 * vct, "Vrms": 0.8 * p["VRMS"], "F3 R0/R1": 0.85 * p["VR"],
               "F3 any reading": p["VR"], "double fault Z0max x top": p["VR"], "dV/dt": p["dvdt"]}
        st = {"V 28 A": V_PK, "no-pan": V_NOPAN, "Vrms": V_RMS, "F3 R0/R1": worst["F3_V"], "F3 any reading": worst_all["F3_V"],
              "double fault Z0max x top": worst_all["Z0max_x_top_V"], "dV/dt": dvdt}
        parts[mpn] = {"role": p["role"], "VR_V": p["VR"], "VRMS_V": p["VRMS"], "Top_max_C": p["top_max"],
                      "VC_at_Top_max_V": round(vct, 1), "dVdt_V_per_us": p["dvdt"], "source": p["source"],
                      "rows": {k: {"stress": st[k], "limit": round(lim[k], 1), "utilisation": round(st[k] / lim[k], 4),
                                   "margin": round(lim[k] - st[k], 1)} for k in lim},
                      "pass": all(st[k] <= lim[k] for k in lim)}
    out = {"board_sha256": bands["board_sha256"], "z0_max_ohm": round(Z0_MAX, 3),
           "F3_basis": {"F3_J_V": F3_J, "at_top_A": F3_TOP, "V_per_A": round(F3_J / F3_TOP, 3)},
           "readings": rows, "worst_R0_R1": worst, "worst_any_reading": worst_all,
           "dVdt": {"V_per_us": dvdt}, "parts": parts}
    OUT.mkdir(exist_ok=True)
    (OUT / "bank-voltage-s52.json").write_text(json.dumps(out, indent=1) + "\n")
    L = ["# Bank voltage rows, stage 52 (generated by s52-proto-bom/scripts/bank_voltage52.py; do not edit)\n",
         f"Board {bands['board_sha256'][:8]}. F3 = {F3_J:g} V x top / {F3_TOP} A; Z0,max {Z0_MAX:.3f} ohm; dV/dt {dvdt} V/us. "
         f"Worst R0/R1: {worst['network']} {worst['reading']} {worst['hot5']}, top {worst['ocp_top_A']} A, F3 {worst['F3_V']} V; "
         f"worst any reading: {worst_all['network']} {worst_all['reading']} {worst_all['hot5']}, F3 {worst_all['F3_V']} V, "
         f"Z0max x top {worst_all['Z0max_x_top_V']} V.\n",
         "| Part | Row | Stress | Limit | Utilisation | Margin |", "|---|---|---:|---:|---:|---:|"]
    for mpn, p in parts.items():
        for k, r in p["rows"].items():
            L.append(f"| {mpn} ({p['role']}) | {k} | {r['stress']} | {r['limit']} | {r['utilisation']} | {r['margin']:+.1f} |")
    L += ["", "| Network | Reading | HOT5 | OCP top (A) | F3 (V) | Z0max x top (V) |", "|---|---|---|---:|---:|---:|"]
    for x in rows:
        L.append(f"| {x['network']} | {x['reading']} | {x['hot5']} | {x['ocp_top_A']} | {x['F3_V']} | {x['Z0max_x_top_V']} |")
    L += ["", f"Pass: { {m: p['pass'] for m, p in parts.items()} }"]
    (OUT / "bank-voltage-s52.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    _s.exit(0 if all(p["pass"] for p in parts.values()) else 1)


if __name__ == "__main__":
    main()
