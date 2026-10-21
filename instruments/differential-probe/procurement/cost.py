#!/usr/bin/env python3
"""Two-board component cost for Rev C and Rev B from prices-2026-10-20.csv.

Run from the probe directory: python3 procurement/cost.py
Unit prices are the tier covering the two-board quantity; LCSC minimums are applied.
Rev B is read from git at ca79d882f plus its five off-board parts.
"""
import collections, csv, io, subprocess

REVB = "ca79d882f:instruments/differential-probe/procurement/bom-jlc.csv"
REVB_OFFBOARD = {"235": 2, "31-221-RFX": 1, "7201SYZBE": 1, "7201SYZQE": 1}
REVB_BREAKS = {"RNCF0603TKY499R": 1.414}  # 22 pcs reaches the 10+ tier

prices = {r["mpn"]: r for r in csv.DictReader(open("procurement/prices-2026-10-20.csv"))}

def counts(text, extra=None):
    c = collections.Counter(r["MPN"] for r in csv.DictReader(io.StringIO(text)))
    c.update(extra or {})
    return c

def cost(bom, overrides):
    total = 0.0
    for mpn, qty in bom.items():
        p = prices[mpn]
        unit = overrides.get(mpn, float(p["unit_usd"]))
        total += max(2 * qty, int(p["moq"])) * unit
    return total

revc = counts(open("procurement/bom-jlc.csv").read())
revb = counts(subprocess.run(["git", "show", REVB], check=True, capture_output=True, text=True).stdout, REVB_OFFBOARD)
for name, bom, ov in (("Rev C", revc, {}), ("Rev B", revb, REVB_BREAKS)):
    t = cost(bom, ov)
    print(f"{name}: {sum(bom.values())} parts/board, {len(bom)} MPNs, 2 boards ${t:.2f} (${t / 2:.2f}/board)")
