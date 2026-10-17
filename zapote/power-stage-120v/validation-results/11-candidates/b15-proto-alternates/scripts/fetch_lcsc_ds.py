#!/usr/bin/env python3
"""Download the LCSC-hosted datasheet PDF for JLC/LCSC part codes into ../sources/<prefix>-<MPN>/ds.pdf (online).
Reads the dataManualUrl from the cached JLC detail record (jlc_fetch.py detail <code> first). The LCSC page is a
viewer shell: the first datasheet.lcsc.com PDF link in it is followed. PDFs are untrusted data (never executed).
usage: python3 -I fetch_lcsc_ds.py <prefix> C123 [C456 ...]"""
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read()


prefix = sys.argv[1]
for code in sys.argv[2:]:
    x = json.loads((ROOT / f"snapshots/jlc-raw/detail_{code}.json").read_text())["data"]
    mpn = re.sub(r"[^A-Za-z0-9._-]", "_", x["componentModelEn"])
    d = ROOT / "sources" / f"{prefix}-{mpn}"
    d.mkdir(parents=True, exist_ok=True)
    url = x.get("dataManualUrl") or ""
    body = get(url) if url else b""
    if not body.startswith(b"%PDF"):
        m = re.search(rb"https://datasheet\.lcsc\.com/datasheet/pdf/[0-9a-f]+\.pdf\?productCode=C\d+", body)
        body = get(m.group(0).decode()) if m else b""
        url = m.group(0).decode() if m else url
    ok = body.startswith(b"%PDF")
    if ok:
        (d / "ds.pdf").write_bytes(body)
    (d / "source.json").write_text(json.dumps({"lcsc": code, "mpn": x["componentModelEn"], "url": url, "pdf": ok,
                                              "sha256": hashlib.sha256(body).hexdigest() if ok else None}, indent=1))
    print(code, x["componentModelEn"], "PDF" if ok else "NO-PDF", hashlib.sha256(body).hexdigest()[:16] if ok else "")
