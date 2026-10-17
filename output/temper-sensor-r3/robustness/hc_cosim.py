"""C-in-the-loop co-sim of the h_c-step set and the oil / water / crud cases.

The firmware's C1 loop (firmware/components/control/pan_temp_loop.c with the
contact-shift window, contact_shift.c, and the latent-plateau guard in
pan_rate_pid.c; DECISIONS.md D-CSW / D-LPG) closes the loop around the Python
truth plants through ../firmware/cosim.py run_case (same per-step order, D1 and
the runaway supervisor on, Python double-precision shadow for parity). Cases
come from cases.py; the true contact follows pyloop.h_profile, contaminated
contacts the truths of contaminants.py.

Each case runs twice per gain mode (true / id_measured / id_estimated):
  after   the firmware as committed
  before  the same firmware with the window and the guard switched off
          (sim_set csw 0, lpg 0): the sensor-r3 loop before this study

Bars (DECISIONS.md R-HS, R-CT), gated on "after" in every gain mode:
  HS (64 h_c steps 1000 or the pan's design-mid h_c -> 600 / 300, at 100 / 250 /
  365 / 500 s, 4 pans):
    R-HS1  overshoot of T_c <= 5 K (B2) on every case
    R-HS2  |T_hat - T_c| <= 5 K from 10 s on, outside 20 s after the step
    R-HS3  |hold error| <= 5 K on every case D1 did not latch
    R-HS4  no runaway-supervisor latch or R1 trip; no D1 latch except the one
           known case (LATCH_OK: the water pot 5811 -> 300 at 250 s, a 19x drop
           that leaves the probe response below D1's threshold; it latches
           before this change and in the Python screen too; power off, safe side)
    R-HS5  C vs Python shadow rms <= 0.05 K
  B1 (3 K) and B3 (1.5 / 3 K) are reported: a step to 300 or 600 W/m2K leaves
  the C1 design contact range (screen.h_spread floor ~700), where the design
  bars were never claimed.
  Contaminants (oil 28, water 54, crud 18):
    R-CT1  oil and water: T_c never above SP + 15 K (the safety line) and no D1
           latch. Runaway-supervisor latches are reported: a latch is the
           safe state, not a hazard
    R-CT2  parity as R-HS5
  Crud (a stuck post plus pan bow) is reported, not gated: it is a slow
  mechanical failure the sensor cannot observe (DECISIONS.md R-CT3).
Reported: HS_DEEP / HS_BACK / HS_GRAD (cases.report_cases).

Run: python hc_cosim.py [--lib path] [--out hc-cosim.json]   (~4 min on 10 cores)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_compare as EC  # noqa: E402  (reference_platform on the evidence written)
sys.path.insert(0, str(HERE.parent / "firmware"))
import cases as cs  # noqa: E402
import cosim  # noqa: E402
import pyloop as pl  # noqa: E402

GAINS = ("true", "id_measured", "id_estimated")
LATCH_OK = {("disc_pot_water_1l5", "5811->300@250")}
OFF = {"csw": 0, "lpg": 0}


def job(args):
    path, version, gain, c = args
    cosim.LIB_PATH = path
    np.seterr(all="ignore")
    case = {k: v for k, v in c.items() if k not in ("h_spec", "truth")}
    case.update(gain=gain, params=dict(OFF) if version == "before" else {}, return_log=True, kind=c["kind"])
    tf = cs.make_truth(c.get("truth"))
    hp = pl.h_profile(c.get("h_spec")) if c.get("h_spec") is not None else None
    row, L = cosim.run_case(case, truth_factory=tf, h_profile=hp)
    m = pl.metrics(L, c.get("loss_at"), c.get("ev_at"), c.get("settle", 20.0))
    sp, Tc, Tm = L[:, 1], L[:, 3], L[:, 4]
    lim = cs.b3_limit(c["pan"])
    hold = max(abs(x) for x in m["hold_err_c_K"])
    r = {"version": version, "gain": gain, "kind": c["kind"], "group": c.get("group"), "pan": c["pan"],
         "h": c["h"], "label": c.get("label"), "h_spec": str(c.get("h_spec")), "truth": str(c.get("truth")),
         "seed": c["seed"],
         "est_err_K": m["est_err_c_max_K"], "est_err_in_transient_K": m.get("est_err_in_transient_K"),
         "overshoot_K": m["overshoot_K"], "hold_err_c_K": m["hold_err_c_K"],
         "Tc_max_over_sp_K": round(float((Tc - sp).max()), 2), "Tmean_max_over_sp_K": round(float((Tm - sp).max()), 2),
         "B1": m["est_err_c_max_K"] <= 3.0, "B2": m["overshoot_K"] <= 5.0, "B3": hold <= lim,
         "est_err_le_5": m["est_err_c_max_K"] <= 5.0, "hold_le_5": hold <= 5.0,
         "false_latch": row["detected_at"] is not None, "probes": row["probes"],
         "sup_latch": row["sup_latch"], "r1_trip": row["r1_trip"],
         "shadow_rms_K": row["shadow_rms_K"], "shadow_max_K": row["shadow_max_K"],
         "cs_events": row["cs_events"], "h_model_end": row["h_model_end"], "lpg_s": row["lpg_s"]}
    r["SAFE"] = r["Tc_max_over_sp_K"] <= 15.0
    return r


def summary(rows):
    out = {}
    for v in ("after", "before"):
        for g in GAINS:
            R = [r for r in rows if r["version"] == v and r["gain"] == g]
            if not R:
                continue
            d = {}
            for key in ("hs", "hs_deep", "hs_back", "hs_grad", "oil", "water", "crud"):
                G = [r for r in R if r["kind"] == key or r["group"] == key]
                if not G:
                    continue
                d[key] = {"cases": len(G), **{b: sum(r[b] for r in G) for b in
                                              ("B1", "B2", "B3", "est_err_le_5", "hold_le_5", "SAFE")},
                          "worst_overshoot_K": max(r["overshoot_K"] for r in G),
                          "worst_est_err_K": max(r["est_err_K"] for r in G),
                          "worst_hold_K": max(max(abs(x) for x in r["hold_err_c_K"]) for r in G),
                          "worst_Tc_over_sp_K": max(r["Tc_max_over_sp_K"] for r in G),
                          "worst_Tmean_over_sp_K": max(r["Tmean_max_over_sp_K"] for r in G),
                          "false_latches": sum(r["false_latch"] for r in G),
                          "sup_latches": sum(r["sup_latch"] is not None for r in G),
                          "r1_trips": sum(r["r1_trip"] is not None for r in G),
                          "probes": sum(r["probes"] for r in G),
                          "windows_accepted": sum(sum(e[1] == "accept" for e in r["cs_events"]) for r in G),
                          "escalations": sum(sum(e[1] == "escalate" for e in r["cs_events"]) for r in G),
                          "worst_shadow_rms_K": max(r["shadow_rms_K"] for r in G)}
            out[f"{v}/{g}"] = d
    return out


def bars(summ, rows):
    b = {}
    for g in GAINS:
        d = summ[f"after/{g}"]
        hs, oil, wat = d["hs"], d["oil"], d["water"]
        n = hs["cases"]
        H = [r for r in rows if r["version"] == "after" and r["gain"] == g and r["kind"] == "hs"]
        b[g] = {
            "R-HS1_overshoot_le_5K_all": hs["B2"] == n,
            "R-HS2_est_err_le_5K_outside_20s_all": hs["est_err_le_5"] == n,
            "R-HS3_hold_err_le_5K_unlatched": all(r["hold_le_5"] for r in H if not r["false_latch"]),
            "R-HS4_no_supervisor_trip_no_unknown_latch": hs["sup_latches"] == 0 and hs["r1_trips"] == 0
            and all((r["pan"], r["label"]) in LATCH_OK for r in H if r["false_latch"]),
            "R-CT1_oil_water_safe_no_latch": oil["SAFE"] == oil["cases"] and wat["SAFE"] == wat["cases"]
            and oil["false_latches"] == 0 and wat["false_latches"] == 0,
            "R-HS5_R-CT2_parity_rms_le_0p05K": max(x["worst_shadow_rms_K"] for x in d.values()) <= 0.05,
        }
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=cosim.LIB_PATH)
    ap.add_argument("--out", default=str(HERE / "hc-cosim.json"))
    ap.add_argument("--after-only", action="store_true", help="skip the 'before' baseline (gates only)")
    args = ap.parse_args()
    C = cs.hs_cases() + cs.report_cases() + cs.contaminant_cases()
    versions = ("after",) if args.after_only else ("after", "before")
    jobs = [(args.lib, v, g, c) for v in versions for g in GAINS for c in C]
    with Pool(min(10, os.cpu_count() or 1)) as pool:
        rows = pool.map(job, jobs, chunksize=2)
    summ = summary(rows)
    b = bars(summ, rows)
    ok = all(all(x.values()) for x in b.values())
    out = {"scope": __doc__.strip(), "summary": summ, "bars": b, "all_bars_pass": ok, "rows": rows}
    if args.after_only and Path(args.out).exists():
        # keep the committed baseline rows; replace the 'after' ones
        old = json.loads(Path(args.out).read_text())
        before = [r for r in old.get("rows", []) if r["version"] == "before"]
        out["rows"] = rows + before
        out["summary"] = summary(out["rows"])
    Path(args.out).write_text(json.dumps(EC.stamp(out), indent=1, default=float) + "\n")
    for k, d in out["summary"].items():
        print("==", k)
        for g, x in d.items():
            print("   ", g, x)
    for g, x in b.items():
        print("BARS", g, x)
    for r in rows:
        hs_bad = r["kind"] == "hs" and not (r["B2"] and r["est_err_le_5"] and (r["hold_le_5"] or r["false_latch"])
                                            and (not r["false_latch"] or (r["pan"], r["label"]) in LATCH_OK))
        ct_bad = r["group"] in ("oil", "water") and not (r["SAFE"] and not r["false_latch"])
        if r["version"] == "after" and (hs_bad or ct_bad):
            print("FAIL", r["gain"], r["kind"], r["group"], r["pan"], r["label"], r["est_err_K"], r["overshoot_K"],
                  r["hold_err_c_K"], r["Tc_max_over_sp_K"], r["false_latch"], r["cs_events"][:4])
    print("ALL HC BARS PASS" if ok else "HC BAR FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
