#!/usr/bin/env python3
"""Cost/line arithmetic for the G02/G03 proposals from the repo's stock survey plus public JLC listing tiers.
Survey source: 08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13.csv (per-board $ at 500 boards).
JLC listing tiers: JLCPCB public part-list endpoint queried 2026-10-13 (selectSmtComponentList), LISTING prices,
not quotes; stock was 0 for every row marked so. They differ from the survey's Digi-Key-based prices by 2-5x,
so they are "re-quote" leads, not claimed savings.

    python3 -I cost_lines.py
"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pp_common import PS, RESULTS

CSV = PS / "validation-results/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13.csv"
rows = list(csv.reader(open(CSV)))
hdr = rows[0]
print("survey columns:", hdr[:22])
want = {"74650074": "J7-J10 link studs (+J2,J5)", "30KPA150CA": "D3,D17 TVS", "B32676G1905K000": "C5,C6 bulk", "IPW65R018CFD7": "Q2,Q3,Q5,Q6", "B32652A0104K000": "C38-C41"}
out = {}
for r in rows[1:]:
    for k, lab in want.items():
        if k in r:
            out[k] = r
for k, r in out.items():
    print(k, want[k], "|", ",".join(r[2:6]), "| qty", r[3], "| $/u@500 col:", r[16:21])

# --- proposal arithmetic (per board, 500-board volume; survey $/u at 500 for 74650074 = 2.73)
stud = 2.73
print("\nP-A/P-B: remove J7-J10 in the mains build: -4 x %.2f = -%.2f USD/board @500, -4 THT placements, 74650074 line stays (J2,J5)" % (stud, 4 * stud))
print("         bench build: BR1 DNP, J8+J10 only fitted: 2 studs")
listing = {  # JLC listing tiers 2026-10-13 (USD, stock 0 unless noted)
    "30KPA150CA-B (Brightking, LCSC C522439)": {"@1": 6.0559, "@104": 5.8797, "stock": 0},
    "30KPA150CA (JLC listing, Good-Ark class)": {"@1": 5.2192, "@500": 2.0143, "@800": 1.9801, "stock": 0},
    "B32676G1905K000 (LCSC C3802167)": {"@1": 3.2816, "@500": 1.2265, "@1000": 1.2037, "stock": 0},
    "74650074 THR terminal (JLC listing)": {"@1": 1.2494, "@100": 1.1776, "stock": 0},
    "IPW65R018CFD7 (C3289047)": {"@1": 21.5746, "@100": 17.5363, "stock": 6},
}
print(json.dumps(listing, indent=1))
print("\nSurvey vs listing at 500 boards (per board): D3+D17 survey 19.64 vs listing 2 x 1.98 = 3.96 ; C5+C6 survey 12.34 vs listing 2 x 1.23 = 2.45 ;")
print("  J7-J10 survey 10.92 vs listing 4 x 1.18 = 4.71.  Re-quote before believing any of these (price tier / brand / stock 0).")
RESULTS.mkdir(exist_ok=True)
(RESULTS / "cost_lines.json").write_text(json.dumps({"listing_tiers_2026-10-13": listing, "stud_usd_500": stud}, indent=1) + "\n")
