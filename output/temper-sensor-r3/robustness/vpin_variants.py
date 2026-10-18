"""Window design alternatives in the Python screen (robustness/DECISIONS.md R-A4).

The contact-shift window (shift_kf.py) pins the pan's rate v at the snapshot. Its
G estimate is relative to the model before the step, and its error is largest at
the start of a ramp, where the pan accelerates. Alternatives run on the 64-case
gated h-step set plus the stress (constant h_c outside the design spread) and
design / nominal / food / loss runs (pyloop.py variant
V3L, true a):
  v_mode   slope (reading slope over v_ref_s before the snapshot, chosen),
           kf (the KF's v at the snapshot), quad (end slope of a quadratic fit
           over v_ref_s), short (reading slope over the last 2 s)
  accept_bias_sd  0 / 0.5 / 1.0 (chosen): accept ln G minus this many posterior sd
  steady_v0  in a window opened while the loop holds its setpoint, pin v = 0
           instead of the reading slope

Run: python vpin_variants.py -> vpin-variants.json (about 5 min on 10 cores)
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

VARIANTS = {"slope_bias1.0": {}, "kf_bias1.0": {"v_mode": "kf"}, "quad_bias1.0": {"v_mode": "quad"},
            "short_bias1.0": {"v_mode": "short"}, "slope_bias0": {"accept_bias_sd": 0.0},
            "slope_bias0.5": {"accept_bias_sd": 0.5},
            "slope_bias1.0_steady_v0": {"v_steady_zero": True}}


def job(args):
    name, c = args
    L, info = pl.run(c["pan"], c["h"], c["eta"], c["seed"], "V3L", c.get("h_spec"), food_at=c.get("food_at"),
                     loss_at=c.get("loss_at"), cand_opt={"kf": VARIANTS[name]})
    m = pl.metrics(L, c.get("loss_at"), c.get("ev_at"), 20.0)
    return {"variant": name, "kind": c["kind"], "pan": c["pan"], "label": c.get("label"), "h": c["h"],
            "est_err_K": m["est_err_c_max_K"], "overshoot_K": m["overshoot_K"],
            "hold_K": max(abs(x) for x in m["hold_err_c_K"]), "latch": info["detected_at"] is not None,
            "cs_events": info["cs_events"][:4]}


def main():
    C = cs.hs_cases() + cs.stress_cases() + [c for c in cs.base_cases()
                                             if c["kind"] in ("design", "food", "nominal", "loss")]
    with Pool(min(10, os.cpu_count() or 1)) as pool:
        rows = pool.map(job, [(v, c) for v in VARIANTS for c in C], chunksize=2)
    summ = {}
    for v in VARIANTS:
        H = [r for r in rows if r["variant"] == v and r["kind"] == "hs"]
        D = [r for r in rows if r["variant"] == v and r["kind"] == "design"]
        summ[v] = {"hs_worst_overshoot_K": max(r["overshoot_K"] for r in H),
                   "hs_worst_overshoot_with_window_K": max((r["overshoot_K"] for r in H if r["cs_events"]), default=0.0),
                   "hs_worst_est_err_K": max(r["est_err_K"] for r in H), "hs_worst_hold_K": max(r["hold_K"] for r in H),
                   "hs_B1_3K": sum(r["est_err_K"] <= 3.0 for r in H), "hs_B2_5K": sum(r["overshoot_K"] <= 5.0 for r in H),
                   "design_B1": sum(r["est_err_K"] <= 3.0 for r in D),
                   "stress_B1": sum(r["est_err_K"] <= 3.0 for r in rows if r["variant"] == v and r["kind"] == "stress"),
                   "windows_without_contact_change": sum(bool(r["cs_events"]) for r in rows if r["variant"] == v
                                                         and r["kind"] in ("stress", "design", "nominal")),
                   "design_worst_overshoot_K": max(r["overshoot_K"] for r in D),
                   "false_latches_nominal_food": sum(r["latch"] for r in rows if r["variant"] == v
                                                     and r["kind"] in ("nominal", "food")),
                   "loss_detected": sum(r["latch"] for r in rows if r["variant"] == v and r["kind"] == "loss")}
    out = {"scope": __doc__.strip(), "summary": summ, "rows": rows}
    (HERE / "vpin-variants.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    for v, d in summ.items():
        print(v, d)


if __name__ == "__main__":
    main()
