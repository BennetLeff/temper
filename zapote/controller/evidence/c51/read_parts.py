#!/usr/bin/env python3
"""Read-only JLC stock read for the C51 parts. A row counts only when the returned model equals the MPN exactly.

fetch_stock._jlc(code="", mpn) accepts the first search hit (an empty code is a substring of every URL), so it can
report another part's stock; this reader does not use it. No login, no cart, no order.
usage: python3 read_parts.py MPN [MPN ...]   -> merges into parts-read.json
"""
import importlib.util, json, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fs", HERE.parent / "fab-loose-ends/consignment/fetch_stock.py")
fs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)


def exact(rows, mpn):
    """Every returned row whose model is exactly mpn (case-insensitive)."""
    return [r for r in rows or [] if (r.get("componentModelEn") or "").strip().lower() == mpn.lower()]


def read(mpn):
    body = json.dumps({"keyword": mpn, "currentPage": 1, "pageSize": 50, "searchSource": "search"})
    out = fs.curl(["-H", "Content-Type: application/json", "-H", "Origin: https://jlcpcb.com",
                   "-H", "Referer: https://jlcpcb.com/parts", "-X", "POST", fs.JLC, "-d", body])
    try:
        rows = json.loads(out)["data"]["componentPageInfo"]["list"]
    except Exception as e:
        return {"t": fs.now(), "error": repr(e)}
    hits = [{"lcsc": r.get("componentCode"), "mfr": r.get("componentBrandEn"), "model": r.get("componentModelEn"),
             "package": r.get("componentSpecificationEn"), "stock": r.get("stockCount"),
             "library": r.get("componentLibraryType"),
             "price_qty1": (r.get("componentPrices") or [{}])[0].get("productPrice")} for r in exact(rows, mpn)]
    return {"t": fs.now(), "hits": sorted(hits, key=lambda h: -(h["stock"] or 0))}


def main():
    out = HERE / "parts-read.json"
    d = json.loads(out.read_text()) if out.exists() else {}
    for m in sys.argv[1:]:
        d[m] = read(m)
        time.sleep(0.6)
        print(m, d[m].get("error") or [(h["lcsc"], h["mfr"], h["package"], h["stock"], h["price_qty1"]) for h in d[m]["hits"]] or "NO EXACT MATCH")
    out.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
