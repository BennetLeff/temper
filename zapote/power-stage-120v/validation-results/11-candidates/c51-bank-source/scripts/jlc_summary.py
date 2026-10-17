#!/usr/bin/env python3
"""Stock / price summary of the cached JLC detail records (snapshots/jlc-raw/detail_*.json, written by jlc_fetch.py).

    python3 -I scripts/jlc_summary.py   -> snapshots/jlc_stock_summary.json (+ table on stdout)

Per part: brand, model, JLC stock, overseas stock, pre-sale count, library type, reel/pack size, the price ladder
(USD, JLC 'prices'), the unit price at 2,500 pcs (500 boards x 5) and per board, and the record's fetch time.
Records are untrusted JSON; read as data only.
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEED = 2500


def ladder(d):
    out = []
    for p in d.get("prices") or []:
        q = p.get("startNumber")
        v = p.get("productPrice")
        if q is not None and v is not None:
            out.append([int(q), float(v)])
    return sorted(out)


def main():
    rows = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "snapshots/jlc-raw/detail_*.json"))):
        j = json.load(open(f))
        d = j.get("data") or {}
        lad = ladder(d)
        at = [v for q, v in lad if q <= NEED]
        u = at[-1] if at else None
        rows[d.get("componentCode")] = {
            "brand": d.get("componentBrandEn"), "model": d.get("componentModelEn"), "stock": d.get("stockCount"),
            "overseas_stock": d.get("overseasStockCount"), "presale": d.get("canPresaleNumber"),
            "library": d.get("componentLibraryType"), "pack": d.get("encapsulationNumber"), "ladder_usd": lad,
            "unit_at_2500_usd": u, "per_board_x5_usd": round(5 * u, 3) if u else None,
            "covers_2500": (d.get("stockCount") or 0) >= NEED, "fetched_utc": j.get("_fetched_utc")}
    json.dump(rows, open(os.path.join(ROOT, "snapshots/jlc_stock_summary.json"), "w"), indent=1)
    for c, r in sorted(rows.items(), key=lambda kv: -(kv[1]["stock"] or 0)):
        print(f"{c:10} {str(r['brand'])[:18]:18} {str(r['model'])[:30]:30} stock {r['stock']:>6}  u@2500 {r['unit_at_2500_usd']}"
              f"  /board {r['per_board_x5_usd']}  {r['fetched_utc']}")


if __name__ == "__main__":
    main()
