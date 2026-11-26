#!/usr/bin/env python3
"""Offline: every JLC part seen in reads/search_*.json.gz, filtered to R39's window:
400 / 402 / 430 ohm, tolerance <= 0.1 %, TCR <= 10 ppm/K (owner's bound), any package.
Value / tolerance / TCR are parsed from JLC's own 'describe' string (the detail reads carry the same
fields as attributes). usage: python3 -I r39_candidates.py  -> r39-candidates.json
"""
import glob, json, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
VALUES = (400.0, 402.0, 430.0)
sys.path.insert(0, str(HERE))
import jlc_fetch  # noqa: E402


def parse(desc):
    m = re.search(r"(\d+(?:\.\d+)?)(k|m|M)?Ω", desc)
    t = re.search(r"±([\d.]+)%", desc)
    p = re.search(r"±([\d.]+)ppm", desc)
    r = float(m.group(1)) * {"k": 1e3, "M": 1e6, "m": 1e-3, None: 1.0}[m.group(2)] if m else None
    return r, (float(t.group(1)) if t else None), (float(p.group(1)) if p else None)


def main():
    seen, files = {}, sorted(glob.glob(str(HERE / "reads/search_*.json.gz")))
    for f in files:
        d = jlc_fetch.load(pathlib.Path(f))
        for c in ((d.get("data") or {}).get("componentPageInfo") or {}).get("list") or []:
            seen[c["componentCode"]] = dict(c, _file=pathlib.Path(f).name, _fetched_utc=d.get("_fetched_utc"))
    match, near = [], []
    for code, c in seen.items():
        r, tol, tcr = parse(c.get("describe") or "")
        if r not in VALUES or tol is None or tcr is None:
            continue
        row = {"lcsc": code, "model": c.get("componentModelEn"), "brand": c.get("componentBrandEn"),
               "package": c.get("componentSpecificationEn"), "ohm": r, "tol_pct": tol, "tcr_ppm": tcr,
               "stock": c.get("stockCount"), "library": c.get("componentLibraryType"),
               "read": c["_file"], "fetched_utc": c["_fetched_utc"]}
        if tol <= 0.1 and tcr <= 10:
            match.append(row)
        elif tol <= 0.1 and tcr <= 25 and (c.get("stockCount") or 0) > 0:
            near.append(row)
    key = lambda x: (-(x["stock"] or 0), x["ohm"], x["tcr_ppm"])
    out = {"search_files": len(files), "unique_parts_seen": len(seen),
           "window": "400/402/430 ohm, tol <= 0.1 %, TCR <= 10 ppm/K",
           "matches": len(match), "matches_in_stock": [m for m in sorted(match, key=key) if (m["stock"] or 0) > 0],
           "matches_zero_stock": sorted(match, key=key)[len([m for m in match if (m['stock'] or 0) > 0]):],
           "stocked_outside_window_tcr_15_25ppm": sorted(near, key=key)}
    (HERE / "r39-candidates.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(out["search_files"], "search files;", out["unique_parts_seen"], "parts;", out["matches"], "in window;",
          len(out["matches_in_stock"]), "in stock")
    for m in out["matches_in_stock"]:
        print(m)


if __name__ == "__main__":
    main()
