#!/usr/bin/env python3
"""Read-only JLC/LCSC lookup of the parts the C1 change requests (DECISIONS C37-C41) add.

Searches JLC's public parts search by exact MPN (the same endpoint as
evidence/fab-loose-ends/consignment/fetch_stock.py, imported from there), then reads the LCSC
product detail of the matched code. Writes new-parts-snapshot.json with a UTC timestamp per query.
No login, no cart, no order.
"""
import importlib.util
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fetch_stock", HERE.parent / "fab-loose-ends/consignment/fetch_stock.py")
fs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)

MPNS = ["ESD5Z5.0T1G", "CC0603KRX7R9BB224", "RC0603FR-07499KL", "RG2012V-431-W-T1", "RT0603BRD0786K6L",
        "SN74LVC2G14DBVR", "SN74LVC1G86DBVR", "SN74LVC74APWR", "GRM1885C1H103JA01D", "GRM31C5C1H104JA01L",
        "C0603C102J5GACTU", "RT0603BRD071KL", "SN74LVC1G32DBVR"]


def main():
    mpns = sys.argv[1:] or MPNS
    out = HERE / "new-parts-snapshot.json"
    snap = json.loads(out.read_text()) if out.exists() else {}
    for m in mpns:
        j = fs._jlc("", m)
        code = j.get("matched_lcsc")
        snap[m] = {"jlc": j, "lcsc": fs.lcsc(code) if code else None}
        time.sleep(0.6)
    out.write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n")
    for m in mpns:
        r = snap[m]
        print(f"{m:22s} {r['jlc'].get('matched_lcsc')!s:10s} jlc {r['jlc'].get('stock')!s:>9s} "
              f"{r['jlc'].get('library')!s:9s} lcsc {(r['lcsc'] or {}).get('stock')!s:>9s} "
              f"{(r['lcsc'] or {}).get('desc', '')!s:.80s}")


if __name__ == "__main__":
    main()
