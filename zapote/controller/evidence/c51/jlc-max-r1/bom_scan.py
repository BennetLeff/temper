#!/usr/bin/env python3
"""Scan the C51 BOM (frozen/default.csv, MPN -> LCSC from bom/controller-parts.json) against JLC part records.

Reads reads/detail_<LCSC>.json.gz through jlc_fetch.detail() (fetched once, then cached; --refresh re-reads).
Flags a line when: JLC stock < 2 x need at 5 / 10 / 20 boards, the JLC model differs from the MPN, the part
has no LCSC code, or JLC assembles it by hand (assemblyMode manualWeld = THT). No login, no cart, no order.

usage: python3 -I bom_scan.py [--refresh]   -> bom-scan.json
"""
import csv, io, json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
UNIT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import jlc_fetch  # noqa: E402

LOTS = (5, 10, 20)
C49_COMMIT = "cb7ac6435"   # last commit before the C51 circuit (07848ba2f): its frozen BOM is the C49 board's


def c49_parts():
    """MPN per designator on the C49 frozen BOM (git), to mark what C51 added or changed."""
    txt = subprocess.run(["git", "show", f"{C49_COMMIT}:zapote/controller/frozen/default.csv"], cwd=UNIT,
                         capture_output=True, text=True, check=True).stdout
    return {d: r["Comment"] for r in csv.DictReader(io.StringIO(txt)) for d in r["Designator"].split(",")}


def earlier_stock():
    """Earlier JLC reads in the repo: 2026-10-18 order read (by LCSC) and the 2026-11-25 C51 parts read (by MPN)."""
    o = json.loads((UNIT / "evidence/order/stock-read-2026-10-18.json").read_text())
    a = {r["lcsc"]: (r["stock"], o["read_utc"]) for r in o["rows"]}
    b = {}
    for mpn, v in json.loads((UNIT / "evidence/c51/parts-read.json").read_text()).items():
        for h in v.get("hits") or []:
            b[h["lcsc"]] = (h["stock"], v["t"])
    return a, b


def norm(m):
    """JLC drops hyphens and leading zeros in some models (ERA3AEB103V, 430451600): compare alphanumerics only."""
    return "".join(ch for ch in (m or "").lower() if ch.isalnum()).lstrip("0")


def main():
    if "--refresh" in sys.argv:
        jlc_fetch.REFRESH = True
    parts = json.loads((UNIT / "bom/controller-parts.json").read_text())["parts"]
    rows = list(csv.DictReader(open(UNIT / "frozen/default.csv")))
    c49 = c49_parts()
    s1018, s1125 = earlier_stock()
    out, flagged = [], []
    for r in rows:
        mpn, refs = r["Comment"], r["Designator"].split(",")
        lcsc = (parts.get(mpn) or {}).get("lcsc")
        line = {"mpn": mpn, "refs": refs, "qty": len(refs), "footprint": r["Footprint"].split(":")[-1], "lcsc": lcsc,
                "c51_new_refs": [x for x in refs if c49.get(x) != mpn],
                "need_x2": {n: 2 * len(refs) * n for n in LOTS}}
        if lcsc in s1018:
            line["stock_2026_10_18"] = s1018[lcsc]
        if lcsc in s1125:
            line["stock_2026_11_25_c51_read"] = s1125[lcsc]
        if not lcsc:
            line["issue"] = ["no LCSC code (not a JLC line)"]
            out.append(line)
            flagged.append(line)
            continue
        d = jlc_fetch.detail(lcsc)
        raw = jlc_fetch.load(HERE / "reads" / f"detail_{lcsc}.json")
        line.update({"fetched_utc": raw.get("_fetched_utc"), "jlc_model": d.get("componentModelEn"),
                     "stock": d.get("stockCount"), "library": d.get("componentLibraryType"),
                     "assembly": d.get("assemblyMode"), "describe": d.get("describe"),
                     "price_qty1": ((d.get("prices") or [{}])[0]).get("productPrice")})
        issues = []
        if norm(d.get("componentModelEn")) != norm(mpn):
            issues.append(f"JLC model {d.get('componentModelEn')!r} != MPN")
        for n in LOTS:
            line[f"cover_{n}"] = (line["stock"] or 0) >= 2 * line["qty"] * n
        short = [n for n in LOTS if not line[f"cover_{n}"]]
        if short:
            issues.append("stock < 2 x need at " + "/".join(map(str, short)) + " boards")
        prev = [v[0] for v in (line.get("stock_2026_10_18"), line.get("stock_2026_11_25_c51_read")) if v]
        if (d.get("componentLibraryType") == "expand" and prev and max(prev) > 0
                and (line["stock"] or 0) < 0.5 * max(prev) and (line["stock"] or 0) < 10 * line["need_x2"][20] / 2):
            issues.append(f"Extended, stock down from {max(prev)} to {line['stock']}")
        if d.get("assemblyMode") == "manualWeld":
            issues.append("JLC hand-solders (THT)")
        line["issue"] = issues
        out.append(line)
        if issues:
            flagged.append(line)
    res = {"bom": "frozen/default.csv (C51 circuit)", "lines": len(out), "lots": LOTS,
           "rule": "stock >= 2 x qty/board x boards", "flagged": [f["mpn"] for f in flagged], "rows": out}
    (HERE / "bom-scan.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    for f in flagged:
        print(f["mpn"], f.get("lcsc"), f["qty"], f.get("stock"), f.get("library"), f.get("assembly"), f["issue"])
    print(len(out), "lines;", len(flagged), "flagged")


if __name__ == "__main__":
    main()
