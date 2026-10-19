#!/usr/bin/env python3
"""Offline: build results/consign-table.csv from the cached reads (reads/jlc-raw/, reads/octopart-2026-10-18.json).
One row per consigned / hand-assembled line and per candidate alternate: need at 20 boards (controller: 5), the 2x target, JLC stock and
JLC's own assembly mode for the code, the best single authorised non-broker distributor offer (brokers and unauthorised
sellers count 0), and whether one source holds >= 2x the need. usage: python3 -I scripts/consign_table.py"""
import csv, json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
BOARDS = 20
# (line, designators, qty/board, role, mpn, jlc code or '', octopart key or '')
ROWS = [
    ("U41/U42", "U41,U42", 2, "fitted", "R24C2T25/R-R", "C9900245652", "R24C2T25/R-R"),
    ("U41/U42", "U41,U42", 2, "trap: JLC auto-match, non-/R series", "R24C2T25-R", "C22466894", ""),
    ("U41/U42", "U41,U42", 2, "THT alt (ALT-BIAS A3)", "MGJ2D242005SC", "", "MGJ2D242005SC"),
    ("U41/U42", "U41,U42", 2, "SMD second source (basic, 18-25 V)", "UCC14240QDWNRQ1", "", "UCC14240QDWNRQ1"),
    ("Q2/Q3/Q5/Q6", "Q2,Q3,Q5,Q6", 4, "fitted", "IPW65R018CFD7XKSA1", "C3289047", "IPW65R018CFD7XKSA1"),
    ("bank", "C21,C22,C23,C151,C152", 5, "fitted", "B32643H8104J000", "", "B32643H8104J000"),
    ("bank", "C21,C22,C23,C151,C152", 5, "fallback (27.5 mm hole, 22 A)", "MMK104J3DF1KN208G2", "C528962", ""),
    ("C5/C6", "C5,C6", 2, "fitted", "B32676G1905K000", "C3802167", "B32676G1905K000"),
    ("L1", "L1", 1, "fitted", "B82726S2243A020", "C7084710", "B82726S2243A020"),
    ("D3/D17", "D3,D17", 2, "fitted", "30KPA150CA", "C19111562", "30KPA150CA"),
    ("C1/C2", "C1,C2", 2, "fitted", "R463N410050N1K", "C3299886", "R463N410050N1K"),
    ("C1/C2", "C1,C2", 2, "alt", "B32923C3105M189", "C3299462", "B32923C3105M189"),
    ("J3/J11", "J3,J11", 2, "fitted", "B2P3-VH(LF)(SN)", "C160745", "B2P3-VH(LF)(SN)"),
    ("J3/J11", "J3,J11", 2, "alt (gray, colour only)", "B2P3-VH-H(LF)(SN)", "C160900", ""),
    ("J3/J11", "J3,J11", 2, "alt (PBT-GF body)", "B2P3-VH-B(LF)(SN)", "C158010", ""),
    ("F1", "F1", 1, "fitted (cartridge, inserted)", "KLDR025.TXP", "C187688", "KLDR025.TXP"),
    ("F1 clips", "F1-CLIP", 2, "fitted (no CPL row)", "01250003H", "C223911", "01250003H"),
    ("F2", "F2", 1, "fitted", "3403.0279.23", "C3163739", "3403.0279.23"),
    ("J2/J5", "J2,J5", 2, "fitted", "7466004R", "C6708126", "7466004R"),
    ("J6", "J6", 1, "fitted", "1704004", "C5481600", "1704004"),
    ("RV1", "RV1", 1, "fitted (deselected, hand-fit)", "TMOV20RP175E", "C1527834", "TMOV20RP175E"),
    ("T1", "T1", 1, "fitted", "CST3015-200ED", "C50132500", ""),
    ("BR1", "BR1", 1, "fitted (owner fits at heatsink step)", "GBJ2510-F", "C526644", ""),
    ("J1", "J1", 1, "fitted", "1714971", "C92145", ""),
    ("C3/C4", "C3,C4", 2, "fitted", "DE1E3RA222MJ4BH01F", "C7170908", ""),
    ("C38-C41", "C38,C39,C40,C41", 4, "fitted", "B32652A0104K000", "C125402", ""),
    ("R130", "R130", 1, "fitted", "AC05000001507JAC00", "C1382388", ""),
    ("PS2", "PS2", 1, "fitted", "MPM-20-24", "C6675337", ""),
    ("J4", "J4", 1, "fitted", "0430451612", "C491447", ""),
    ("controller R39", "R39", 1, "fitted (controller, 3-5 boards)", "RG2012V-431-W-T1", "C4260028", "RG2012V-431-W-T1"),
]
op = json.loads((R / "reads/octopart-2026-10-18.json").read_text())
out = []
BRAND = {"R24C2T25/R-R": "Recom", "MGJ2D242005SC": "Murata", "UCC14240QDWNRQ1": "Texas", "30KPA150CA": "Good-Ark"}
for line, des, q, role, mpn, code, okey in ROWS:
    brand = BRAND.get(okey, "")
    need = q * (5 if line.startswith("controller") else BOARDS)
    j = {}
    if code:
        rec = json.loads((R / f"reads/jlc-raw/detail_{code}.json").read_text())
        j = dict(rec.get("data") or {}, _t=rec.get("_fetched_utc"))
    best = ("", 0, "")
    if okey:
        r = op[okey]
        for o in r["offers"]:
            if brand and brand.lower() not in (o["mfr"] or "").lower():
                continue  # same MPN under another maker's name (e.g. EVISUN / YLPTEC copies of Murata / RECOM numbers)
            if o["authorized"] and not o["broker"] and (o["stock"] or 0) > best[1]:
                best = (o["seller"], o["stock"], o["mfr"])
    jst = j.get("stockCount") or 0
    single = max(jst, best[1])
    out.append({"line": line, "designators": des, "role": role, "mpn": mpn, "need": need, "target_2x": 2 * need,
                "jlc_code": code, "jlc_stock": jst if code else "", "jlc_assembly_mode": j.get("assemblyMode", ""),
                "jlc_read_utc": j.get("_t", ""), "best_auth_dist": best[0], "best_auth_stock": best[1] if okey else "",
                "brand_filter": brand, "best_auth_mfr": best[2], "octopart_read_utc": op[okey]["fetched_utc"] if okey else "",
                "one_source_ge_2x": single >= 2 * need, "jlc_ge_2x": jst >= 2 * need})
if __name__ == "__main__":
    p = R / "results/consign-table.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    for o in out:
        print(f"{o['line']:<14} {o['mpn']:<22} need {o["need"]:>3} JLC {str(o['jlc_stock']):>6} {o['jlc_assembly_mode']:<10} "
              f"dist {o['best_auth_dist'][:18]:<18} {str(o['best_auth_stock']):>6}  2x:{o['one_source_ge_2x']}  JLC2x:{o['jlc_ge_2x']}  ({o['role']})")
