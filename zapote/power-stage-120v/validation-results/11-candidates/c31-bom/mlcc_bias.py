#!/usr/bin/env python3
"""Effective capacitance of the 24 x 10 uF 50 V X7R 1210 reservoirs at their rail voltage (stage 31, DECISIONS 34).

    python3 -I mlcc_bias.py            ->  mlcc_bias.json beside this script; exit 1 if a check fails

Compares the stage-30 part (Taiyo Yuden UMK325AB7106KM-T) with the stage-31 part (Samsung CL32B106KBJNNNE) on the
same basis: nominal x (1 - 10 % tolerance) x (1 + dC/C at the rail's DC bias, 25 C) x (1 + dC/C at 100 C, 0 V).
For Samsung a second, harsher figure also applies its bias-and-temperature curve (25 V: 25 C -50.1 %, 100 C -54.7 %),
as the extra factor 0.453 / 0.499 on top of the 25 C bias value. No such curve exists for the Taiyo part.

Read-off points (vendor characteristic data; the documents themselves are not in the repo):
- Taiyo Yuden UMK325AB7106KM: TY-COMPAS "Electrical Characteristics Data" 20R2A03, "DC Bias Char." and
  "Capacitance Temp." graphs (https://ds.yuden.co.jp/TYCOMPAS/ut/detail?pn=UMK325AB7106KM-T&u=M), read off the
  graph: about +/-2 % points. The curve rises about +5 % near 2 V; no gain is credited (0 %).
- Samsung CL32B106KBJNNNE: product.samsungsem.com/mlcc/CL32B106KBJNNN.do, "DCBias" (1 kHz, 161 tabulated points,
  linear interpolation), "TCC" and "BiasTCC" data series.
Neither vendor states the AC test level of its bias curve, so the two curves may not be measured identically. Ageing is
not included.

Checks:
- SW-N and LEG_RET-N_LS reservoirs (2 V): >= 10 uF effective per pair (native-21/ECO.md:44-51, acceptance condition).
- P-N (17 V): the module start-up bound. The RECOM soft-start passed with 41.4 uF on P-N (ALT-BIAS.md s.3.4,
  13.3 ms against 16 ms at the pessimistic 60 mA ceiling). The as-built P-N bank is 21.4 uF nominal
  (C104 or C108 10 uF + C11 or C18 10 uF + C145 or C147 1 uF + 4 x 100 nF); no part can exceed its nominal, so the
  swap stays inside the simulated passing case.
- Every other rail: the stage-31 part keeps >= 97 % of the stage-30 part's effective value (no rail loses more than
  3 %); the absolute values are reported.
Not a check here: the s19b rubric's BP-04 target (>= 70 % of design capacitance per rail). The 2 V and 5 V positions
meet it with either part; at 15 / 17 / 24 V neither part does (stage 31 raises them from 37-22 % to 57-39 %
of nominal at 100 C with tolerance), so BP-04 stays open for those rails.
"""
import json
import sys
from pathlib import Path

NOMINAL_UF = 10.0
TOL = 0.10
BIAS = {   # dC/C (%) at DC bias (V), 25 C
    "UMK325AB7106KM-T": {2: 0.0, 5: -4.0, 15: -57.0, 17: -63.0, 24: -74.0},
    "CL32B106KBJNNNE": {2: 0.0, 5: -6.07, 15: -34.47, 17: -39.95, 24: -55.78},
}
TEMP100 = {"UMK325AB7106KM-T": -5.1, "CL32B106KBJNNNE": -2.7}   # dC/C (%) at 100 C, 0 V
SAMSUNG_BIAS_TEMP = (1 - 0.547) / (1 - 0.501)                   # 25 V curve: 100 C over 25 C
RAILS = [   # (rail, volts, designators)
    ("SW_A-N_HA / SW_B-N_HB (driver VSS reservoirs)", 2, ["C90", "C91", "C94", "C95"]),
    ("LEG_RET-N_LS (LS driver VSS reservoirs)", 2, ["C92", "C93", "C96", "C97"]),
    ("5 V rails (HOT5, LS_V5, HS monitor 5 V)", 5, ["C26", "C132", "C136", "C140"]),
    ("V15_LS", 15, ["C9", "C16", "C24", "C99", "C100"]),
    ("P_H-N_H (module output span)", 17, ["C104", "C108"]),
    ("V24_RAW", 24, ["C98", "C102", "C103", "C106", "C107"]),
]
PN_NOMINAL_UF = 10 + 10 + 1 + 4 * 0.1
PN_SIMULATED_PASS_UF = 41.4


def eff(mpn, v, harsh=False):
    c = NOMINAL_UF * (1 - TOL) * (1 + BIAS[mpn][v] / 100) * (1 + TEMP100[mpn] / 100)
    if harsh and mpn == "CL32B106KBJNNNE":
        c = NOMINAL_UF * (1 - TOL) * (1 + BIAS[mpn][v] / 100) * SAMSUNG_BIAS_TEMP
    return round(c, 2)


def main():
    rows, fails = [], []
    for rail, v, refs in RAILS:
        old, new = eff("UMK325AB7106KM-T", v), eff("CL32B106KBJNNNE", v)
        row = {"rail": rail, "volts": v, "designators": refs, "per_part_uF_stage30": old, "per_part_uF_stage31": new,
               "per_part_uF_stage31_bias_temp": eff("CL32B106KBJNNNE", v, harsh=True), "ratio_new_over_old": round(new / old, 3)}
        if v == 2:
            pair = 2 * min(new, row["per_part_uF_stage31_bias_temp"])
            row["pair_uF_stage31"] = round(pair, 2)
            row["check"] = f"pair >= 10 uF effective (ECO.md): {pair:.2f}"
            if pair < 10:
                fails.append(rail)
        elif new / old < 0.97:
            fails.append(rail)
        rows.append(row)
    pn = {"as_built_nominal_uF": PN_NOMINAL_UF, "simulated_pass_uF": PN_SIMULATED_PASS_UF,
          "ok": PN_NOMINAL_UF <= PN_SIMULATED_PASS_UF}
    if not pn["ok"]:
        fails.append("P-N start-up bound")
    out = {"rows": rows, "pn_startup_bound": pn, "fails": fails, "pass": not fails}
    (Path(__file__).resolve().parent / "mlcc_bias.json").write_text(json.dumps(out, indent=1) + "\n")
    for r in rows:
        print(f"{r['rail']:48s} {r['volts']:>2} V  {r['per_part_uF_stage30']:5.2f} -> {r['per_part_uF_stage31']:5.2f} uF "
              f"(x{r['ratio_new_over_old']}; with bias-temp {r['per_part_uF_stage31_bias_temp']:.2f})")
    print(f"P-N nominal {PN_NOMINAL_UF:.1f} uF <= simulated-pass {PN_SIMULATED_PASS_UF} uF: {pn['ok']}")
    print("PASS" if not fails else f"FAIL {fails}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
