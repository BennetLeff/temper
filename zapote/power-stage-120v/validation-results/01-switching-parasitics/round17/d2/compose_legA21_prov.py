#!/usr/bin/env python3
"""Provisional leg A native-21 decision matrix (round 17, pending native-21's own corrections).

    legA21-h0-prov-n21 = legA21 coarse (h 1 mm, 1.0 mm edges, 10 mm crop, native-21)
                       + [legA best (native-19) - legA coarse (same reference, native-19)]

Native-19's per-entry closure-height, crop and mesh corrections are carried to the
native-21 copper, as compose_legB_prov.py did for leg B (that transfer held: no
verdict flips once leg B's own corrections landed). Caveat specific to native-21:
its gate ports close through the driver's bias capacitor (closures-legA-n21.json),
not native-19's gate-return closure, so the gate-entry corrections are a rougher
transfer than the power-loop ones. Native-21's own corrections (remote `a21corr`,
then `campA21`) replace this.

    python3 compose_legA21_prov.py  ->  legA21-h0-prov-n21.matrix.txt
"""
import hashlib
import json
from pathlib import Path

import numpy as np

import run_d2

HERE = Path(__file__).resolve().parent
M = HERE.parent / "results" / "matrices"
SRC = {"legA21_coarse": M / "legA21-h1-e1p0-m10-n21.matrix.txt",
       "legA_best": HERE / "legA-h0-best-n19.matrix.txt",
       "legA_coarse": M / "legA-h1-e1p0-m10-n19.matrix.txt"}
L = {k: np.array(run_d2.read_L(str(p))) for k, p in SRC.items()}
corr = L["legA_best"] - L["legA_coarse"]
out = L["legA21_coarse"] + corr
out = (out + out.T) / 2
eig = float(np.linalg.eigvalsh(out).min())
assert eig > 0, eig
names = ["P1_C38", "P2_C39", "P3_gate_high", "P4_gate_low"]
res = {"names": names, "L0_nH": np.round(out, 4).tolist(), "legA_correction_nH": np.round(corr, 4).tolist(),
       "min_eigenvalue_nH": eig, "status": "PROVISIONAL (native-19 leg-A correction transfer)",
       "sources": {k: {"path": str(p.relative_to(HERE.parent)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                   for k, p in SRC.items()}}
(HERE / "legA21-h0-prov-n21.matrix.txt").write_text("RESULT " + json.dumps(res) + "\n")
print(json.dumps({"L0_nH": res["L0_nH"], "min_eig": eig}))
