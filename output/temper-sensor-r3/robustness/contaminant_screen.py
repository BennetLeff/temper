"""Problem B in the Python screen: oil, water and crud cases (cases.contaminant_cases)
through the closed loop of pyloop.py: baseline V0, the h_c-step window V3, the
window plus the plain latent-plateau cap V3Lc (rejected: it can stall a cook at
100 C), and the chosen V3L (window plus the energy-budget plateau guard).

Bars per case: B1 |T_hat - T_c| <= 3 K from 10 s on (outside 60 s after a water
arrival / 20 s after a contact event); B2 overshoot of T_c <= 5 K; B3 hold error;
SAFE: true T_c never above SP + 15 K (the task's safety line) and no false D1 latch.
The C co-sim (hc_cosim.py) repeats these with the firmware.

Run: python contaminant_screen.py -> contaminant-screen.json (about 2 min on 10 cores)
"""
from __future__ import annotations

import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cases as cs  # noqa: E402
import pyloop as pl  # noqa: E402

VARIANTS = ("V0", "V3", "V3Lc", "V3L")


def judge(c, L, m, info):
    lim = cs.b3_limit(c["pan"])
    t, sp, Tc, Tm = L[:, 0], L[:, 1], L[:, 3], L[:, 4]
    row = {**{k: v for k, v in c.items() if k not in ("truth", "h_spec")}, "truth": str(c.get("truth")),
           "h_spec": str(c.get("h_spec")), **m, **{k: v for k, v in info.items() if k != "stat"}}
    row["Tc_max_over_sp_K"] = round(float((Tc - sp).max()), 2)
    row["Tmean_max_over_sp_K"] = round(float((Tm - sp).max()), 2)
    row["B1"] = m["est_err_c_max_K"] <= 3.0
    row["B2"] = m["overshoot_K"] <= 5.0
    row["B3"] = max(abs(x) for x in m["hold_err_c_K"]) <= lim
    row["false_latch"] = info["detected_at"] is not None
    row["SAFE"] = row["Tc_max_over_sp_K"] <= 15.0
    return row


def job(args):
    variant, c = args
    tf = cs.make_truth(c.get("truth"))
    L, info = pl.run(c["pan"], c["h"], c["eta"], c["seed"], variant, c.get("h_spec"), truth_factory=tf)
    m = pl.metrics(L, None, c.get("ev_at"), c.get("settle", 20.0))
    return judge(c, L, m, info)


def summarise(rows):
    out = {}
    for v in VARIANTS:
        d = {}
        for g in ("oil", "water", "crud"):
            G = [r for r in rows if r["variant"] == v and r["group"] == g]
            d[g] = {"cases": len(G), **{b: sum(r[b] for r in G) for b in ("B1", "B2", "B3", "SAFE")},
                    "false_latches": sum(r["false_latch"] for r in G),
                    "worst_Tc_over_sp_K": max(r["Tc_max_over_sp_K"] for r in G),
                    "worst_Tmean_over_sp_K": max(r["Tmean_max_over_sp_K"] for r in G),
                    "worst_est_err_K": max(r["est_err_c_max_K"] for r in G)}
        out[v] = d
    return out


def main():
    C = cs.contaminant_cases()
    jobs = [(v, c) for v in VARIANTS for c in C]
    with Pool(min(10, os.cpu_count() or 1)) as pool:
        rows = pool.map(job, jobs, chunksize=2)
    for r, (v, _) in zip(rows, jobs):
        r["variant"] = v
    out = {"scope": __doc__.strip(), "summary": summarise(rows), "rows": rows}
    (HERE / "contaminant-screen.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    for v, d in out["summary"].items():
        print("==", v)
        for g, x in d.items():
            print("   ", g, x)
    for r in rows:
        if not (r["B1"] and r["B2"] and r["B3"] and r["SAFE"]) or r["false_latch"]:
            print(f"{r['variant']} {r['group']:5s} {r['pan'][:10]:10s} {r['label'][:46]:46s} B1 {r['est_err_c_max_K']:6.2f} "
                  f"os {r['overshoot_K']:6.2f} hold {r['hold_err_c_K']} Tc>sp {r['Tc_max_over_sp_K']:6.2f} "
                  f"latch {r['false_latch']} ev {r['cs_events'][:4]}")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
