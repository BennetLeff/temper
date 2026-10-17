"""Seed-to-seed robustness of detector D1 with the C code in the loop.

screen.py and cosim.py run each D1 case on one noise seed. This repeats the
loss, food, nominal and probe-on-intact-contact cases over N_SEEDS seeds
(identified gain, measured power) for three D1 rule sets:

  screen_d1        screen.py's rules exactly (firmware additions off)
  firmware         the firmware defaults: D-D1a (a probe from NORMAL needs
                   >= 1 K of fitted free decay to conclude LOST), D-D1b (a
                   retry restores only on departure from the free decay),
                   D-D1c (the probe response must be >= 3 standard errors)
  stretch_3_6_3    firmware rules with a 3/6/3 s first probe at 60 % and a
                   1.5 s regressor lag (the B5 15 s stretch candidate)

Pass criteria (firmware rule set only; the others are evidence for the
decisions in DECISIONS.md D-D1a..c and D-B5) are the safety ones: every loss
detected, T_c <= SP + 15 K, no false restore, and no latch in any food,
nominal or probe-on-intact-contact run. The B5 timing clauses (suspect <= 3 s,
confirm <= 21 s) are gated in cosim.py on screen.py's seeds and only REPORTED
here across seeds (worst_suspect_s / worst_confirm_s).

Run: python b5_montecarlo.py [--lib path] [--seeds 20]   (about 2 min)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_compare as EC  # noqa: E402  (reference_platform on the evidence written)
import cosim  # noqa: E402

VARIANTS = {
    "screen_d1": dict(decay_min_change=0.0, retry_decay_only=0, probe_min_sigma=0.0),
    "firmware": {},
    "stretch_3_6_3": dict(probe_off=3.0, probe_on=6.0, probe_p=0.6, probe_lag=1.5),
}
KINDS = ("loss", "food", "nominal", "probe_intact")


def jobs(n_seeds):
    base = cosim.cases(gains=("id_measured",), kinds=KINDS)
    out = []
    for name, v in VARIANTS.items():
        for bi, b in enumerate(base):
            for s in range(n_seeds):
                c = dict(b)
                c["seed"] = 10_000 + 100 * bi + s
                c["params"] = dict(v)
                c["variant"] = name
                out.append(c)
    return out


def false_restore(r):
    """A retry (state LOST before it) that ended back in NORMAL on a loss run."""
    return r["kind"] == "loss" and any(x[-1] == 0 for x in r["probe_log"][1:])


def summarise(rows):
    out = {}
    for name in VARIANTS:
        R = [r for r in rows if r["variant"] == name]
        d = {}
        for pan in sorted({r["pan"] for r in R}):
            G = [r for r in R if r["pan"] == pan and r["kind"] == "loss"]
            d[f"loss/{pan}"] = {
                "runs": len(G),
                "detected": sum(r["detected_at"] is not None for r in G),
                "worst_confirm_s": max((r["B5_confirm_s"] if r["B5_confirm_s"] is not None else 1e9) for r in G),
                "worst_suspect_s": max((r["B5_suspect_s"] if r["B5_suspect_s"] is not None else 1e9) for r in G),
                "worst_Tc_over_sp_K": max(r["B5_Tc_over_sp_K"] for r in G),
                "runs_with_false_restore": sum(false_restore(r) for r in G),
            }
        for kind in ("food", "nominal", "probe_intact"):
            G = [r for r in R if r["kind"] == kind]
            d[kind] = {"runs": len(G), "probes": sum(r["probes"] for r in G),
                       "false_latches": sum(r["false_latch"] for r in G)}
        out[name] = d
    return out


def passes(d):
    loss = [v for k, v in d.items() if k.startswith("loss/")]
    return (all(v["detected"] == v["runs"] for v in loss)
            and all(v["worst_Tc_over_sp_K"] <= 15.0 for v in loss)
            and all(v["runs_with_false_restore"] == 0 for v in loss)
            and all(d[k]["false_latches"] == 0 for k in ("food", "nominal", "probe_intact")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=cosim.LIB_PATH)
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--out", default=str(HERE / "b5-montecarlo.json"))
    args = ap.parse_args()
    cosim.LIB_PATH = args.lib
    with Pool(min(10, os.cpu_count() or 1), initializer=cosim._init, initargs=(args.lib,)) as pool:
        rows = pool.map(cosim.run_case, jobs(args.seeds))
    summ = summarise(rows)
    verdict = {name: passes(d) for name, d in summ.items()}
    Path(args.out).write_text(json.dumps(EC.stamp({"scope": __doc__.strip(), "seeds": args.seeds, "variants": VARIANTS,
                                          "summary": summ, "passes": verdict}), indent=1, default=float) + "\n")
    for name, d in summ.items():
        print(f"== {name}: {'PASS' if verdict[name] else 'FAIL'}")
        for k, v in d.items():
            print("   ", k, v)
    return 0 if verdict["firmware"] else 1


if __name__ == "__main__":
    sys.exit(main())
