#!/usr/bin/env python3
"""Prototype order table (ORDER.md): per BOM line the quantity per board, the latest JLC stock and
price in the repo's snapshots (no network), and the stock check against a build quantity.

    python3 evidence/order/order_table.py [--boards N]     # writes evidence/order/order-table.json

Sources, newest first per LCSC code:
  evidence/c1-crs/new-parts-snapshot.json            JLC + LCSC reads 2026-10-15 (C37-C41 parts)
  evidence/fab-loose-ends/consignment/stock-snapshot.json   JLC + LCSC reads 2026-10-12
  bom/controller-parts.json                           jlc_stock_* / lcsc_stock_* keys (2026-10-08..15)
Price is JLC's quantity-1 unit price (USD) from the same read; lines without one are listed.
"""
import argparse
import csv
import json
from pathlib import Path

UNIT = Path(__file__).resolve().parents[2]
NEW = UNIT / "evidence/c1-crs/new-parts-snapshot.json"
OLD = UNIT / "evidence/fab-loose-ends/consignment/stock-snapshot.json"
PARTS = UNIT / "bom/controller-parts.json"
BOM = UNIT / "fab/bom-jlcpcb.csv"
OUT = Path(__file__).resolve().parent / "order-table.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", type=int, default=5)
    a = ap.parse_args()
    by_code = {}
    for k, v in json.loads(OLD.read_text()).items():
        if isinstance(v, dict) and "jlc" in v:
            by_code[k] = {"stock": v["jlc"].get("stock"), "price": v["jlc"].get("price_qty1"),
                          "library": v["jlc"].get("library"), "t": v["jlc"].get("t"), "src": OLD.name}
    for mpn, v in json.loads(NEW.read_text()).items():
        if isinstance(v, dict) and "jlc" in v and v["jlc"].get("matched_lcsc"):
            j = v["jlc"]
            by_code[j["matched_lcsc"]] = {"stock": j.get("stock"), "price": j.get("price_qty1"),
                                          "library": j.get("library"), "t": j.get("t"), "src": NEW.name}
    parts = json.loads(PARTS.read_text())
    parts = parts.get("parts", parts)
    rows, total = [], 0.0
    for r in csv.DictReader(BOM.open()):
        refs = [x.strip() for x in r["Designator"].split(",")]
        code, mpn = r["LCSC Part #"], r["Manufacturer Part Number"]
        snap = dict(by_code.get(code, {}))
        if snap.get("stock") is None:
            rec = parts.get(mpn, {})
            for key in sorted((k for k in rec if k.startswith(("jlc_stock_", "lcsc_stock_"))), reverse=True):
                if rec[key] is not None:
                    snap.update({"stock": rec[key], "t": key, "src": PARTS.name})
                    break
        need = len(refs) * a.boards
        stock = snap.get("stock")
        status = ("unknown" if stock is None else "zero" if stock == 0 else
                  "below_2x_build" if stock < 2 * need else "ok")
        line_cost = None if snap.get("price") is None else snap["price"] * len(refs)
        if line_cost is not None:
            total += line_cost
        rows.append({"mpn": mpn, "lcsc": code, "refs": refs, "qty_per_board": len(refs), "mount": r["Mount"],
                     "jlc_stock": stock, "stock_read": snap.get("t"), "source": snap.get("src"),
                     "library": snap.get("library"), "unit_price_usd": snap.get("price"),
                     "line_cost_per_board_usd": line_cost, "status": status})
    no_price = [x["mpn"] for x in rows if x["unit_price_usd"] is None]
    out = {"boards": a.boards, "bom_lines": len(rows), "placements_per_board": sum(x["qty_per_board"] for x in rows),
           "parts_cost_per_board_usd_qty1_priced_lines": round(total, 2), "lines_without_price": no_price,
           "extended_library_lines": sum(1 for x in rows if x["library"] == "expand"),
           "attention": [x for x in rows if x["status"] != "ok"], "rows": rows}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows", "attention")}, indent=1))
    for x in out["attention"]:
        print(x["status"], x["mpn"], x["lcsc"], x["refs"], x["jlc_stock"], x["stock_read"])


if __name__ == "__main__":
    main()
