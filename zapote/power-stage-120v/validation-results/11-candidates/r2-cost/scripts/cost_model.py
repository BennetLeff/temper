#!/usr/bin/env python3
"""Round-2 cost model: stage-20 power-board baseline in two price bases, top-25 ranking, and every proposal's $ delta.

Bases (per board, 500 boards):
  S = scorecard basis: STOCK-2026-10-13.csv line_cost_500 (+ stage-20 addendum rows), the number the scorecard prints (check: 234.83).
  B = best-known basis: JLC/LCSC ladder at qty*500 pieces for lines the survey priced as an ESTIMATE (price_is_estimate=yes);
      for non-estimate lines min(S, JLC ladder) only when JLC stock covers qty*500 pieces, else S. (Listings with stock 0 never lower a line.)
Proposal deltas are new-minus-old in each basis. Unit prices that are not in raw/ come from scripts/prices_manual.json (each with URL+date).
Run: python3 -I cost_model.py  -> ../results/cost_model.json, prints markdown tables."""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import jlc_lib as J
SRC = os.path.join(HERE, "..", "..", "..", "08-manufacturing-package", "native-21", "sourcing")
rows = [r for r in csv.DictReader(open(os.path.join(SRC, "STOCK-2026-10-13.csv"))) if r["board"] == "power-19b"]
add = list(csv.DictReader(open(os.path.join(SRC, "STOCK-2026-10-13-addendum-s20.csv"))))
M = json.load(open(os.path.join(HERE, "prices_manual.json")))
# --- stage-20 baseline: swap T1, R39, U36, bank K->J per DECISIONS 23 / addendum
swap = {"T1": "T1", "R39": "R39", "U36": "U36"}
lines = []
for r in rows:
    if r["designators"] == "F1-CLIP": continue            # scorecard excludes the hand-fit clip row
    if r["designators"] == "T1" or r["designators"] == "R39" or r["designators"] == "U36" or r["designators"].startswith("C21,C22"): continue
    lines.append(r)
for a in add:
    lines.append(a)
def f(x):
    try: return float(x)
    except: return 0.0
base = []
for r in lines:
    q = int(r["qty_per_board"]); S = f(r["line_cost_500"]); code = (r["lcsc_code"] or "").strip()
    B = S; note = ""
    if code.startswith("C"):
        d = J.detail(code).get("data") or {}
        need = q * 500; p = J.price_at(code, need); stock = d.get("stockCount") or 0
        if p:
            j = p * q
            if r["price_is_estimate"] == "yes": B = j; note = "est->JLC"
            elif stock >= need and j < S: B = j; note = "JLC covered"
            elif j < S: note = "JLC cheaper but stock %s < %s" % (stock, need)
    if r["mpn"] == "B32654A1104J000": B = S           # addendum already same-channel
    if r["mpn"] == "GBJ2510-F": B = min(B, 1.81933 * q); note = "DK top break 105+: $1.82 (survey used the qty-1 $4.02)"
    if r["mpn"].startswith("R24C2T25"): B = 7.18188 * q; note = "DK T&R 750 break $7.18 (1000 pcs); survey used the 250 break"
    base.append(dict(des=r["designators"], mpn=r["mpn"], qty=q, code=code, S=round(S, 4), B=round(B, 4), jlc_class=r["jlc_class"], mount=r["mount"], note=note))
totS = sum(b["S"] for b in base); totB = sum(b["B"] for b in base)
print("Baseline stage 20 power board: S = %.2f (scorecard 234.83), B = %.2f" % (totS, totB))
assert abs(totS - 234.83) < 0.05, totS
print("\n## Top 25 lines (S rank), with B and note\n\n| # | Designators | MPN | qty | S $ | B $ | class | note |\n|---|---|---|---|---|---|---|---|")
tops = sorted(base, key=lambda b: -b["S"])[:25]
cum = 0
for i, b in enumerate(tops, 1):
    cum += b["S"]
    print("| %d | %s | %s | %d | %.2f | %.2f | %s/%s | %s |" % (i, b["des"][:28], b["mpn"], b["qty"], b["S"], b["B"], b["jlc_class"], b["mount"], b["note"]))
print("\nTop-25 share of S: %.1f %% (%.2f of %.2f)" % (100 * cum / totS, cum, totS))
# --- proposals
P = []
def prop(id, name, S_old, S_new, B_old, B_new, lines, place, risk, safety, effort, note=""):
    P.append(dict(id=id, name=name, dS=round(S_new - S_old, 2), dB=round(B_new - B_old, 2), dlines=lines, dplace=place, risk=risk, safety=safety, effort=effort, note=note))
b = {x["des"]: x for x in base}
def jl(code, qty_total):  # JLC ladder unit at qty_total pieces
    return J.price_at(code, qty_total)
# R2-01 delete D3/D17
d3 = b["D3,D17"]
prop("R2-01", "Delete D3/D17 30KPA150CA clamp pair (bus C is 18.4 uF)", d3["S"], 0, d3["B"], 0, -1, -2, "med-high", True, "schematic + 2 placements removed, copper unchanged", "bus_peak_no_clamp.py")
# R2-02 TVS channel fallback (keep clamp): Brightking C522439 JLC ref (stock 0)
prop("R2-02", "Keep D3/D17 but source Brightking 30KPA150CA-B (C522439, ref price, stock 0)", d3["S"], 2 * jl("C522439", 1000), d3["B"], 2 * jl("C522439", 1000), 0, 0, "med", True, "BOM + owner approval of brand (DC-LINK-CLAMP no-silent-substitution)", "LCSC reference price, zero stock, quote needed")
# R2-03 BR1
br = b["BR1"]; n = jl("C27523", 500)
prop("R2-03", "BR1 GBJ2510-F -> MDD GBJ2510 (C27523)", br["S"], n, br["B"], n, 0, 0, "low", False, "BOM only (same GBJ footprint)", "datasheet I2t not read")
# R2-04 10 uF 1210 x24
c = [x for x in base if x["mpn"] == "UMK325AB7106KM-T"][0]
n = 24 * jl("C138687", 24 * 500)
prop("R2-04", "24x UMK325AB7106KM-T -> Samsung CL32B106KBJNNNE (C138687)", c["S"], n, c["B"], n, 0, 0, "low-med", False, "BOM only; thickness/DC-bias check", "JLC stock 3,923 < 12,000 needed for the current part; 45,882 for the new")
# R2-05 6SVPC220M -> MV
c = [x for x in base if x["mpn"] == "6SVPC220M"][0]
n = 4 * jl("C128504", 2000)
prop("R2-05", "4x 6SVPC220M -> 6SVPC220MV (C128504, lower ESR)", c["S"], n, c["B"], n, 0, 0, "low", False, "BOM only", "stock 13 -> 845")
# R2-06 HS bias module quote at actual break
prop("R2-06", "U41/U42 R24C2T25 priced at the 1000-pc break not the 250 break", b["U41,U42"]["S"], 2 * 7.18188, b["U41,U42"]["B"], 2 * 7.18188, 0, 0, "none", False, "price basis only", "DK T&R break $7.18188 at 750; $6.24 at 1500 pcs (750 boards)")
# R2-07 J7-J10 delete (g02-g03 A) repriced
st = b["J2,J5,J7,J8,J9,J10"]
prop("R1-g02A-studs", "g02-g03 A: J7-J10 leave the mains build (4 of 6 studs), repriced", st["S"] * 4 / 6, 0, st["B"] * 4 / 6, 0, 0, -4, "med", True, "re-layout BR1 zone (round 1)", "S: 4 x $2.73 DK 100-break; JLC listing 1.18 has stock 0")
# R1 g06 P1 PS1 delete
ps1 = b["PS1"]
prop("R1-g06P1", "g06 P1: delete PS1 (IRM-20-15)", ps1["S"], 0, ps1["B"], 0, -1, -1, "med", True, "round 1")
# R1 g05-g07 P2: 2 ISO7710 -> 2 ISO6721FB, and others (take their own totals)
iso = b["U9,U32,U33,U34"]
newS = 2 * 1.287 + 2 * jl("C5216431", 1000); newB = newS
prop("R1-g05P2-iso", "g05-g07 P2, ISO part only: U33/U34 ISO7710 -> ISO6721FB (rest of P2 in their file)", 2 * 1.287, 2 * jl("C5216431", 1000), 2 * 1.287, 2 * jl("C5216431", 1000), 0, 0, "med-high", True, "round 1", "U9/U32 stay ISO7710; ISO7710 at JLC listing is $2.37 (stock 0), TI.com unpriced")
# R1 g04 P1 T1
prop("R1-g04P1-T1", "g04 P1: T1 CST3015-200ED at the JLC listing price (64 pcs only; Coilcraft volume price unquoted)", 11.43, jl("C50132500", 90), 11.43, jl("C50132500", 90), 0, 0, "med", True, "already in stage 20 at the old price", "-4.12 only if a volume quote matches the listing")
# R1 g01 P1 L1 / choke
prop("R1-g01P1-L1", "g01 P1: L1 -> KEMET SC-20-201 (g01's DK EUR5.37@510 x1.16)", 9.88484, 6.2, 9.88484, 6.2, 0, 0, "med", True, "round 1; LCSC reference has the opposite order (TDK 2.11 < KEMET 2.70, both stock 0)", "")
# R1 g04 P4
prop("R1-g04P4", "g04 P4: U10+U11 TLV3201 -> one TLV3202 (JLC ladder)", 2 * 0.45, jl("C129325", 500), 2 * jl("C105188", 1000), jl("C129325", 500), 1, -1, "low-med", False, "round 1 (placements: 2 -> 1)", "")
c56 = b["C5,C6"]; n = 2 * jl("C3802167", 1000)
prop("R2-07", "C5/C6 B32676G1905K000: quote at the LCSC reference ($1.23 at 500 vs DK $6.17)", c56["S"], n, c56["B"], n, 0, 0, "low (price only)", False, "quote request; LCSC listing stock 0, reference price may not be orderable", "UNVERIFIED")
l1 = b["L1"]; n = jl("C1534260", 500)
prop("R2-08", "L1 B82726S2203A020: quote at the LCSC reference ($2.11 at 500 vs DK $9.88)", l1["S"], n, l1["B"], n, 0, 0, "low (price only)", False, "quote request; LCSC listing stock 0", "UNVERIFIED, alternative to g01 P1 (not additive)")
json.dump(dict(baseline_S=totS, baseline_B=totB, top25=tops, base=base, proposals=P), open(os.path.join(HERE, "..", "results", "cost_model.json"), "w"), indent=1)
print("\n## Proposal deltas per board at 500 (negative = saving)\n\n| id | proposal | dS | dB | d lines | d place. | risk | SAFETY |\n|---|---|---|---|---|---|---|---|")
for p in P:
    print("| %s | %s | %+.2f | %+.2f | %d | %d | %s | %s |" % (p["id"], p["name"], p["dS"], p["dB"], p["dlines"], p["dplace"], p["risk"], "yes" if p["safety"] else "no"))
