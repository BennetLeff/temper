#!/usr/bin/env python3
"""L1 current / temperature rating of the B82726S22*3A020 parts against the ledger basis, using the ledger's own
digitised series derating curve (datasheet p.5 IND0372-K-E applies to the whole B82726S22*3A020 sheet;
native-21/verification/datasheet-ledger/scripts/datasheet_gap_calcs.py L1_DERATE).
Stresses: 15 A owner inlet cap (the ledger check) and 13.5 A firmware inlet bound (B3 body rows); local air 50 C
(design inlet) and 61 C (release bay, taken as L1's local air). Usage: python3 -I l1_rating.py OUT.json"""
import json
import sys

DERATE = [(60, 1.00), (65, 0.964), (67, 0.945), (70, 0.916), (75, 0.865), (78, 0.834), (80, 0.809),
          (85, 0.754), (90, 0.690), (100, 0.543), (110, 0.365), (120, 0.160), (125.6, 0.0)]
PARTS = {"B82726S2203A020": dict(IR=20.0, R=4.5e-3), "B82726S2243A020": dict(IR=24.0, R=3.2e-3)}


def k(ta):
    if ta <= 60:
        return 1.0
    for (t0, k0), (t1, k1) in zip(DERATE, DERATE[1:]):
        if t0 <= ta <= t1:
            return k0 + (k1 - k0) * (ta - t0) / (t1 - t0)
    return 0.0


def max_ta(ratio_needed):
    t = 60.0
    while t < 125.6 and k(t) >= ratio_needed:
        t += 0.01
    return round(t - 0.01, 1)


out = {}
for mpn, p in PARTS.items():
    r = {}
    for i in (15.0, 13.5):
        for ta in (50, 61):
            r[f"{i}A_at_{ta}C_ratio"] = round(i / (p["IR"] * k(ta)), 4)
        r[f"{i}A_80pct_holds_to_local_air_C"] = max_ta(i / (0.8 * p["IR"]))
        r[f"{i}A_IR_holds_to_local_air_C"] = max_ta(i / p["IR"])
        r[f"{i}A_copper_loss_W"] = round(2 * i * i * p["R"], 3)
    out[mpn] = r
json.dump(out, open(sys.argv[1], "w"), indent=1)
for m, r in out.items():
    print(m, r)
