#!/usr/bin/env python3
"""Rows near R5 / the FET row from b3_ratings_gate margins files, one row per file (c22 / c28, bay 55 C).
    python3 -I variants_table.py results/margins/*.json > results/variants.json
The files are basis_variant.py runs on the s40 base (s40.json is the s40 chain's own margins)."""
import json
import sys
from pathlib import Path

PICK = {"laminate: 1 mm-block copper peak": "lam_block", "laminate: FET-row copper": "lam_fet_row"}


def short(item):
    if item in PICK:
        return PICK[item]
    head = item.split(":")[0]
    if head in ("C38", "C39", "C40", "C41"):
        return head
    if head == "R5":
        return "R5 term" if "terminal" in item else "R5 el"
    if head == "R12":
        return "R12 der" if "derating" in item else "R12 el"
    return None


out = {}
for f in sys.argv[1:]:
    d = json.load(open(f))
    row = {}
    for c in ("c22_h10", "c28_h10"):
        lam, rated = [], []
        for r in d["cases"][c]:
            k = short(r["item"])
            if k:
                row[f"{c[:3]} {k}"] = r["margin_k"]
            if r["gated"]:
                (lam if r["item"].startswith("laminate") else rated).append(r["margin_k"])
        row[f"{c[:3]} laminate min"] = min(lam)
        row[f"{c[:3]} rated min"] = min(rated)
    out[Path(f).stem] = row
print(json.dumps(out, indent=1))
