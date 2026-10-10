#!/usr/bin/env python3
"""Snapshot the round-5 FEM coupling ratios this round uses (mu 100, f_k / f_r against the round-4 basis
coil) into outputs/coupling-factors.json, with the SHA-256 of the source file. Round 5's addendum appends
'd228_gap84' to its coupling.json; freezing the factors here keeps round 6 reproducible if that file moves.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT.parent / "round5-coil-od210" / "outputs" / "coupling.json"
raw = SRC.read_bytes()
d = json.loads(raw)
fac = {}
for r in d["rows"]:
    if r["geom"] in ("d228_gap84", "d228_2sec", "d240_cont") and r["mu_pan"] == 100.0 and r["pan_d_mm"] in (180, 220, 260):
        fac.setdefault(r["geom"], {})[str(r["pan_d_mm"])] = {"f_k": r["f_k"], "f_r": r["f_r"], "kl_mu100": r["kl"]}
out = {"status": "ASSUMED: linear-mu axisymmetric FEM ratios (round 5); mu 100 central",
       "source": str(SRC.relative_to(ROOT.parent)), "source_sha256": hashlib.sha256(raw).hexdigest(),
       "factors": fac}
(ROOT / "outputs" / "coupling-factors.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(fac, indent=1))
