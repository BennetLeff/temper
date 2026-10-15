#!/usr/bin/env python3
"""Compact console view of results*/summary.json and targets.json (no new numbers; for reading)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS  # noqa: E402

d = json.loads((RESULTS / "summary.json").read_text())
cols = ["lam_block", "lam_fet_row", "R5_el", "R5_term", "U26", "U42", "C38", "C40", "gateR_el", "gateR_der", "min_gated", "lead_sink_w"]
print("cols:", " ".join(cols))
for label, t in d["tables"].items():
    for c in ("c22_h10", "c28_h10"):
        v = t[c]
        print(f"{label[:64]:64s} {c[:3]}", " ".join("    -" if v[k] is None else f"{v[k]:+5.1f}" for k in cols))
tg = json.loads((RESULTS / "targets.json").read_text())
print("ceilings", tg["ceilings"])
for k, v in tg["fix_targets"].items():
    print(k, {x: v[x] for x in v if x.startswith("f_")})
