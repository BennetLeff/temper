#!/usr/bin/env python3
"""S23 option C: pass limits for the TLV3201 common-mode bench characterisation, from the s23_optb.py allowances.

    python3 -I s23_bench.py   -> ../results/s23_bench.json (and stdout); run s23_optb.py first

Allowance A (mV) = the R0 floor margin / (A per mV) at the trip VCM: the adverse common-mode shift (VOS at the trip VCM
minus VOS at VCC/2, falling trip point, same VCC and temperature) the floor can absorb on top of the datasheet 4 mV.
Limit = A - U_meas. Pass: every unit <= limit AND the one-sided normal upper tolerance bound mean + k s <= limit.
"""
import sys
sys.dont_write_bytecode = True
import json
import math
from pathlib import Path

from scipy.stats import nct, norm

HERE = Path(__file__).resolve().parent
R = HERE.parent / "results"
U_MEAS = 0.03          # mV: 6.5-digit DMM on a 100 mV range differential, thermal EMF, fixture leakage (budget, not measured)


def k_factor(n, p, g):
    return nct.ppf(g, n - 1, norm.ppf(p) * math.sqrt(n)) / math.sqrt(n)


def main():
    ob = json.loads((R / "s23_optb.json").read_text())
    rows = ob["rows"]
    out = {"u_meas_mV": U_MEAS, "k": {f"n{n} {p}/{g}": round(k_factor(n, p, g), 3)
                                      for n in (20, 30, 45) for p, g in ((0.95, 0.95), (0.99, 0.95))},
           "nonparametric_zero_fail_n_95_95": math.ceil(math.log(0.05) / math.log(0.95)), "limits": []}
    for d in dict.fromkeys(r["design"] for r in rows):
        for net in ("release c17.5@61", "c28@55"):
            for h5 in ("Q1", "phys"):
                r0 = next(r for r in rows if r["design"] == d and r["network"] == net and r["reading"] == "R0" and r["hot5"] == h5)
                a = r0["floor_margin_A"] / r0["dI_dVOS_A_per_mV"]
                lim = a - U_MEAS
                k = k_factor(30, 0.99, 0.95)
                out["limits"].append({"design": d, "network": net, "hot5": h5, "vcm_trip_V": r0["vcm_nom_V"],
                                      "allowance_mV": round(a, 3), "limit_mV": round(lim, 3),
                                      "max_sigma_mV_if_mean_0p1_n30_99_95": round(max(0.0, (lim - 0.1) / k), 3)})
    (R / "s23_bench.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
