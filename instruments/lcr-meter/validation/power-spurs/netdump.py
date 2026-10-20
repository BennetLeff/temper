#!/usr/bin/env python3
"""Print every component's value and pin->net map from cad/design.json, and each
net's members. Used to read the power-tree topology the analysis relies on.
Usage: netdump.py [REF|NET ...]  (no args: list power-related parts)"""
import json, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
D = json.loads((ROOT / "cad/design.json").read_text())
parts = {p["ref"]: p for p in D["parts"]}
nets = {}
for p in D["parts"]:
    for pin, n in p["pins"].items():
        if n:
            nets.setdefault(n, []).append(f'{p["ref"]}.{pin}')
def show(x):
    if x in parts:
        p = parts[x]
        print(x, p["value"], p.get("kind"), {k: v for k, v in p["pins"].items() if v})
    elif x in nets:
        print(x, ":", " ".join(f"{m}({parts[m.split('.')[0]]['value']})" for m in nets[x]))
    else:
        print(x, "not found")
for a in sys.argv[1:]:
    show(a)
