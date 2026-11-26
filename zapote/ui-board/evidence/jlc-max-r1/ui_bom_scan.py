#!/usr/bin/env python3
"""Scan the UI board BOM (bom/ui-parts.csv, JLC layout) against JLC part records (reads/detail_<LCSC>.json.gz via
jlc_fetch.detail; cached, --refresh re-reads). Flags stock < 2 x need at 5 / 10 / 20 boards, no LCSC code, or a
JLC hand-solder (manualWeld) part. No login, no cart, no order. usage: python3 -I ui_bom_scan.py -> ui-bom-scan.json
"""
import csv, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
UNIT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import jlc_fetch  # noqa: E402

LOTS = (5, 10, 20)


def main():
    if "--refresh" in sys.argv:
        jlc_fetch.REFRESH = True
    out = []
    for r in csv.DictReader(open(UNIT / "bom/ui-parts.csv")):
        refs = r["Designator"].split(",")
        line = {"mpn": r["Comment"], "refs": refs, "qty": len(refs), "lcsc": r["LCSC Part #"] or None,
                "stock_2026_10_12": int(r["JLC Stock"]) if r["JLC Stock"] else None,
                "need_x2": {n: 2 * len(refs) * n for n in LOTS}, "issue": []}
        if not line["lcsc"]:
            line["issue"].append("no LCSC code: " + r["Note"])
        else:
            d = jlc_fetch.detail(line["lcsc"])
            raw = jlc_fetch.load(HERE / "reads" / f"detail_{line['lcsc']}.json")
            line.update({"fetched_utc": raw.get("_fetched_utc"), "jlc_model": d.get("componentModelEn"),
                         "stock": d.get("stockCount"), "library": d.get("componentLibraryType"),
                         "assembly": d.get("assemblyMode"), "describe": d.get("describe")})
            short = [n for n in LOTS if (line["stock"] or 0) < line["need_x2"][n]]
            if short:
                line["issue"].append("stock < 2 x need at " + "/".join(map(str, short)) + " boards")
            if d.get("assemblyMode") == "manualWeld":
                line["issue"].append("JLC hand-solders (THT)")
        out.append(line)
    (HERE / "ui-bom-scan.json").write_text(json.dumps({"bom": "bom/ui-parts.csv", "lots": LOTS, "rows": out},
                                                      indent=1, ensure_ascii=False) + "\n")
    for l in out:
        print(l["mpn"], l["lcsc"], l["qty"], l.get("stock"), l.get("stock_2026_10_12"), l.get("library"),
              l.get("assembly"), l["issue"])


if __name__ == "__main__":
    main()
