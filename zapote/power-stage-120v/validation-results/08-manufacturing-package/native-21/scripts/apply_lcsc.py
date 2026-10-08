#!/usr/bin/env python3
"""Fill the JLCPCB BOM's LCSC column from sourcing/lcsc-map.csv (2026-10-08 LCSC survey).

    python3 apply_lcsc.py  ->  fab/bom-jlcpcb.csv (LCSC Part # and Assembly columns)

Rules: EXACT matches are used as found. Design changes made after the survey (DECISIONS.md
2026-10-08: R83/R101/R116 -> RT0603BRD077K68L, R51/R52/R55/R56 -> RL1206FR-070R68L) map to the
C-numbers checked on lcsc.com. The snubber caps' alternate (Yageo CC1206JKNPOCBN102: 1206, 1 nF,
5 %, 1 kV, C0G, same as Murata GRM31A5C3A102JW01D) is accepted as a JLC substitution. R34's
alternate has no stock, so R34 is consigned. NOT_FOUND lines are consigned or hand-assembled.
"""
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MAP = {r["Designator"]: r for r in csv.DictReader(open(HERE / "sourcing" / "lcsc-map.csv"))}
CHANGED = {"RT0603BRD077K68L": "C375517", "RL1206FR-070R68L": "C728510"}     # verified on lcsc.com 2026-10-08
ACCEPT_ALT = {"GRM31A5C3A102JW01D"}
bom_path = HERE / "fab" / "bom-jlcpcb.csv"
rows = list(csv.DictReader(open(bom_path)))
counts = {"exact": 0, "changed": 0, "substitute": 0, "consign": 0}
for r in rows:
    mpn = r["Manufacturer Part Number"]
    m = MAP.get(r["Designator"])
    if mpn in CHANGED:
        r["LCSC Part #"], r["Assembly"] = CHANGED[mpn], "JLC (Extended)"
        counts["changed"] += 1
    elif m and m["Match"] == "EXACT" and m["MPN"] == mpn:
        r["LCSC Part #"], r["Assembly"] = m["LCSC"], f"JLC ({m['JLC_class'] or 'class unknown'}); stock at survey: {m['Stock']}"
        counts["exact"] += 1
    elif m and m["Match"] == "ALTERNATE" and mpn in ACCEPT_ALT:
        r["LCSC Part #"], r["Assembly"] = m["LCSC"], f"JLC substitute {m['Alternate_MPN']} (equivalent: 1206 1 nF 5 % 1 kV C0G)"
        counts["substitute"] += 1
    else:
        r["LCSC Part #"], r["Assembly"] = "", "consign or hand-assemble (not on LCSC / no stock / no exact match)"
        counts["consign"] += 1
with open(bom_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(counts)
