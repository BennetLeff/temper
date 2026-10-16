#!/usr/bin/env python3
"""Controls for the scorecard stock gate (bom_buildable_500 / bom_lines_short_at_500) and same-channel price comparison.

    python3 -I native-21/layout/gates/test_stock_gate.py

Why: stage 49 was ACCEPTed against stage 48 ("cheaper parts_usd_at_500_v2, jlc_assemblable_share_500") although its new
resonant-bank part, TDK B32643B8104J000 (5 per board), had JLC stock 0, no distributor stock, 28-week lead and MOQ 2080
(flag OWNER_PREORDER_CONSIGN); and its $1.37 saving per part compared a DigiKey price for the old part with a JLC catalogue
price (0 stock) for the new one. Synthetic cases check the rule; real-data cases run the committed s48 snapshot / BOM, and
the s49 swap built from the verbatim s49 snapshot row. PS_ROOT (env) overrides the unit root.
"""
import copy
import csv
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("scorecard", HERE / "scorecard.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

PS = Path(os.environ.get("PS_ROOT") or sc.UNIT)
SRC = PS / "validation-results/08-manufacturing-package/native-21/sourcing"
SNAP48 = SRC / "study-2026-10-15/snapshot/s48/SNAPSHOT-s48.csv"
BOM48 = SRC / "study-2026-10-15/snapshot/s48/bom-jlcpcb.s48.csv"
CARD48 = PS / "validation-results/10-benchmark/scorecard-native21s48.json"
STOCKS = ",".join(str(p) for p in sorted(SRC.glob("STOCK-2026-10-13*.csv")))
fails = 0


def check(name, ok, detail=""):
    global fails
    fails += not ok
    print(("ok   " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


# ---- synthetic snapshot rows
def srow(jlc=0, lib="extended", auth=0, auth_total=None, unauth=0):
    return {"jlc_stock": str(jlc), "jlc_library": lib, "auth_best_stock": str(auth),
            "auth_total_stock": str(auth if auth_total is None else auth_total), "unauth_max_stock": str(unauth)}


def bq(s, **kw):
    return sc.buildable_stock(s, **kw)[0]


check("JLC library stock counts", bq(srow(jlc=3000)) == 3000)
check("authorised distributor in-stock quantity counts (global sourcing)", bq(srow(auth=3000)) == 3000)
check("larger single source, not the sum (JLC places from one source)", bq(srow(jlc=1200, auth=1500)) == 1500)
check("JLC stock of a part outside the JLC library does not count", bq(srow(jlc=9000, lib="")) == 0)
check("broker stock does not count", bq(srow(unauth=10**6)) == 0)
check("stock split over several distributors does not count (only the best single source)", bq(srow(auth=800, auth_total=5000)) == 800)
check("not in the snapshot -> 0", bq(None) == 0)
check("OWNER_PREORDER_CONSIGN -> 0 even with JLC stock", bq(srow(jlc=100000), flags="LOW_JLC_STOCK(50 < 500);OWNER_PREORDER_CONSIGN(>=550)") == 0)
check("LONG_LEAD flag -> 0", bq(srow(jlc=100000), flags="LONG_LEAD(28 wk)") == 0)
check("legacy LEAD_12wk survey note does not zero a line that has counted stock", bq(srow(jlc=100000), flags="LEAD_12wk;SINGLE_SOURCE") == 100000)

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    HDR = ["line", "mpn", "jlc_stock", "jlc_library", "auth_best_stock", "auth_total_stock", "unauth_max_stock"]

    def write(rows, name, cols):
        with open(td / name, "w", newline="") as f:
            w = csv.DictWriter(f, cols)
            w.writeheader()
            w.writerows(rows)
        return td / name

    bom = write([{"Designator": "C1,C2", "Manufacturer Part Number": "OK"}, {"Designator": "U1", "Manufacturer Part Number": "PRE"},
                 {"Designator": "R1,R2,R3", "Manufacturer Part Number": "LOW"}], "bom.csv", ["Designator", "Manufacturer Part Number"])
    snap = write([{"mpn": "OK", **srow(jlc=1000)}, {"mpn": "PRE", **srow(jlc=5000)}, {"mpn": "LOW", **srow(jlc=1499)}],
                 "snap.csv", ["mpn", "jlc_stock", "jlc_library", "auth_best_stock", "auth_total_stock", "unauth_max_stock"])
    stock = write([{"board": "power-19b", "mpn": "PRE", "flags": "OWNER_PREORDER_CONSIGN(>=550)"}], "stock.csv", ["board", "mpn", "flags"])
    g = sc.stock_gate(bom, snap, stock)
    short = {l["mpn"]: l for l in g["bom_short_lines_500"]}
    check("synthetic: exactly the pre-order line and the 1499 < 3 x 500 line fail", set(short) == {"PRE", "LOW"} and g["bom_lines_short_at_500"] == 2, g)
    check("synthetic: need = qty_per_board x 500, listed with stock", short["LOW"]["need"] == 1500 and short["LOW"]["buildable"] == 1499
          and short["PRE"]["need"] == 500 and short["PRE"]["buildable"] == 0 and short["PRE"]["jlc_stock"] == "5000")
    check("synthetic: no snapshot -> no verdict", sc.stock_gate(bom, "", stock) == {})

# ---- real data: s48
g48 = sc.stock_gate(BOM48, SNAP48, STOCKS)
mp48 = {l["mpn"]: l for l in g48["bom_short_lines_500"]}
# Honest record of what the committed s48 snapshot says (nothing loosened to make s48 pass): 15 lines are short at 500 boards
EXPECT48 = {"KLDR025.TXP", "R463N410050N1K", "B82726S2203A020", "DE1E3RA222MA4BP01F", "B32676G1905K000", "6SVPC220MV",
            "PMEG6030EP,115", "IPW65R018CFD7", "CST3015-200ED", "B32654A1104J000", "AC05000001507JAC00", "C0603C102J5GACTU",
            "LM4050AEM3-2.5/NOPB", "1704004", "VOL628A-2X001T"}
check("s48: the gate names the 15 short lines (they are real, listed in the report)", set(mp48) == EXPECT48, sorted(set(mp48) ^ EXPECT48))
check("s48: old bank part B32654A1104J000 holds 881 of 2500", mp48["B32654A1104J000"]["buildable"] == 881 and mp48["B32654A1104J000"]["need"] == 2500)
check("s48: LM4050 (U5) is zero by its OWNER_PREORDER_CONSIGN flag although JLC shows 50",
      mp48["LM4050AEM3-2.5/NOPB"]["buildable"] == 0 and mp48["LM4050AEM3-2.5/NOPB"]["jlc_stock"] == "50")
check("s48: every other BOM line passes", g48["bom_lines_short_at_500"] == 15)
c48 = json.load(open(CARD48))
check("s48 card carries the metric, the failing list and a failing release gate",
      c48["cost"].get("bom_lines_short_at_500") == 15 and c48["gates"].get("bom_buildable_500") is False
      and {l["mpn"] for l in c48["cost"]["bom_short_lines_500"]} == EXPECT48)

# ---- real data: the s49 swap (verbatim s49 snapshot row for B32643B8104J000, DECISIONS 68; flags from STOCK addendum s49)
S49_ROW = {"mpn": "B32643B8104J000", "jlc_stock": "0", "jlc_library": "listed_no_stock", "auth_best_stock": "0.0",
           "auth_total_stock": "0", "unauth_max_stock": "27690"}      # 27690 is broker stock in the s49 snapshot: not counted
S49_FLAGS = "ZERO_JLC_STOCK;OWNER_PREORDER_CONSIGN(MOQ 2080, 28 wk);LONG_LEAD(28 wk)"
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    rows = list(csv.DictReader(open(BOM48)))
    for r in rows:
        if r["Manufacturer Part Number"] == "B32654A1104J000":
            r["Manufacturer Part Number"], r["LCSC Part #"] = "B32643B8104J000", "C3781430"
    with open(td / "bom49.csv", "w", newline="") as f:
        w = csv.DictWriter(f, rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    srows = list(csv.DictReader(open(SNAP48)))
    srows = [r for r in srows if r["mpn"] != "B32654A1104J000"]
    srows.append({**{k: "" for k in srows[0]}, **S49_ROW})
    with open(td / "snap49.csv", "w", newline="") as f:
        w = csv.DictWriter(f, srows[0].keys())
        w.writeheader()
        w.writerows(srows)
    with open(td / "stock49.csv", "w", newline="") as f:
        f.write("board,mpn,flags\n" + f'power-19b,B32643B8104J000,"{S49_FLAGS}"\n')
    g49 = sc.stock_gate(td / "bom49.csv", td / "snap49.csv", STOCKS + "," + str(td / "stock49.csv"))
    mp49 = {l["mpn"]: l for l in g49["bom_short_lines_500"]}
    check("s49: B32643B8104J000 fails the gate: need 5 x 500 = 2500, buildable 0",
          "B32643B8104J000" in mp49 and mp49["B32643B8104J000"]["need"] == 2500 and mp49["B32643B8104J000"]["buildable"] == 0, mp49.get("B32643B8104J000"))
    check("s49: broker stock (27,690) is not counted", mp49["B32643B8104J000"]["buildable"] == 0)
    nof = sc.stock_gate(td / "bom49.csv", td / "snap49.csv", STOCKS)["bom_short_lines_500"]
    check("s49: with no flags the same row still fails on the counts (JLC 0, no authorised stock)",
          any(l["mpn"] == "B32643B8104J000" for l in nof))

    # ---- compare: card against card
    def card(g, lines, tag):
        c = copy.deepcopy(c48)
        c["tag"] = tag
        c["cost"].update(g)
        c["cost"]["price_lines_500"] = lines
        return c

    def pl(mpn, ch, unit, cp, tier="P2", d="C21,C22,C23,C151,C152"):
        return {"designators": d, "mpn": mpn, "qty": 5, "tier": tier, "channel": ch, "unit": unit, "channel_prices": cp}

    old = card(g48, [pl("B32654A1104J000", "digikey", 1.48848, {"digikey": 1.48848, "jlc": 0.5218})], "bench")
    new = card(g49, [pl("B32643B8104J000", "jlc", 0.248, {"jlc_no_stock": 0.248}, tier="P3")], "cand")
    new["cost"]["parts_usd_at_500_v2"] = old["cost"]["parts_usd_at_500_v2"] - 6.19      # the card totals: a $1.24 x 5 "saving"
    notes = []
    ok, reasons, cheaper, better = sc.compare(new, old, notes)
    check("compare s49 vs s48: REJECT on the newly unbuildable line", not ok and any("newly unbuildable" in r and "B32643B8104J000" in r for r in reasons), reasons)
    check("compare: the unbuyable part's saving is not counted as cheaper", "parts_usd_at_500_v2" not in cheaper, cheaper)
    check("compare: price-channel mismatch flagged (digikey→jlc)",
          any(n.startswith("price-channel mismatch: B32654A1104J000→B32643B8104J000") and "digikey→jlc" in n for n in notes), notes)

    # common channel exists: re-priced on it, saving judged there
    new2 = copy.deepcopy(new)
    new2["cost"]["price_lines_500"] = [pl("B32643B8104J000", "jlc", 0.248, {"jlc": 0.248, "digikey": 1.309}, tier="P1")]
    notes2 = []
    sc.compare(new2, old, notes2)
    check("compare: a line with a common channel is re-priced there (jlc: 0.5218 -> 0.248), not flagged unresolved",
          any("re-priced on jlc" in n and "0.5218" in n and "0.248" in n for n in notes2), notes2)
    d, = [sc.channel_check(new2["cost"], old["cost"])[1]]
    check("channel_check: like-for-like delta is (0.248 - 0.5218) x 5", abs(d - (0.248 - 0.5218) * 5) < 1e-6, d)

    # same part, same channel: no mismatch note, no flag
    same = card(g48, [pl("B32654A1104J000", "digikey", 1.4, {"digikey": 1.4})], "same")
    n3 = sc.channel_check(same["cost"], old["cost"])[0]
    check("compare: same channel on both cards -> no mismatch note", n3 == [], n3)

    # a candidate no worse than the benchmark on stock is not rejected for it
    keep = card(g48, old["cost"]["price_lines_500"], "keep")
    ok4, r4, _, _ = sc.compare(keep, old, [])
    check("compare: same short lines as the benchmark -> stock ratchet silent", not any("short" in r or "unbuildable" in r for r in r4), r4)

print("PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
