#!/usr/bin/env python3
"""Native-21 stage 9: gate-loop bound matrices for the VDD-VSS cap stacks (review B1).

Stage 9 necks each UCC21550 output from 0.6 / 0.5 mm to 0.3 mm over its last ~7.5 mm (under the
0805 cap stack at the driver pins). Every other conductor of the extracted gate loops is the
extracted copper: the sw_a link and the VSSA -> reservoir path measure the same as stage 7.

The neck's partial self-inductance rise, thin-strip estimate 0.2*l*(ln(2l/(w+t)) + 0.5) nH, is
about 0.9 nH (5.4 -> 6.3 nH at l = 7.5 mm, t = 0.07 mm). This writes each leg's provisional
decision matrix with +2 nH on both gate-port diagonals (P3 high, P4 low): about twice the
estimate, with the mutual terms unchanged. Adding to a diagonal keeps the matrix SPD. F6 is
re-run on these to bound the change.

    python3 compose_stage9_bound.py  ->  legA21-h0-s9b2-n21.matrix.txt, legB21-h0-s9b2-n21.matrix.txt
"""
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DL = 2.0   # nH added to each gate-port self term

for leg, src in (("A", "legA21-h0-prov-n21.matrix.txt"), ("B", "legB21-h0-prov-n21.matrix.txt")):
    path = HERE / src
    text = path.read_text()
    res = json.loads(text[text.index("{"):])
    L = np.array(res["L0_nH"], dtype=float)
    for i, name in enumerate(res["names"]):
        if name.startswith(("P3", "P4")):
            L[i, i] += DL
    out = {"names": res["names"], "L0_nH": L.round(4).tolist(),
           "min_eigenvalue_nH": float(np.linalg.eigvalsh(L).min()),
           "status": f"STAGE-9 BOUND: provisional + {DL} nH on the gate-port diagonals (0.3 mm output necks)",
           "sources": {"provisional": {"path": f"d2/{src}", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}}
    dst = HERE / f"leg{leg}21-h0-s9b2-n21.matrix.txt"
    dst.write_text("RESULT " + json.dumps(out) + "\n")
    print(dst.name, "gate diagonals", [round(L[i, i], 3) for i in range(len(L)) if res["names"][i].startswith(("P3", "P4"))],
          "min eig", round(out["min_eigenvalue_nH"], 3))
