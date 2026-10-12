#!/usr/bin/env python3
"""Build consignment-sheet.csv / consignment-sheet.md from the BOM, stock-snapshot.json (fetch_stock.py) and
distributor_records.json (hand-recorded, timestamped).  Offline and read-only.  Proposals only: no order, cart,
login or contact.  usage: build_sheet.py
"""
import csv, json, math, pathlib

HERE = pathlib.Path(__file__).resolve().parent
CTRL = HERE.parents[2]
BOARDS = 2
bom = list(csv.DictReader(open(CTRL / "fab" / "bom-jlcpcb.csv")))
snap = json.load(open(HERE / "stock-snapshot.json"))
dist = json.load(open(HERE / "distributor_records.json"))


def spares(lot):
    return 2 if lot < 20 else math.ceil(0.1 * lot)


def jstock(code):
    j = snap[code]["jlc"]
    return j.get("stock"), j.get("matched_lcsc"), j.get("t")


# Alternates are PROPOSALS with the evidence that was actually read.  DS = datasheet read in a scratch folder
# (not committed) from the LCSC-hosted copy; sha256 of that copy given so the reading can be reproduced.
ALT_CODES = {"AD8436BRQZ": ["C495329", "C578725", "C652841"], "TPS3703A4330DSERQ1": ["C2861205"], "ERA-3AEB1652V": ["C728584"],
             "RG2012V-431-W-T1": ["C865488", "C4360543"], "CD74HC30PWR": ["C546857"],
             "RC0603FR-078K06L": ["C861587", "C23112"], "B2P-VH(LF)(SN)": ["C160315"]}
ALT = {
    "AD8436BRQZ": {
        "alt": "AD8436ARQZ-R7 (LCSC C495329); also AD8436ARQZ C578725",
        "kind": "pin/footprint-identical, SPEC-DEGRADED (not a like-for-like drop-in)",
        "evidence": "ADI AD8436 Rev. E (sha256 of LCSC copy e230dda9... B copy / 257a2ad3... A copy): ordering guide lists A and B grades in the same 20-lead QSOP RQ-20, -40..125 C; Table 1 columns 'AD8436A, AD8436J' vs 'AD8436B' differ only in accuracy: conversion error +/-10 uV +/-0.5 % rdg (A) vs +/-0.25 % (B); input VOS +/-500 vs +/-250 uV; output-buffer VOS +/-200 vs +/-150 uV. 65 kHz 1 % bandwidth, 8 kOhm input, 16 kOhm output, supply 4.8-36 V identical.",
        "decision": "Owner: accept 0.5 % instead of 0.25 % reading error in the tank-RMS channel (not assessed against the controller error budget here), otherwise consign the B grade."},
    "TPS3703A4330DSERQ1": {
        "alt": "TPS3703A4330DSER (non-Q1, LCSC C2861205)",
        "kind": "same device without AEC-Q100 qualification; only a contingency (JLC stock for the Q1 part is 18)",
        "evidence": "TI SBVS249B (TPS3703, sha256 63a37f1d...) orderable table lists TPS3703A4330DSER ACTIVE, WSON DSE-6 1.5x1.5 mm; its pin table (1 SENSE, 2 VDD, 3 CT, 4 RESET ...) is identical to the TPS3703-Q1 datasheet (sha256 8e872666...), whose nomenclature is the same 'TPS 3703 A 4 330 DSE R Q1'. The non-Q1 part has 0 stock at JLC (C2861205) so it would have to be consigned (DigiKey 2,954 on 2026-10-12).",
        "decision": "Not needed now: JLC holds 18 against a lot need of 4."},
    "ERA-3AEB1652V": {
        "alt": "RT0603BRD0716K5L (Yageo, LCSC C728584)",
        "kind": "drop-in (value, tolerance, TCR, size, power equal)",
        "evidence": "Panasonic ERA-3A datasheet (sha256 8591ebf4...): ERA-3AEB = 0603, 0.1 W, TCR code E +/-25 ppm/K, tolerance code B +/-0.1 %. Yageo RT series datasheet (sha256 0a729d14...): RT0603 1/10 W 75 V, 'D = 25 ppm/C'; JLC parts-search description of RT0603BRD0716K5L (C728584): '100mW 16.5k 75V Thin Film Resistor +/-0.1 % +/-25ppm 0603'. Same sibling family is already on this BOM (RT0603BRD07xxxL).",
        "decision": "Propose swapping R53 to C728584 (JLC stock in snapshot)."},
    "RG2012V-431-W-T1": {
        "alt": "none equal at JLC; degraded option RT0805BRD07430RL (C865488, 0.1 %, +/-25 ppm)",
        "kind": "NO equal-spec alternate in JLC stock; the degraded option doubles the tolerance and 2.5x the TCR",
        "evidence": "JLC search 2026-10-12 for 430 Ohm 0.05 % thin-film 0805: RG2012V-431-W-T1, RG2012V-431-W-T5, RG2012P-431-W-T5, RG2012N-431-W-T1/-T5, RT0805WRD07430RL, RT0805WRC07430RL, RT0805WRB07430RL, RN73R2ATTD4300A25, RN73H2ATTD4300A25, RN732ATTD4300A05 all show stock 0. Susumu RG datasheet (sha256 61928fcb...): 0.05 % is code W; V = 10 ppm per the BOM basis. DigiKey sells the W-T1 only as a 3,000-piece reel ($3,712.35) per the page read.",
        "decision": "Owner: (a) consign a 0.05 % 430 Ohm 0805 from another source (not found in stock via the pages that could be read), or (b) accept 0.1 %/25 ppm for the prototype lot (R39 is the RTD block reference; ratiometric error scales with it)."},
    "CD74HC30PWR": {
        "alt": "74HC30PW,118 (Nexperia, LCSC C546857; -Q100 variant C546858)",
        "kind": "pin-compatible drop-in (same 8-input NAND, same TSSOP-14 pinout, same 2-6 V HC supply)",
        "evidence": "TI CD74HC30 (sha256 670c85e4...) and Nexperia 74HC30 Rev. 10 (sha256 461f481b...): both pin tables are 1 A, 2 B, 3 C, 4 D, 5 E, 6 F, 7 GND, 8 Y, 9/10/13 n.c., 11 G, 12 H, 14 VCC (TSSOP14 SOT402-1 / TI PW); both recommend VCC 2.0-6.0 V. Propagation delay and output drive not compared.",
        "decision": "Propose swapping U22 to C546857 (interlock block: re-run verify_controller.py's HC30 model with the Nexperia pin table, which is identical, before release)."},
    "RC0603FR-078K06L": {
        "alt": "RT0603BRD078K06L (Yageo 0.1 %, C861587) or 0603WAF8061T5E (UniOhm 1 %, C23112)",
        "kind": "drop-in by JLC/LCSC parametric text (8.06 kOhm 0603 100 mW 75 V); no datasheet read",
        "evidence": "JLC parts search 2026-10-12 descriptions: C131052 thick film +/-1 % +/-100 ppm; C861587 thin film +/-0.1 % +/-25 ppm (better); C23112 thick film +/-1 % +/-100 ppm (equal). Weaker evidence than the datasheet-backed rows.",
        "decision": "R31 stock fell from 163 (2026-10-08 CSV) to 3 today: swap to C861587 or C23112 or watch stock."},
    "B2P-VH(LF)(SN)": {
        "alt": "same MPN, JLC listing C160315",
        "kind": "BOM LCSC-code mismatch, not an alternate",
        "evidence": "The BOM's C20571196 is not returned by JLC's parts search; searching the MPN returns C160315 (stock in snapshot, matched_lcsc column).",
        "decision": "Owner/BOM: repoint J13 to the JLC-listed code after confirming it is the same JST part."},
}

rows = []
for r in bom:
    refs = [d.strip() for d in r["Designator"].split(",")]
    pb = len(refs)
    lot = pb * BOARDS
    sp = spares(lot)
    oq = lot + sp
    code, mpn = r["LCSC Part #"], r["Manufacturer Part Number"]
    js, matched, jt = jstock(code)
    ls = snap[code]["lcsc"].get("stock")
    eff = js
    ratio = None if eff is None else eff / oq
    if eff is None:
        status = "JLC-NOT-FOUND-BY-CODE"
    elif eff < oq:
        status = "SHORT"
    elif eff < 10 * oq:
        status = "THIN"
    else:
        status = "OK"
    a = ALT.get(mpn)
    rows.append({"designators": r["Designator"], "mpn": mpn, "lcsc": code, "mount": r["Mount"],
                 "qty_per_board": pb, "qty_lot_2_boards": lot, "spares": sp, "qty_to_supply": oq,
                 "jlc_stock": js, "jlc_matched_lcsc": matched, "jlc_stock_time_utc": jt, "lcsc_stock": ls,
                 "bom_csv_jlc_stock_2026_10_08": r["JLC stock 2026-10-08"], "status": status,
                 "alternate": a["alt"] if a else "", "alternate_kind": a["kind"] if a else ""})
with open(HERE / "consignment-sheet.csv", "w", newline="") as f:
    w = csv.DictWriter(f, list(rows[0]))
    w.writeheader()
    w.writerows(rows)

flag = [x for x in rows if x["status"] != "OK" or x["mpn"] in ALT]
nz = lambda v: "n/a" if v is None else f"{v:,}"
md = ["# Controller 2-board prototype lot: consignment / sourcing sheet", "",
      "Generated by `build_sheet.py` from `stock-snapshot.json` (JLC + LCSC live reads, timestamps inside) and "
      "`distributor_records.json`. Quantity rule: 2 boards, plus spares of 2 per line (10 % when the lot quantity is 20 or more). "
      "Stock status: OK >= 10x the quantity, THIN < 10x, SHORT < quantity. **Proposals only; nothing was ordered.**", "",
      "## Lines needing action", "",
      "| Part (refs) | Supply qty | JLC stock | LCSC stock | CSV 2026-10-08 | Status |", "|---|---|---|---|---|---|"]
for x in flag:
    md.append(f"| {x['mpn']} ({x['designators']}) | {x['qty_to_supply']} ({x['qty_per_board']}/board) | {nz(x['jlc_stock'])} | {nz(x['lcsc_stock'])} | {x['bom_csv_jlc_stock_2026_10_08'] or 'blank'} | {x['status']} |")
md += ["", "## Per-part route and alternates (propose only)", ""]
for mpn, a in ALT.items():
    x = next(v for v in rows if v["mpn"] == mpn)
    md += [f"### {mpn} ({x['designators']}), supply {x['qty_to_supply']}", "",
           f"- Stock: JLC {nz(x['jlc_stock'])} ({x['jlc_stock_time_utc']}), LCSC {nz(x['lcsc_stock'])}.",
           f"- Alternate: **{a['alt']}**: {a['kind']}.",
           "- Alternate stock: " + "; ".join(
               f"{c} {snap[c]['jlc'].get('mfr_part') or snap[c]['lcsc'].get('mfr_part')}: JLC {nz(snap[c]['jlc'].get('stock'))}, LCSC {nz(snap[c]['lcsc'].get('stock'))} ({snap[c]['jlc'].get('t')})"
               for c in ALT_CODES[mpn]) + ".",
           f"- Evidence: {a['evidence']}",
           f"- Decision needed: {a['decision']}", ""]
md += ["## Distributor reads", "", "| MPN | Site | Date | Stock | Qty-1 USD | Lead time | Note |", "|---|---|---|---|---|---|---|"]
for d in dist["records"]:
    md.append(f"| {d['mpn']} | [{d['site']}]({d['url']}) | {d['date']} | {d['stock'] if d['stock'] is not None else 'not shown'} | {d['price_qty1_usd'] if d['price_qty1_usd'] is not None else 'n/a'} | {d['lead_time'] or 'not shown'} | {d['note']} |")
md += ["", "Sites that could not be read: " + "; ".join(f"{x['site']} ({x['result']})" for x in dist["fetch_failures"]), ""]
md += ["## JLC consignment steps (overseas shipper, from JLC's help page dated 2026-09-09, read 2026-10-12)", "",
       "1. In the PCBA order choose to consign the part (mark the BOM line as customer-supplied; JLC's page does not describe the BOM marking, check the order page).",
       "2. Open the consignment form, pick the shipping mode: 'Outside Mainland China' (Hong Kong, Macao, Taiwan) or Mainland China.",
       "3. Package as the system instructs and ship to the Hong Kong warehouse address that the system shows (wrong address may be refused). Seller pays all freight; CNY 5,000+ shipments need formal export clearance or must be split.",
       "4. Enter courier and tracking number, contact name and phone; shipments must be approved before dispatch.",
       "5. Enter sales information: unit price, manufacturer, description, application, country of origin, unit weight, HS code; attach purchase records; tick the Component Sale and Purchase Agreement.",
       "6. JLC reviews the price (2 business days); if status becomes 'Confirm Price', revise and resubmit.",
       "7. Pay the pre-deposit and fees when 'Awaiting Payment': import duty (refundable deposit), import VAT 13 % of (value + duty) (refundable once used in a PCBA order), handling 2 % of declared value, minimum USD 10 per shipment (non-refundable).",
       "8. Ship; status goes 'In Transit'. JLC verifies quantities; resolve any 'Quantity Discrepancy' (confirm or supplement).",
       "9. Download the Component Sales Contract. Storage is free for 3 years; retrieval needs 7 days' notice and costs 30 % of value (min USD 30).", "",
       "Alternative to consigning: JLC 'Global Sourcing' buys from global distributors for the assembly order (search summary: 9-15 days, payment final, parts not shipped to you); whether AD8436BRQZ can be sourced this way is only visible in JLC's BOM tool at order time (not checked: needs an account).",
       "Mainland-China consignment uses the Zhuhai warehouse and is irrelevant unless the parts are bought in China.", ""]
(HERE / "consignment-sheet.md").write_text("\n".join(md))
print(len(rows), "lines;", len(flag), "flagged")
