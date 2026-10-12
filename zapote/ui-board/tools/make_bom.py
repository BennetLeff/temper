#!/usr/bin/env python3
"""Build bom/ui-parts.json and bom/ui-parts.csv for the UI board.

The part table below is the single source of the non-netlist facts (LCSC code, role, datasheet
basis). Designators and footprints come from frozen/default.net + resolved-components.json.
Stock, JLC library type (basic / extended) and price come from a read-only query of the public
JLCPCB parts search (one POST per part, no login, nothing ordered):

  python3 tools/make_bom.py --refresh   # query JLC, rewrite the JSON and CSV
  python3 tools/make_bom.py             # rewrite the CSV from the committed JSON + netlist

The CSV is in the JLCPCB assembly BOM layout (Comment, Designator, Footprint, LCSC Part #) with
extra columns after those four.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from netlist import attach_resolved, read_netlist  # noqa: E402

UNIT = Path(__file__).resolve().parents[1]
API = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"

# mpn -> facts. `lcsc_exception` marks the one hand-fitted panel part with no LCSC listing.
PARTS: dict[str, dict] = {
    "B12B-XH-A(LF)(SN)": dict(lcsc="C158027", role="J7: UI bus to the controller (same part as the controller's J7)",
        basis="JST eXH catalogue p.1-2 (7.0 mm body, 9.8 mm mated); controller bom/controller-parts.json"),
    "7-215079-6": dict(lcsc="C306122", role="J2: encoder socket, mates the 7-215083-6 on the Grayhill lead",
        basis="Grayhill 62AG/VG Rev. 02/2024 p.1 (connector is AMP 7-215083-6); enclosure R33 DECISIONS 3 (TE 7-215079-6)"),
    "PM254V-11-20-H85": dict(lcsc="C46595982", role="J3: 1x20 2.54 mm socket for the OLED header (8.5 mm tall: OPEN, DECISIONS U-OPEN-1)",
        basis="Newhaven rev. 7 p.4 (recommended header 1x20 2.54 mm); LCSC listing 8.5 mm",
        alternates=[dict(lcsc="C2905423", mpn="KH-2.54FH-1X20P-H8.5"), dict(lcsc="C41417332", mpn="HX PM2.54-1x20P ZC")]),
    "MCP23S08-E/SO": dict(lcsc="C152205", role="U1: SPI I/O expander, opcode 0x40",
        basis="Microchip DS20001919F p.4, p.22, p.27-28 (1.8-5.5 V, 10 MHz at 2.7-5.5 V I-temp). The JLC listing says 4.5-5.5 V; the datasheet governs",
        alternates=[dict(lcsc="C631462", mpn="MCP23S08T-E/SO")]),
    "TMP122AIDBVR": dict(lcsc="C2877606", role="U2: temperature near the OLED (FW-UI-1 derate)",
        basis="TI SBOS272B p.2-3, p.9. Low stock at JLC: buy before the board run"),
    "TLV3202AIDR": dict(lcsc="C129325", role="U3: encoder A/B level restorer (threshold 1.5 V)",
        basis="TI SBOS561C p.3 (pins), p.6 (electrical)"),
    "SRV05-4": dict(lcsc="C2836319", role="U4-U7: ESD arrays (J7, buttons, encoder); same part as the controller's J7",
        basis="MSKSEMI SRV05-4; controller DECISIONS C26"),
    "GSD9605YB-3V2800": dict(lcsc="C255327", role="BZ1: self-oscillating electromagnetic buzzer, 3.3 V rated (-20..+70 C)",
        basis="Inghai spec sheet V1.1 p.1-2",
        alternates=[dict(lcsc="C530415", mpn="GSD9605YB-5V2800", note="-30..+85 C, 5 V rated, 2-12 V operating; same 9.6 x 9.6 footprint; SPL at 3.3 V not specified"),
                    dict(lcsc="C42420997", mpn="SMD-9650-3327", note="-20..+80 C, 3.3 V rated")]),
    "AO3400A": dict(lcsc="C20917", role="Q1: buzzer low-side switch", basis="LCSC C20917 listing (30 V, 1.45 V max Vth, 48 mohm at 2.5 V)"),
    "1N4148WS": dict(lcsc="C2128", role="D1 buzzer flyback; D2 OLED RES# discharge", basis="LCSC C2128 listing (100 V, 150 mA, 4 ns)"),
    "BLM18PG121SN1D": dict(lcsc="C14709", role="FB1: encoder supply bead (50 mohm max)", basis="LCSC C14709 listing (120 ohm at 100 MHz, 2 A, 50 mohm)"),
    "0603WAF1000T5E": dict(lcsc="C22775", role="100 ohm 1 %: MISO source termination, buzzer gate", basis="UNI-ROYAL 0603 1 %"),
    "0603WAF1001T5E": dict(lcsc="C21190", role="1 kohm 1 %: button / encoder-switch series", basis="UNI-ROYAL 0603 1 %"),
    "0603WAF1002T5E": dict(lcsc="C25804", role="10 kohm 1 %: pull-ups, comparator input and divider", basis="UNI-ROYAL 0603 1 %"),
    "0603WAF1003T5E": dict(lcsc="C25803", role="100 kohm 1 %: buzzer gate pull-down", basis="UNI-ROYAL 0603 1 %"),
    "0603WAF1202T5E": dict(lcsc="C22790", role="12 kohm 1 %: comparator reference top", basis="UNI-ROYAL 0603 1 %"),
    "0603WAF4703T5E": dict(lcsc="C23178", role="470 kohm 1 %: comparator hysteresis", basis="UNI-ROYAL 0603 1 %"),
    "CC0603KRX7R9BB104": dict(lcsc="C14663", role="100 nF 50 V X7R: decoupling", basis="Yageo 0603 X7R"),
    "CL10A105KB8NNNC": dict(lcsc="C15849", role="1 uF 50 V X5R: OLED RES# timing", basis="Samsung 0603 X5R"),
    "CL10A106KP8NNNC": dict(lcsc="C19702", role="10 uF 10 V X5R: encoder and buzzer bulk", basis="Samsung 0603 X5R"),
    "CL21A226MAQNNNE": dict(lcsc="C45783", role="22 uF 25 V X5R 0805: J7 and OLED bulk", basis="Samsung 0805 X5R"),
    "0603B471K500NT": dict(lcsc="C1620", role="470 pF 50 V X7R: encoder noise capacitor (< 1 nF per Grayhill)", basis="Grayhill 62AG/VG p.3"),
    "IPR3PAD2": dict(lcsc=None, lcsc_exception="hand-fitted IP67 panel pushbutton (APEM IP series, straight PC pins); no LCSC listing; "
        "bought with the enclosure controls BOM (controls-apem-*) and soldered after PCBA",
        role="SW1-SW3: START / STOP / BACK buttons", basis="APEM IP series catalogue p.2, p.5"),
}

OFF_BOARD = [
    dict(item="OLED module NHD-3.12-25664UCW2 (rev. 7)", source="enclosure controls BOM (Newhaven_OLED_module)", lcsc=None),
    dict(item="Encoder Grayhill 62VG15-H9S-030C with 3 in lead and AMP 7-215083-6 plug", source="enclosure controls BOM (controls-encoder)", lcsc=None),
    dict(item="Jumper: JST XHP-12 housing x2 + SXH-001T-P0.6 contacts x24, AWG28, 120 mm cut", source="enclosure harness_UI_fascia_to_controller", lcsc=None),
]


def query(code: str) -> dict:
    req = urllib.request.Request(API, data=json.dumps({"currentPage": 1, "pageSize": 5, "keyword": code,
                                                        "searchSource": "search"}).encode(),
                                 headers={"Content-Type": "application/json"})
    err = None
    for _ in range(3):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=40))
            for c in d["data"]["componentPageInfo"]["list"] or []:
                if c.get("componentCode") == code:
                    lib = {"base": "basic", "expand": "extended"}.get(c.get("componentLibraryType"), c.get("componentLibraryType"))
                    return {"jlc_library": lib, "jlc_stock": c.get("stockCount"),
                            "jlc_price_usd_qty1": (c.get("componentPrices") or [{}])[0].get("productPrice"),
                            "jlc_model": c.get("componentModelEn")}
            return {}
        except Exception as exc:        # noqa: BLE001 - retry then report
            err = exc
    raise SystemExit(f"JLC query failed for {code}: {err}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    nl = attach_resolved(read_netlist(UNIT / "frozen/default.net"), UNIT / "frozen/resolved-components.json")
    path = UNIT / "bom/ui-parts.json"
    old = json.loads(path.read_text())["parts"] if path.exists() else {}
    today = datetime.date.today().isoformat()
    parts = {}
    for mpn, meta in PARTS.items():
        rec = dict(meta)
        if args.refresh and meta["lcsc"]:
            rec.update(query(meta["lcsc"]))
            rec["jlc_stock_checked"] = today
            alts = []
            for a in meta.get("alternates", []):
                a = dict(a)
                a.update({k: v for k, v in query(a["lcsc"]).items() if k in ("jlc_library", "jlc_stock")})
                alts.append(a)
            if alts:
                rec["alternates"] = alts
        elif mpn in old:
            for k in ("jlc_library", "jlc_stock", "jlc_price_usd_qty1", "jlc_model", "jlc_stock_checked"):
                if k in old[mpn]:
                    rec[k] = old[mpn][k]
            if "alternates" in old[mpn]:
                rec["alternates"] = old[mpn]["alternates"]
        parts[mpn] = rec
    by = defaultdict(list)
    for ref, mpn in nl.mpn.items():
        by[mpn].append(ref)
    for mpn, rec in parts.items():
        rec["designators"] = sorted(by.get(mpn, []), key=lambda r: (r.rstrip("0123456789"), int("".join(c for c in r if c.isdigit()) or 0)))
        fp = {nl.footprint[r] for r in by.get(mpn, [])}
        rec["footprint"] = sorted(fp)[0] if fp else ""
        rec["qty"] = len(rec["designators"])
    unknown = sorted(set(by) - set(parts))
    if unknown:
        raise SystemExit(f"netlist MPNs missing from PARTS: {unknown}")
    lines = [r for r in parts.values() if r["qty"]]
    basic = sum(1 for r in lines if r.get("jlc_library") == "basic")
    ext = sum(1 for r in lines if r.get("jlc_library") == "extended")
    out = {"schema": "temper.ui-board.parts.v1",
           "checked": "stock, JLC library type and price read from the public JLCPCB parts search "
                      f"({today if args.refresh else 'see jlc_stock_checked'}), read-only; datasheets are scratch copies outside the repo, "
                      "cited by document and page in each part's basis",
           "summary": {"bom_lines": len(lines), "lcsc_lines": sum(1 for r in lines if r["lcsc"]), "basic": basic, "extended": ext,
                       "no_lcsc": [m for m, r in parts.items() if not r["lcsc"]], "placements": sum(r["qty"] for r in lines)},
           "parts": parts, "off_board": OFF_BOARD}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=False) + "\n")
    with (UNIT / "bom/ui-parts.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Qty", "JLC Library", "JLC Stock", "Stock Checked", "Note"])
        for mpn, r in sorted(parts.items(), key=lambda kv: kv[1]["designators"][0] if kv[1]["designators"] else "~"):
            if not r["qty"]:
                continue
            w.writerow([mpn, ",".join(r["designators"]), r["footprint"], r["lcsc"] or "", r["qty"], r.get("jlc_library", ""),
                        r.get("jlc_stock", ""), r.get("jlc_stock_checked", ""), r.get("lcsc_exception", "")])
    print(json.dumps(out["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
