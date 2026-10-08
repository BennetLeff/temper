#!/usr/bin/env python3
"""Leg B corrected matrix from leg B's OWN coarse corrections; tests compose_legB_prov's transfer.

Per leg, on the coarse mesh (1.0 mm edges):
  C_h = cubic(0.5, 1, 2, 3 mm) at h = 0  -  L(h 1, m10)     (closure-height correction)
  C_m = L(h 1, m20)  -  L(h 1, m10)                        (crop correction)
The provisional leg B matrix used leg A's whole best-minus-coarse change, which
is C_h(A) + C_m(A) + the fine-minus-coarse mesh change. Replacing leg A's
closure and crop parts with leg B's own:

  legB-h0-corr-n19 = legB-h0-prov-n19 + [C_h(B) + C_m(B)] - [C_h(A) + C_m(A)]

so the only borrowed part left is leg A's mesh refinement (fine quad(1,2,3)
vs coarse), which the fine leg B campaign (campB19) replaces. Leg A's
coarse set is native-17 copper (corrections are closure/crop effects; the
native-19 change at h 1 mm moved entries by <= 1.8 %).

    compose_legB_corr.py [--selftest]  ->  legB-h0-corr-n19.matrix.txt, results/legB-corr-vs-prov.json
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

import run_d2

HERE = Path(__file__).resolve().parent
M = HERE.parent / "results" / "matrices"
SETS = {
    "A": {"h0.5": "legA-h0p5-e1p0-m10", "h1": "legA-h1-e1p0-m10", "h2": "legA-h2-e1p0-m10",
          "h3": "legA-h3-e1p0-m10", "m20": "legA-h1-e1p0-m20"},
    "B": {"h0.5": "legB-h0p5-e1p0-m10-n19", "h1": "legB-h1-e1p0-m10-n19", "h2": "legB-h2-e1p0-m10-n19",
          "h3": "legB-h3-e1p0-m10-n19", "m20": "legB-h1-e1p0-m20-n19"},
}


def load(name):
    p = M / f"{name}.matrix.txt"
    return np.array(run_d2.read_L(str(p))), p


def corrections(leg):
    L = {k: load(v)[0] for k, v in SETS[leg].items()}
    hs = np.array([0.5, 1, 2, 3])
    stack = np.stack([L["h0.5"], L["h1"], L["h2"], L["h3"]])
    cubic0 = np.zeros_like(L["h1"])
    for i in range(4):
        for j in range(4):
            cubic0[i, j] = np.polyval(np.polyfit(hs, stack[:, i, j], 3), 0.0)
    return cubic0 - L["h1"], L["m20"] - L["h1"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="use leg A for both legs; the change must be zero")
    a = ap.parse_args()
    ChA, CmA = corrections("A")
    ChB, CmB = (ChA, CmA) if a.selftest else corrections("B")
    delta = (ChB + CmB) - (ChA + CmA)
    if a.selftest:
        assert np.allclose(delta, 0), delta
        print("selftest ok")
        return
    prov = np.array(run_d2.read_L(str(HERE / "legB-h0-prov-n19.matrix.txt")))
    out = (prov + delta + (prov + delta).T) / 2
    eig = float(np.linalg.eigvalsh(out).min())
    assert eig > 0, eig
    names = ["P1_C40", "P2_C41", "P3_gate_high", "P4_gate_low"]
    srcs = {f"{leg}:{k}": v for leg in "AB" for k, v in SETS[leg].items()}
    res = {"names": names, "L0_nH": np.round(out, 4).tolist(), "delta_vs_prov_nH": np.round(delta, 4).tolist(),
           "closure_corr_nH": {"A": np.round(ChA, 4).tolist(), "B": np.round(ChB, 4).tolist()},
           "crop_corr_nH": {"A": np.round(CmA, 4).tolist(), "B": np.round(CmB, 4).tolist()},
           "min_eigenvalue_nH": eig, "status": "leg B's own closure + crop corrections; mesh refinement still from leg A",
           "sources": {k: hashlib.sha256((M / f"{v}.matrix.txt").read_bytes()).hexdigest() for k, v in srcs.items()}}
    (HERE / "legB-h0-corr-n19.matrix.txt").write_text("RESULT " + json.dumps(res) + "\n")
    rel = delta / prov * 100
    summ = {"max_abs_delta_nH": float(abs(delta).max()), "delta_pct": np.round(rel, 2).tolist(), "min_eig_nH": eig}
    (HERE / "results" / "legB-corr-vs-prov.json").write_text(json.dumps(summ, indent=1) + "\n")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
