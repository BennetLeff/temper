#!/usr/bin/env python3
"""Provisional leg B native-19 decision matrix (round 17, pending leg B's own corrections).

    legB-h0-prov-n19 = legB coarse (h 1 mm, 1.0 mm edges, 10 mm crop, native-19)
                     + [legA best (native-19) - legA coarse (same reference, native-19)]

i.e. leg A's per-entry closure-height, crop and mesh corrections are transferred
to leg B. Both legs' closure files give every port the same semantic orientation
(bus_p -> hv_ret for the capacitor ports, driver output -> its return for the
gate ports), so entries correspond one to one. This is an assumption, not a
measurement: leg B's own corrections (remote `b19corr`, then fine extraction
`campB19`) replace it, and comparing the two tests the transfer.

    python3 compose_legB_prov.py  ->  legB-h0-prov-n19.matrix.txt
"""
import hashlib
import json
from pathlib import Path

import numpy as np

import run_d2

HERE = Path(__file__).resolve().parent
M = HERE.parent / "results" / "matrices"
SRC = {"legB_coarse": M / "legB-h1-e1p0-m10-n19.matrix.txt",
       "legA_best": HERE / "legA-h0-best-n19.matrix.txt",
       "legA_coarse": M / "legA-h1-e1p0-m10-n19.matrix.txt"}
L = {k: np.array(run_d2.read_L(str(p))) for k, p in SRC.items()}
corr = L["legA_best"] - L["legA_coarse"]
out = L["legB_coarse"] + corr
out = (out + out.T) / 2
eig = float(np.linalg.eigvalsh(out).min())
assert eig > 0, eig
names = ["P1_C40", "P2_C41", "P3_gate_high", "P4_gate_low"]
res = {"names": names, "L0_nH": np.round(out, 4).tolist(), "legA_correction_nH": np.round(corr, 4).tolist(),
       "min_eigenvalue_nH": eig, "status": "PROVISIONAL (leg-A correction transfer)",
       "sources": {k: {"path": str(p.relative_to(HERE.parent)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                   for k, p in SRC.items()}}
(HERE / "legB-h0-prov-n19.matrix.txt").write_text("RESULT " + json.dumps(res) + "\n")
for r in out:
    print([round(v, 3) for v in r])
print("min eig", round(eig, 3))
