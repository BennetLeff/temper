#!/usr/bin/env python3
"""Per-line stock table for the prototype lot, on the scorecard's own stock-gate basis (read only).

    python3 -I owner-items/order/scripts/proto_stock.py [--boards 20] [--csv OUT.csv]

Every fitted line of fab/bom-jlcpcb.csv against qty_per_board x boards, with the same inputs and rules as
native-21/layout/gates/scorecard.py stock_gate(): the latest SNAPSHOT-*.csv, the STOCK-*.csv list in the scorecard's
default order, and a dated read (STOCK-2026-10-16*.csv) over the snapshot row when it is newer; buildable stock is the
larger of JLC library stock and ONE authorised distributor's stock (never a sum; brokers, split stock and lead-time-only
listings count 0); the prototype count ignores the OWNER_PREORDER_CONSIGN / LONG_LEAD flags, as the gate does.
The total of short lines equals the card's bom_lines_short_proto (asserted). Prints a Markdown table; --csv writes one row
per line. It adds no stock read of its own.
"""
import sys as _s; _s.dont_write_bytecode = True
import argparse
import csv
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[5]                                   # zapote/power-stage-120v
SC = UNIT / "native-21/layout/gates/scorecard.py"
spec = importlib.util.spec_from_file_location("scorecard", SC)
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", type=int, default=sc.PROTO_BOARDS)
    ap.add_argument("--csv")
    a = ap.parse_args()
    bom = sc.FAB / "bom-jlcpcb.csv"
    src = sc.VR / "08-manufacturing-package/native-21/sourcing"
    s13 = sorted(src.glob("STOCK-2026-10-13*.csv"))
    stock = ",".join(str(p) for p in s13 + sorted(set(src.glob("STOCK-*.csv")) - set(s13)))
    snap_path = sorted(src.glob("SNAPSHOT-*.csv"))[-1]
    snap = {r["mpn"].strip(): r for r in csv.DictReader(open(snap_path))}
    newer = {}
    for mpn, rd in sc._stock_reads(stock).items():          # same override rule as stock_gate()
        s0 = snap.get(mpn)
        if rd["read_utc"] and (s0 is None or rd["read_utc"] > sc._read_utc(s0.get("fetched_utc"))):
            snap[mpn] = {**(s0 or {"mpn": mpn, "auth_total_stock": "0", "unauth_max_stock": "0"}),
                         "jlc_stock": rd["jlc_stock"], "jlc_library": rd["jlc_library"], "auth_best_stock": rd["auth_best_stock"]}
            newer[mpn] = f"{rd['read_file']} {rd['read_utc']}"
    rows = []
    for r in csv.DictReader(open(bom)):
        mpn = r["Manufacturer Part Number"].strip()
        q = len([d for d in r["Designator"].split(",") if d.strip()])
        have, why = sc.buildable_stock(snap.get(mpn), "", ignore_flags=True)
        s = snap.get(mpn) or {}
        rows.append({"designators": r["Designator"], "mpn": mpn, "lcsc": r["LCSC Part #"], "assembly": r["Assembly"],
                     "qty_per_board": q, "need": q * a.boards, "buildable": int(have),
                     "jlc_stock": s.get("jlc_stock", ""), "jlc_library": s.get("jlc_library", ""),
                     "auth_best_stock": s.get("auth_best_stock", ""), "source": why,
                     "read": newer.get(mpn, f"{snap_path.name} {sc._read_utc(s.get('fetched_utc'))}".strip()),
                     "short": int(have) < q * a.boards})
    gate = sc.stock_gate(bom, str(snap_path), stock, a.boards)
    assert sum(r["short"] for r in rows) == gate["bom_lines_short_proto"], (sum(r["short"] for r in rows), gate)
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"{len(rows)} lines, {a.boards} boards, short {gate['bom_lines_short_proto']}; snapshot {snap_path.name}; "
          f"dated-read overrides {sorted(newer.keys() & {r['mpn'] for r in rows})}")
    print("| Designators | MPN | LCSC | Assembly | Need | Buildable | JLC | Best authorised | Read |")
    print("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |")
    for r in rows:
        print(f"| {r['designators']} | {r['mpn']} | {r['lcsc']} | {r['assembly']} | {r['need']} | {r['buildable']}"
              f"{' **SHORT**' if r['short'] else ''} | {r['jlc_stock']} ({r['jlc_library']}) | {r['auth_best_stock']} | {r['read']} |")


if __name__ == "__main__":
    main()
