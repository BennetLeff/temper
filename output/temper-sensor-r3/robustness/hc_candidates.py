"""Problem A (DECISIONS open item 9): compare the h_c-step candidates in the Python screen.

Candidates (pyloop.py; all use the firmware's cartridge constants, D1 in
screen.py form, the frozen rate PID with the true a):
  V0  baseline: fixed contact model, no residual detector
  V1  residual detector -> cap the power at the pre-event mean for 30 s
  V2  residual detector -> request a D1 probe at once ("use D1 more aggressively")
  V3  residual detector -> contact-shift window (shift_kf.py): rewind 2.5 s, pin the
      pan, estimate ln G, accept only a lower contact (or a return toward nominal),
      escalate to a D1 probe when the fall is faster than any partial contact
The residual detector is the same in V1-V3 (shift_kf.ShiftKF.triggered).

Cases (cases.py): the 64-case gated h-step set, the reported deep / re-seat /
gradual cases, and screen.py's 16 design, 4 nominal, 3 food and 4 loss runs.
Bars per case: B1 |T_hat - T_c| <= 3 K from 10 s on, outside 20 s after each
contact event (the whole run for design cases); B2 overshoot of T_c <= 5 K;
B3 hold error (1.5 K at <= 100 C, else 3 K); no false D1 latch.

Run: python hc_candidates.py  -> hc-candidates.json  (about 3 min on 10 cores)
"""
from __future__ import annotations

import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cases as cs  # noqa: E402
import pyloop as pl  # noqa: E402

VARIANTS = ("V0", "V1", "V2", "V3f", "V3", "V3L")


def job(args):
    variant, c = args
    L, info = pl.run(c["pan"], c["h"], c["eta"], c["seed"], variant, c.get("h_spec"),
                     food_at=c.get("food_at"), loss_at=c.get("loss_at"))
    m = pl.metrics(L, c.get("loss_at"), c.get("ev_at"), c.get("settle", 20.0))
    lim = cs.b3_limit(c["pan"])
    row = {"variant": variant, **{k: v for k, v in c.items() if k != "h_spec"}, "h_spec": str(c.get("h_spec")),
           **m, **info}
    if c["kind"] not in ("loss", "nominal", "food"):
        row["B1"] = m["est_err_c_max_K"] <= 3.0
        row["B2"] = m["overshoot_K"] <= 5.0
        row["B3"] = max(abs(x) for x in m["hold_err_c_K"]) <= lim
    if c["kind"] == "loss":
        row["suspect_s"] = None if info["suspect_at"] is None else round(info["suspect_at"] - c["loss_at"], 1)
        row["confirm_s"] = None if info["detected_at"] is None else round(info["detected_at"] - c["loss_at"], 1)
    row["false_latch"] = c["kind"] != "loss" and info["detected_at"] is not None
    return row


def summarise(rows):
    out = {}
    for v in VARIANTS:
        R = [r for r in rows if r["variant"] == v]
        d = {}
        for kind in ("design", "hs", "hs_deep", "hs_back", "hs_grad"):
            G = [r for r in R if r["kind"] == kind]
            if not G:
                continue
            d[kind] = {"cases": len(G), "B1": sum(r["B1"] for r in G), "B2": sum(r["B2"] for r in G),
                       "B3": sum(r["B3"] for r in G), "all": sum(r["B1"] and r["B2"] and r["B3"] for r in G),
                       "worst_overshoot_K": max(r["overshoot_K"] for r in G),
                       "worst_est_err_K": max(r["est_err_c_max_K"] for r in G),
                       "worst_hold_K": max(max(abs(x) for x in r["hold_err_c_K"]) for r in G),
                       "probes": sum(r["probes"] for r in G), "false_latches": sum(r["false_latch"] for r in G)}
        for kind in ("nominal", "food"):
            G = [r for r in R if r["kind"] == kind]
            d[kind] = {"cases": len(G), "probes": sum(r["probes"] for r in G),
                       "false_latches": sum(r["false_latch"] for r in G)}
        G = [r for r in R if r["kind"] == "loss"]
        d["loss"] = {"cases": len(G), "detected": sum(r["detected_at"] is not None for r in G),
                     "worst_suspect_s": max((r["suspect_s"] or 1e9) for r in G),
                     "worst_confirm_s": max((r["confirm_s"] or 1e9) for r in G),
                     "worst_Tc_over_sp_K": max(r["Tc_max_over_sp_after_loss_K"] for r in G)}
        out[v] = d
    return out


def main():
    allc = cs.hs_cases() + cs.report_cases() + cs.base_cases()
    jobs = [(v, c) for v in VARIANTS for c in allc]
    with Pool(min(10, os.cpu_count() or 1)) as pool:
        rows = pool.map(job, jobs, chunksize=4)
    summ = summarise(rows)
    out = {"scope": __doc__.strip(), "summary": summ, "rows": rows}
    (HERE / "hc-candidates.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    for v, d in summ.items():
        print("==", v)
        for k, x in d.items():
            print("   ", k, x)


if __name__ == "__main__":
    main()
