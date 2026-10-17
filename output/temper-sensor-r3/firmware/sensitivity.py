"""Sensitivity of the C1 loop to the plant gain a, C code in the loop.

Evidence for DECISIONS.md D-ID (why the identifier is the effective heat-up
gain with no loss term, and how much error in a the controller tolerates):

  a_scale   gain fixed (identification off) at a_true x {0.5, 0.7, 1.4, 2.0}
  k_loss    identification on (measured power) with the loss regressor
            dT = a (dE - k_loss dS) at k_loss {1, 2} W/K, against the default 0

on the 16 C1 design cases (screen.py's seeds). Reported, not gated.
Run: python sensitivity.py [--lib path] [--out sensitivity.json]   (about 1 min)
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

A_SCALES = (0.5, 0.7, 1.4, 2.0)
K_LOSS = (1.0, 2.0)


def jobs():
    out = []
    for s in A_SCALES:
        for c in cosim.cases(gains=("true",), kinds=("design",)):
            out.append({**c, "a_scale": s, "variant": f"a_scale {s}"})
    for k in K_LOSS:
        for c in cosim.cases(gains=("id_measured",), params={"pg_k_loss": k}, kinds=("design",)):
            out.append({**c, "variant": f"k_loss {k} W/K"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=cosim.LIB_PATH)
    ap.add_argument("--out", default=str(HERE / "sensitivity.json"))
    args = ap.parse_args()
    cosim.LIB_PATH = args.lib
    with Pool(min(10, os.cpu_count() or 1), initializer=cosim._init, initargs=(args.lib,)) as pool:
        rows = pool.map(cosim.run_case, jobs())
    summ = {}
    for v in dict.fromkeys(r["variant"] for r in rows):
        G = [r for r in rows if r["variant"] == v]
        d = {"cases": len(G), "B1_pass": sum(r["B1"] for r in G), "B2_pass": sum(r["B2"] for r in G),
             "B3_pass": sum(r["B3"] for r in G), "worst_overshoot_K": max(r["overshoot_K"] for r in G),
             "slowest_reach_sp1_minus2K_s": max(r["t_reach_sp1_minus2K_s"] or 1e9 for r in G)}
        if v.startswith("k_loss"):
            rat = [r["a_ratio_end_ramp1"] for r in G]
            d["a_ratio_end_ramp1"] = [min(rat), max(rat)]
        summ[v] = d
    Path(args.out).write_text(json.dumps(EC.stamp({"scope": __doc__.strip(), "summary": summ}), indent=1) + "\n")
    for v, d in summ.items():
        print(v, d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
