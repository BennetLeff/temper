#!/usr/bin/env python3
"""Fill the JLCPCB BOM's LCSC column from sourcing/lcsc-map.csv (2026-10-08 LCSC survey).

    python3 apply_lcsc.py  ->  fab/bom-jlcpcb.csv (LCSC Part # and Assembly columns)

Rules: EXACT matches are used as found. Design changes made after the survey (DECISIONS.md
2026-10-08: R83/R101/R116 -> RT0603BRD077K68L, R51/R52/R55/R56 -> RL1206FR-070R68L) map to the
C-numbers checked on lcsc.com. The snubber caps' alternate (Yageo CC1206JKNPOCBN102: 1206, 1 nF,
5 %, 1 kV, C0G, same as Murata GRM31A5C3A102JW01D) is accepted as a JLC substitution. R34's
alternate has no stock, so R34 is consigned. NOT_FOUND lines are consigned or hand-assembled.

Stage 8 (review 2026-10-08): rows match the survey by MPN, not by designator group, because new
parts join existing groups (C10 / C17 joined the 100 nF line). The HS bulk GRM21BZ71E106KE15L
(C11 / C18) is new since the survey. J3 is now B2P3-VH(LF)(SN), which has no LCSC match, so it
falls to hand assembly; the survey's C160315 is the old 3.96 mm B2P-VH and must not be used. The F1
fuse clips (2 x Littelfuse 01220088Z) are part of F1's footprint, not source components, so they
get their own hand-assembly line (review M8).
"""
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MAP = {r["MPN"]: r for r in csv.DictReader(open(HERE / "sourcing" / "lcsc-map.csv"))}
CHANGED = {"RT0603BRD077K68L": "C375517", "RL1206FR-070R68L": "C728510",    # verified on lcsc.com 2026-10-08
           "GRM21BZ71E106KE15L": "C237493",                                  # stage 8; lcsc.com 2026-10-08, 930 in stock
           "CC0805KRX7R9BB104": "C49678",                                    # stage 9; lcsc.com 2026-10-08, 8.36 M in stock
           "GRM21BR71H105KA12L": "C77083"}                                   # stage 9; lcsc.com 2026-10-08, 119 k in stock
# BOM simplification 2026-10-09 (../bom-simplification/PROPOSAL.md, safe set): JLC Basic parts of identical
# spec, plus the stocked 0.1 % replacements for R34/R35, R77/R95/R110 and R87/R105/R120. C-numbers, class
# and stock were read from JLC's part listings on 2026-10-09 (bom-simplification/totals.py re-checks them).
BASIC = {"CC0603KRX7R9BB104": "C14663", "CL10C101JB8NNNC": "C14858", "CL21B105KBFNNNE": "C28323",
         "1206B475K500NT": "C29823", "CL05B104KB54PNC": "C307331", "0603WAF1002T5E": "C25804",
         "0603WAF1000T5E": "C22775", "0603WAF1003T5E": "C25803", "0603WAF3300T5E": "C23138",
         "0603WAF1001T5E": "C21190", "0603WAF5601T5E": "C23189", "0603WAF3302T5E": "C4216",
         "0603WAF0000T5E": "C21189", "1206W4F1001T5E": "C4410", "1206W4F100KT5E": "C17928",
         "1N4148W": "C81598", "MMBT3904": "C20526", "0603WAF4991T5E": "C23046", "0603WAF1802T5E": "C25810",
         "0603WAF3002T5E": "C22984", "1206W4F1003T5E": "C17900",
         # stage 14 (bias modules): 330 pF C0G and the 27 k enable-divider leg, JLC Basic (read 2026-10-09)
         "CL10C331JB8NNNC": "C1664", "0603WAF2702T5E": "C22967"}
CHANGED.update({"UMK325AB7106KM-T": "C386167", "RT0603BRD0712K4L": "C861102", "TNPW060311K7BEEA": "C4553285",
                "RT0603BRD076K2L": "C136960", "ARG03BTC1333": "C1509631",
                # stage 14: module feedback divider, 0.1 % 25 ppm (JLC Extended, read 2026-10-09)
                "RT0603BRD0763K4L": "C326723", "RT0603BRD0711KL": "C728581"})
ACCEPT_ALT = {"GRM31A5C3A102JW01D"}
bom_path = HERE / "fab" / "bom-jlcpcb.csv"
rows = list(csv.DictReader(open(bom_path)))
counts = {"exact": 0, "changed": 0, "substitute": 0, "consign": 0}
for r in rows:
    mpn = r["Manufacturer Part Number"]
    m = MAP.get(mpn)
    if mpn in BASIC:
        r["LCSC Part #"], r["Assembly"] = BASIC[mpn], "JLC (Basic)"
        counts["changed"] += 1
    elif mpn in CHANGED:
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
clip = dict.fromkeys(rows[0], "")
clip.update({"Comment": "Fuse clip 10x38 mm (midget / Class CC), 30 A (2 per F1)", "Designator": "F1-CLIP",
             "Manufacturer Part Number": "01250003H", "LCSC Part #": "C223911", "Mount": "THT", "Assembly": "hand-solder, 2 per board (not a source component)"})
rows = [r for r in rows if r["Designator"] != "F1-CLIP"] + [clip]
with open(bom_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(counts)
