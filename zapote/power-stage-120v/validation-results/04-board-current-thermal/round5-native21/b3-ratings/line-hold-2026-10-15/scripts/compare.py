#!/usr/bin/env python3
"""Row-by-row delta between the committed margins.json (I_line 11.1 A) and a line_hold.py result.

    python3 compare.py ../margins-line13p5.json      # prints a markdown table, worst delta first
"""
import json
import sys
from pathlib import Path

B3R = Path(__file__).resolve().parents[2]
base = json.loads((B3R / "margins.json").read_text())
var = json.loads(Path(sys.argv[1]).read_text())
rows = []
for case, items in base["cases"].items():
    v = {r["item"]: r for r in var["cases"][case]}
    for r in items:
        if r["item"] in v:
            rows.append((case, r["item"], r["gated"], r["margin_k"], v[r["item"]]["margin_k"]))
rows.sort(key=lambda t: t[4] - t[3])
print("| case | row | gated | margin 11.1 A | margin variant | delta K |\n|---|---|---|---|---|---|")
for case, item, g, a, b in rows:
    print(f"| {case} | {item} | {'yes' if g else 'adv'} | {a:+.1f} | {b:+.1f} | {b - a:+.1f} |")
