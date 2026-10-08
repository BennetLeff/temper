#!/usr/bin/env python3
"""Provisional leg B native-21 decision matrix (round 17, pending native-21's own corrections).

    legB21-h0-prov-n21 = legB21 coarse (h 1 mm, 1.0 mm edges, 10 mm crop, native-21)
                       + [legB best (native-19) - legB coarse (same reference, native-19)]

Leg B's own native-19 per-entry closure-height, crop and mesh corrections are carried to the
native-21 copper, as compose_legA21_prov.py does for leg A. Caveat specific to native-21:
its gate ports close through the driver's bias capacitor (closures-legB-n21.json),
not native-19's gate-return closure, so the gate-entry corrections are a rougher
transfer than the power-loop ones. Native-21's own corrections (remote `b21corr`,
then `campB21`) replace this.

    python3 compose_legB21_prov.py  ->  legB21-h0-prov-n21.matrix.txt
"""
import hashlib
import json
from pathlib import Path

import numpy as np

import run_d2

HERE = Path(__file__).resolve().parent
M = HERE.parent / "results" / "matrices"
SRC = {"legB21_coarse": M / "legB21-h1-e1p0-m10-n21.matrix.txt",
       "legB_best": HERE / "legB-h0-best-n19.matrix.txt",
       "legB_coarse": M / "legB-h1-e1p0-m10-n19.matrix.txt"}
L = {k: np.array(run_d2.read_L(str(p))) for k, p in SRC.items()}
corr = L["legB_best"] - L["legB_coarse"]
out = L["legB21_coarse"] + corr
out = (out + out.T) / 2
eig = float(np.linalg.eigvalsh(out).min())
assert eig > 0, eig
names = ["P1_C40", "P2_C41", "P3_gate_high", "P4_gate_low"]
res = {"names": names, "L0_nH": np.round(out, 4).tolist(), "legB_correction_nH": np.round(corr, 4).tolist(),
       "min_eigenvalue_nH": eig, "status": "PROVISIONAL (native-19 leg-B correction transfer)",
       "sources": {k: {"path": str(p.relative_to(HERE.parent)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                   for k, p in SRC.items()}}
(HERE / "legB21-h0-prov-n21.matrix.txt").write_text("RESULT " + json.dumps(res) + "\n")
print(json.dumps({"L0_nH": res["L0_nH"], "min_eig": eig}))
