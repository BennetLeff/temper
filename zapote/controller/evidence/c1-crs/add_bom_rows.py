#!/usr/bin/env python3
"""Add the C37-C41 parts to bom/controller-parts.json (stock from new-parts-snapshot.json,
2026-10-15). Idempotent: existing rows are replaced by these.

    python3 evidence/c1-crs/add_bom_rows.py
"""
import json
from pathlib import Path

UNIT = Path(__file__).resolve().parents[2]
BOM = UNIT / "bom/controller-parts.json"
SNAP = json.loads((Path(__file__).resolve().parent / "new-parts-snapshot.json").read_text())


def stock(mpn):
    return SNAP[mpn]["jlc"]["stock"]


ROWS = {
    "RG2012V-431-W-T1": {
        "origin": "ported: zapote/rtd (RTDSensing); restored by C37 (sensor-r3 CR-2), reverting the C35 RT0805 swap",
        "basis": "Susumu RG2012 430 ohm 0.05 % 5 ppm/K 0805 1/8 W (RG series ordering table; RTD_CIRCUIT_AUDIT.md)",
        "lcsc": "C4260028", "jlc_stock_2026_10_15": stock("RG2012V-431-W-T1"),
        "procurement": "JLC/LCSC stock 0 on 2026-10-15: consign (DigiKey 408-1660-1-ND class) or order to JLC global sourcing"},
    "RC0603FR-07499KL": {
        "origin": "controller C37 (sensor-r3 CR-1): RTD open-input pull-ups on the J3 sense nodes",
        "basis": "Yageo RC_L 499 k 1 % 0603 100 mW 75 V", "lcsc": "C131054",
        "jlc_stock_2026_10_15": stock("RC0603FR-07499KL")},
    "CC0603KRX7R9BB224": {
        "origin": "controller C37 (sensor-r3 CR-1): 220 nF at each J3 pin",
        "basis": "Yageo CC 220 nF 10 % 50 V X7R 0603", "lcsc": "C107083",
        "jlc_stock_2026_10_15": stock("CC0603KRX7R9BB224")},
    "RT0603BRD0786K6L": {
        "origin": "controller C38 (sensor-r3 CR-5): rim trip threshold divider top",
        "basis": "Yageo RT 86.6 k 0.1 % 25 ppm 0603", "lcsc": "C861580",
        "jlc_stock_2026_10_15": stock("RT0603BRD0786K6L")},
    "ESD5Z5.0T1G": {
        "origin": "controller C40 (sensor-r3 CR-6): RIM_SENSE TVS (VRWM 5.0 V > v3v3 max; the ESD5Z3.3 it replaces had 3.3 V)",
        "basis": "onsemi ESD5Z series DS: VRWM 5.0 V, IR 0.05 uA max, VBR 6.2 V min, VC 18.6 V at 9.4 A; SOD-523",
        "lcsc": "C82044", "jlc_stock_2026_10_15": stock("ESD5Z5.0T1G")},
    "SN74LVC1G86DBVR": {
        "origin": "controller C39: capacitive-mode detector CT_ZC polarity XOR",
        "basis": "TI SCES222Q: tpd 5 ns max at 3.3 V (CL 50 pF, -40..85 C), ICC 15 uA max (-40..125 C)",
        "lcsc": "C402161", "jlc_stock_2026_10_15": stock("SN74LVC1G86DBVR")},
    "SN74LVC74APWR": {
        "origin": "controller C39: capacitive-mode detector sampling flip-flops (one per leg-A switch)",
        "basis": "TI SCAS287U: CLK->Q 5.2 ns, PRE/CLR->Q 5.4 ns, tsu 3 ns at 3.3 V; ICC 10 uA; TSSOP-14",
        "lcsc": "C350561", "jlc_stock_2026_10_15": stock("SN74LVC74APWR")},
    "TC2050-IDC-NL-LAND": {
        "origin": "controller C41: J11 debug/programming port as a Tag-Connect TC2050-IDC-NL footprint",
        "basis": "Tag-Connect TC2050-IDC-NL land (KiCad Connector:Tag-Connect_TC2050-IDC-NL_2x05_P1.27mm_Vertical): "
                 "copper pads and holes only, no fitted part",
        "board_only": True},
}


def main():
    doc = json.loads(BOM.read_text())
    doc["parts"].update(ROWS)
    BOM.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(ROWS)} rows set; {len(doc['parts'])} parts")


if __name__ == "__main__":
    main()
