"""Lowest true h_c at which C1 (fixed contact model at its nominal h) still meets B1-B3.

Turns the in-the-box result into the bench acceptance threshold for the cookware
survey (HANDOFF firmware/test section). Run: python h_floor.py -> h-floor.json
"""
import json
import os
from multiprocessing import Pool
from pathlib import Path

import screen as s

H_TRY = (400.0, 500.0, 600.0, 700.0, 850.0)


def job(a):
    pan, h, eta = a
    c = s.CANDS["C1"]
    s.apply(c)
    hn = s.h_nominal(c, s.h_spread(c))
    L, _ = s.run("C1", pan, h, eta, "kf_fixed", 900, hn)
    m = s.metrics(L)
    lim = 1.5 if s.es.PANS[pan]["sp"][1] <= 100 else 3.0
    return a, m["est_err_c_max_K"] <= 3.0, m["overshoot_K"] <= 5.0, max(abs(x) for x in m["hold_err_c_K"]) <= lim, m


if __name__ == "__main__":
    jobs = [(p, h, e) for p in s.es.PANS for h in H_TRY for e in s.es.ETA_SWEEP]
    with Pool(min(10, os.cpu_count() or 1)) as pool:
        res = pool.map(job, jobs)
    by_h = {}
    for (p, h, e), b1, b2, b3, m in res:
        d = by_h.setdefault(f"{h:.0f}", {"cases": 0, "all_pass": 0, "worst_err_K": 0.0, "worst_os_K": -99.0})
        d["cases"] += 1
        d["all_pass"] += int(b1 and b2 and b3)
        d["worst_err_K"] = max(d["worst_err_K"], m["est_err_c_max_K"])
        d["worst_os_K"] = max(d["worst_os_K"], m["overshoot_K"])
    c = s.CANDS["C1"]
    out = {"scope": __doc__.strip(), "by_true_h": by_h,
           "tau63_s": {k: round(s.tau63(c, float(k)), 2) for k in by_h}}
    Path(__file__).with_name("h-floor.json").write_text(json.dumps(out, indent=1) + "\n")
    for k, v in by_h.items():
        print(k, out["tau63_s"][k], v)
