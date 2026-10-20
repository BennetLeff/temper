#!/usr/bin/env python3
"""Compact log of the JLC part searches behind the candidate lists (README section 2), from jlc_fetch.py's cache.

    python3 -I scripts/search_log.py      # cache hits are offline; a missing search is fetched (online)

Writes results/jlc-search-log.json: per search, every hit (code, library, JLC stock, MPN, maker, description) and the
fetch time. The raw search caches are not committed (9 MB); the detail_*.json records of the cited parts are."""
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jlc_fetch as j  # noqa: E402

SEARCHES = [  # (keyword, page size, why)
    ("68Ω 2512 2W", 12, "R_on: 2 W 2512 68 ohm"),
    ("68Ω 2512 3W", 12, "R_on: 3 W 2512 68 ohm (none in stock)"),
    ("68Ω 2512 1.5W", 12, "R_on: 1.5 W 2512 68 ohm"),
    ("2512 68Ω 1% 2W", 12, "R_on: 1 % 2 W"),
    ("2512 68Ω 1%", 12, "R_on: 1 W 1 % alternates (no terminal-rated 68 ohm in stock)"),
    ("RC2512FK-7W68RL", 12, "R_on: Yageo 1 % double power (0 stock)"),
    ("CRCW251268R0FKEGHP", 12, "R_on: Vishay CRCW-HP 1.5 W (0 stock)"),
    ("MCR100JZHF68R0", 12, "R_on: ROHM MCR100 1 W (0 stock)"),
    ("RK73H3ATTE68R0F", 12, "R_on: KOA RK73H 1 W (0 stock)"),
    ("4.99kΩ 0603 250mW", 12, "split bleed: 0.25 W 0603 4.99 k"),
    ("PS03W4F4991T5E", 12, "split bleed: UniRoyal PS03 1/4 W (0 stock)"),
    ("RC0603FR-7W4K99L", 12, "split bleed: Yageo double power (0 stock)"),
    ("6SVPC220MV", 12, "C126-C129: fitted part"),
    ("Polymer Aluminum Capacitors SMD,D6.3xL6mm", 100, "C126-C129: 6.3 mm SMD polymer scan"),
    ("Polymer Aluminum Capacitors SMD,D6.3xL5.9mm", 100, "C126-C129: 6.3 mm SMD polymer scan"),
    ("Polymer Aluminum Capacitors SMD,D6.3xL5.8mm", 100, "C126-C129: 6.3 mm SMD polymer scan"),
    ("Polymer Aluminum Capacitors 125℃ 6.3mm", 100, "C126-C129: 125 C scan"),
    ("6SVPK", 50, "C126-C129: Panasonic SVPK (125 C) in 6.3 mm"),
    ("SVPD", 50, "C126-C129: Panasonic SVPD (125 C)"),
    ("SVZ0JM221", 30, "C126-C129: AISHI SVZ (listing says 2000 h at 125 C, category 105 C: a 105 C part)"),
]


def main():
    out = []
    for kw, n, why in SEARCHES:
        body = {"keyword": kw, "currentPage": 1, "pageSize": n}
        key = "search_" + hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10]
        hits = j.search(kw, "all", n)
        raw = json.load(open(os.path.join(j.RAW, key + ".json")))
        out.append({"keyword": kw, "page_size": n, "why": why, "fetched_utc": raw.get("_fetched_utc"),
                    "hits": [dict(zip(("code", "library", "jlc_stock", "mpn", "maker", "describe"), h)) for h in hits]})
    p = HERE.parent / "results/jlc-search-log.json"
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {p.name}: {len(out)} searches, {sum(len(s['hits']) for s in out)} hits")


if __name__ == "__main__":
    main()
