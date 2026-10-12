#!/usr/bin/env python3
"""Read-only stock snapshot for the controller BOM (and optional extra LCSC codes).

Queries only public, unauthenticated endpoints that the vendors' own web pages call:
  * JLCPCB parts search  POST https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList/v2
  * LCSC product detail  GET  https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=Cxxxx
No login, no cart, no order. Writes stock-snapshot.json with a UTC timestamp per query.
usage: fetch_stock.py [--extra C123,C456] [--out stock-snapshot.json]
"""
import argparse, csv, datetime, json, pathlib, subprocess, time

HERE = pathlib.Path(__file__).resolve().parent
BOM = HERE.parents[2] / "fab" / "bom-jlcpcb.csv"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"
JLC = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList/v2"
LCSC = "https://wmsc.lcsc.com/ftps/wm/product/detail?productCode="


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def curl(args):
    return subprocess.run(["curl", "-s", "-m", "40", "-A", UA] + args, capture_output=True, text=True).stdout


def jlc(code, mpn=None):
    r = _jlc(code, code)
    if r.get("stock") is None and mpn:  # some listings are not found by LCSC code; retry by exact MPN
        r2 = _jlc(code, mpn)
        if r2.get("stock") is not None:
            r2["note"] = "found by MPN search"
            return r2
    return r


def _jlc(code, keyword):
    body = json.dumps({"keyword": keyword, "currentPage": 1, "pageSize": 25, "searchSource": "search"})
    out = curl(["-H", "Content-Type: application/json", "-H", "Origin: https://jlcpcb.com",
                "-H", "Referer: https://jlcpcb.com/parts", "-X", "POST", JLC, "-d", body])
    try:
        lst = json.loads(out)["data"]["componentPageInfo"]["list"]
    except Exception as e:
        return {"error": repr(e), "t": now()}
    for it in lst or []:
        if code in (it.get("lcscGoodsUrl") or "") or (it.get("componentModelEn") or "") == keyword:
            return {"t": now(), "matched_lcsc": (it.get("lcscGoodsUrl") or "").split("_")[-1][:-5] or None,
                    "stock": it.get("stockCount"), "library": it.get("componentLibraryType"),
                    "mfr_part": it.get("componentModelEn"), "package": it.get("componentSpecificationEn"),
                    "price_qty1": (it.get("componentPrices") or [{}])[0].get("productPrice"),
                    "url": f"https://jlcpcb.com/partdetail/{code}"}
    return {"t": now(), "stock": None, "note": "no exact match in search"}


def lcsc(code):
    out = curl([LCSC + code])
    try:
        d = json.loads(out)["result"]
    except Exception as e:
        return {"error": repr(e), "t": now()}
    if not d:
        return {"t": now(), "stock": None, "note": "LCSC returned no result for this code"}
    return {"t": now(), "stock": d.get("stockNumber"), "mfr_part": d.get("productModel"),
            "package": d.get("encapStandard"), "brand": d.get("brandNameEn"),
            "desc": d.get("productIntroEn"),
            "price_qty1_usd": (d.get("productPriceList") or [{}])[0].get("usdPrice"),
            "url": f"https://www.lcsc.com/product-detail/{code}.html"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", default="")
    ap.add_argument("--out", default=str(HERE / "stock-snapshot.json"))
    a = ap.parse_args()
    mpn = {r["LCSC Part #"]: r["Manufacturer Part Number"] for r in csv.DictReader(open(BOM))}
    codes = list(mpn) + [c for c in a.extra.split(",") if c]
    snap = {}
    for c in dict.fromkeys(codes):
        snap[c] = {"jlc": jlc(c, mpn.get(c)), "lcsc": lcsc(c)}
        time.sleep(0.6)
    json.dump(snap, open(a.out, "w"), indent=1, sort_keys=True)
    print(len(snap), "codes ->", a.out)


if __name__ == "__main__":
    main()
