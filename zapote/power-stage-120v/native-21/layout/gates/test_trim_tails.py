#!/usr/bin/env python3
"""Controls for trim_tails.follow_on (stage 27).

    python3 native-21/layout/gates/test_trim_tails.py

1. Negative: on the committed copper.json (KiCad reports no dangling copper on its build), walking EVERY net trims nothing.
2. Positive: a synthetic dead branch (F.Cu segment -> via -> two In2 segments) hung off a real leg_b-permit_gate vertex
   goes in one run, and the copper is back to the committed one exactly.
"""
import copy
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("trim_tails", HERE / "trim_tails.py")
tt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tt)

cu = json.loads((HERE.parent / "copper.json").read_text())
fails = 0

done = []
neg = copy.deepcopy(cu)
tt.follow_on(neg, {t["net"] for t in neg["tracks"]} | {v["net"] for v in neg["vias"]}, done)
ok = not done and neg == cu
print("ok  " if ok else "FAIL", "negative: every net of the committed copper, nothing trimmed", done[:5])
fails += not ok

pg = next(t for t in cu["tracks"] if t["net"] == "leg_b-permit_gate" and t["layer"] == "F.Cu")
a = list(next(p for p in pg["points"] if not isinstance(p, str)))
b, c, d = [a[0] + 2.0, a[1]], [a[0] + 2.0, a[1] + 3.0], [a[0] + 3.5, a[1] + 3.0]
pos = copy.deepcopy(cu)
pos["tracks"] += [{"net": "leg_b-permit_gate", "layer": "F.Cu", "width": 0.2, "points": [a, b]},
                  {"net": "leg_b-permit_gate", "layer": "In2.Cu", "width": 0.2, "points": [b, c, d]}]
pos["vias"].append({"net": "leg_b-permit_gate", "at": b, "size": 0.6, "drill": 0.3})
done = []
tt.follow_on(pos, {"leg_b-permit_gate"}, done)
ok = pos == cu and len(done) == 4
print("ok  " if ok else "FAIL", "positive: synthetic 3-segment branch + via removed in one run", done)
fails += not ok

print(f"{fails} failure(s)")
raise SystemExit(1 if fails else 0)
