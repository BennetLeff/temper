#!/usr/bin/env python3
"""Read-only JLC stock read for every line of fab/bom-jlcpcb.csv (C53 review m9), with evidence/c51/read_parts.py's exact
MPN match. No login, no cart, no order. Falls back to a search by the LCSC code when the model string differs. Writes stock-read.json here: per line its MPN, the BOM's LCSC code, quantity
per board, and the exact-match hits; flags lines whose BOM code has no hit or stock under 5 boards' need.
usage: python3 evidence/c53-order/read_stock.py"""
import csv, importlib.util, json, pathlib, time

HERE = pathlib.Path(__file__).resolve().parent
UNIT = HERE.parent.parent
spec = importlib.util.spec_from_file_location("rp", UNIT / "evidence/c51/read_parts.py")
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)

out, flags = {}, []
for row in csv.DictReader(open(UNIT / "fab/bom-jlcpcb.csv")):
    mpn, code, refs = row["Manufacturer Part Number"], row["LCSC Part #"], row["Designator"].split(",")
    r = rp.read(mpn)
    time.sleep(0.6)
    hit = next((h for h in r.get("hits", []) if h["lcsc"] == code), None)
    if hit is None:     # JLC writes some models differently (430451600, ERA3AEB103V): search the BOM's code itself
        body = json.dumps({"keyword": code, "currentPage": 1, "pageSize": 10, "searchSource": "search"})
        raw = rp.fs.curl(["-H", "Content-Type: application/json", "-H", "Origin: https://jlcpcb.com", "-H",
                          "Referer: https://jlcpcb.com/parts", "-X", "POST", rp.fs.JLC, "-d", body])
        try:
            rows = [x for x in json.loads(raw)["data"]["componentPageInfo"]["list"] if x.get("componentCode") == code]
        except Exception:
            rows = []
        if rows:
            x = rows[0]
            hit = {"lcsc": code, "model": x.get("componentModelEn"), "stock": x.get("stockCount"),
                   "library": x.get("componentLibraryType"), "by_code": True}
            r.setdefault("hits", []).append(hit)
        time.sleep(0.6)
    need5 = 5 * len(refs)
    out[mpn] = {"lcsc_bom": code, "qty_per_board": len(refs), "read": r,
                "bom_code_stock": hit and hit["stock"], "library": hit and hit["library"]}
    if r.get("error") or hit is None or (hit["stock"] or 0) < need5:
        flags.append({"mpn": mpn, "lcsc": code, "refs": refs, "need_5_boards": need5,
                      "stock": hit and hit["stock"], "error": r.get("error"),
                      "other_codes": [(h["lcsc"], h["stock"]) for h in r.get("hits", []) if h["lcsc"] != code]})
(HERE / "stock-read.json").write_text(json.dumps({"lines": out, "flags": flags}, indent=1, sort_keys=True) + "\n")
print(len(out), "lines read;", len(flags), "flagged")
for f in flags:
    print(" ", f)
