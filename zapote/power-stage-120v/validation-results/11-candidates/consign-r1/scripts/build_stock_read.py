#!/usr/bin/env python3
"""Offline: write the dated stock read sourcing/STOCK-2026-10-18-consign-r1.csv (the scorecard / proto_stock.py
STOCK-*.csv format, READ_COLS) from this study's cached reads: JLC part API (reads/jlc-raw, 2026-10-18T19:29-19:43Z) and
Octopart public pages (reads/octopart-2026-10-18.json, 19:39-19:44Z). One row per ordered MPN whose order route changed
in consign-r1. best_auth_moq_le_need follows the gate rule: the largest authorised, non-broker, in-stock offer whose MOQ is
<= the 20-board need (an unstated MOQ counts as 1, as the 2026-10-15 snapshot did); offers listed under another maker's
name are skipped (D3 / D17 must be Good-Ark). usage: python3 -I scripts/build_stock_read.py"""
import csv, json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
OUT = R.parents[1] / "08-manufacturing-package/native-21/sourcing/STOCK-2026-10-18-consign-r1.csv"
# (line, qty/board, mpn as in fab/bom-jlcpcb.csv, role, jlc code, octopart key, maker filter)
ROWS = [
    ("U41/U42", 2, "R24C2T25/R-R", "fitted; Global Sourcing", "C9900245652", "R24C2T25/R-R", "Recom"),
    ("Q2/Q3/Q5/Q6", 4, "IPW65R018CFD7", "fitted; consigned DigiKey lot", "C3289047", "IPW65R018CFD7XKSA1", "Infineon"),
    ("C21-C23/C151/C152", 5, "B32643H8104J000", "fitted; Global Sourcing", "", "B32643H8104J000", "TDK"),
    ("C5/C6", 2, "B32676G1905K000", "fitted; Global Sourcing", "C3802167", "B32676G1905K000", "TDK"),
    ("L1", 1, "B82726S2243A020", "fitted; Global Sourcing", "C7084710", "B82726S2243A020", "EPCOS"),
    ("D3/D17", 2, "30KPA150CA", "fitted; Global Sourcing (Good-Ark)", "C19111562", "30KPA150CA", "Good-Ark"),
    ("C1/C2", 2, "R463N410050N1K", "fitted; JLC stock, pre-order reserve", "C3299886", "R463N410050N1K", ""),
    ("J3/J11", 2, "B2P3-VH-H(LF)(SN)", "ordered variant of B2P3-VH(LF)(SN)", "C160900", "", ""),
    ("F1", 1, "KLDR025.TXP", "fitted; owner inserts", "C187688", "KLDR025.TXP", "Littelfuse"),
    ("F2", 1, "3403.0279.23", "fitted; Global Sourcing", "C3163739", "3403.0279.23", "Schurter"),
    ("J2/J5", 2, "7466004R", "fitted; Global Sourcing", "C6708126", "7466004R", "Wurth"),
    ("J6", 1, "1704004", "fitted; Global Sourcing if offered", "C5481600", "1704004", "Phoenix"),
    ("RV1", 1, "TMOV20RP175E", "fitted; owner hand-solders", "C1527834", "TMOV20RP175E", "Littelfuse"),
    ("BR1", 1, "GBJ2510-F", "fitted; owner hand-solders", "C526644", "", ""),
    ("T1", 1, "CST3015-200ED", "fitted; JLC stock, pre-order reserve", "C50132500", "", ""),
]
op = json.loads((R / "reads/octopart-2026-10-18.json").read_text())
# Direct distributor reads that Octopart's page did not carry (reads/distributors/_fetch.log): DigiKey's 3403.0279.23 page,
# read in a browser 2026-10-18 (7,183, cut tape MOQ 1); Octopart's 3403.0279.23 listing showed no DigiKey offer.
_t = next(l.split()[0] for l in open(R / "reads/distributors/_fetch.log") if "3403-0279-23" in l)
op["3403.0279.23"]["offers"].append({"seller": "DigiKey", "authorized": True, "broker": False, "mfr": "Schurter",
                                     "stock": 7183, "moq": 1, "usd_ladder": [[1, 3.33], [10, 2.551]], "updated": _t})
cols = ["line", "qty_per_board", "need_20", "aim_2x", "mpn", "role", "lcsc", "jlc_stock", "jlc_lib", "jlc_usd_at_need",
        "jlc_read_utc", "digikey", "mouser", "newark", "best_auth_moq_le_need", "best_auth_usd_at_need", "best_auth_any_moq",
        "octopart_read_utc", "gate_20", "aim_2x_met", "source"]
out = []
for line, q, mpn, role, code, okey, maker in ROWS:
    need = q * 20
    j, jt = {}, ""
    if code:
        rec = json.loads((R / f"reads/jlc-raw/detail_{code}.json").read_text()); j = rec.get("data") or {}; jt = rec["_fetched_utc"]
    js = int(j.get("stockCount") or 0)
    price = ""
    for p in j.get("prices") or []:
        if p["startNumber"] <= need: price = p["productPrice"]
    offs = []
    if okey:
        offs = [o for o in op[okey]["offers"] if o["authorized"] and not o["broker"] and (o["stock"] or 0) > 0
                and (not maker or maker.lower() in (o["mfr"] or "").lower())]
    seller = lambda n: max([o["stock"] for o in offs if o["seller"] == n] or [0])
    within = [o for o in offs if (o["moq"] or 1) <= need]
    b = max(within, key=lambda o: o["stock"]) if within else None
    a = max(offs, key=lambda o: o["stock"]) if offs else None
    usd = ""
    if b:
        for qq, u in b["usd_ladder"]:
            if qq <= need: usd = u
    best = max(js, b["stock"] if b else 0)
    out.append({"line": line, "qty_per_board": q, "need_20": need, "aim_2x": 2 * need, "mpn": mpn, "role": role, "lcsc": code,
                "jlc_stock": js if code else "", "jlc_lib": j.get("componentLibraryType", ""), "jlc_usd_at_need": price,
                "jlc_read_utc": jt, "digikey": seller("DigiKey") if okey else "", "mouser": seller("Mouser") if okey else "",
                "newark": seller("Newark") if okey else "",
                "best_auth_moq_le_need": f"{b['seller']} {b['stock']}" if b else "", "best_auth_usd_at_need": usd,
                "best_auth_any_moq": f"{a['seller']} {a['stock']} (moq {a['moq'] or 'n/a'})" if a else "",
                "octopart_read_utc": op[okey]["fetched_utc"] if okey else "", "gate_20": "PASS" if best >= need else "SHORT",
                "aim_2x_met": best >= 2 * need,
                "source": "11-candidates/consign-r1 (JLC part API + Octopart public pages; digikey.com 403, mouser.com bot wall: "
                          "not read directly; Octopart's Mouser offers are stamped 2026-10-16T21:15Z)"})
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
for o in out:
    print(f"{o['line']:<18} {o['mpn']:<20} need {o['need_20']:>3} JLC {str(o['jlc_stock']):>5} best<=need {o['best_auth_moq_le_need']:<22} {o['gate_20']} 2x:{o['aim_2x_met']}")
