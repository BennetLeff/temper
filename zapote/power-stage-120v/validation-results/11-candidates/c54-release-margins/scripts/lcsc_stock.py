#!/usr/bin/env python3
"""LCSC stock and price read (online once; cached with the read time in ./lcsc-raw beside this script).

    python3 -I scripts/lcsc_stock.py C2793964 C4036134 ...     # prints code, MPN, stock, price at 5 and 500 pcs

Endpoint: LCSC's public product-detail JSON (wmsc.lcsc.com/ftps/wm/product/detail). JLC's own assembly stock is read
separately by jlc_fetch.py (jlc-raw/detail_*.json); both reads are quoted in results/bom-patch.json."""
import json
import os
import sys
import time
import urllib.request

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lcsc-raw")
URL = "https://wmsc.lcsc.com/ftps/wm/product/detail?productCode="


def detail(code):
    os.makedirs(RAW, exist_ok=True)
    p = os.path.join(RAW, f"detail_{code}.json")
    if not os.path.exists(p):
        req = urllib.request.Request(URL + code, headers={"User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        json.dump(d, open(p, "w"), indent=1)
    return json.load(open(p))


def price_at(prices, n):
    """Unit price (USD) of the ladder step that applies at quantity n (LCSC ladders: ladder / usdPrice)."""
    best = None
    for s in sorted(prices or [], key=lambda s: s["ladder"]):
        if s["ladder"] <= n:
            best = s
    return None if best is None else best["usdPrice"]


def summary(code):
    d = detail(code)
    r = d.get("result") or {}
    pl = r.get("productPriceList") or []
    return {"lcsc": code, "mpn": r.get("productModel"), "brand": r.get("brandNameEn"), "package": r.get("encapStandard"),
            "stock": r.get("stockNumber"), "min_order": r.get("minBuyNumber"), "price_usd_at_5": price_at(pl, 5),
            "price_usd_at_500": price_at(pl, 500), "ladder": [(s["ladder"], s["usdPrice"]) for s in pl],
            "read_utc": d["_fetched_utc"]}


if __name__ == "__main__":
    for c in sys.argv[1:]:
        print(json.dumps(summary(c)))
