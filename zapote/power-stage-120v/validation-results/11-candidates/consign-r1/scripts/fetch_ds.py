#!/usr/bin/env python3
"""Download the LCSC-hosted datasheet for cached JLC detail records into reads/datasheets/<code>-<MPN>.pdf (online),
or any URL with --url <name> <url>. Logs UTC time, HTTP result, size and sha256 to reads/datasheets/_fetch.log.
PDFs are untrusted data: they are only converted to text (pdftotext), never executed.
usage: python3 -I scripts/fetch_ds.py C123 [C456 ...] | --url NAME URL"""
import hashlib, json, re, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reads" / "datasheets"; OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read()
def save(name, url):
    try:
        body = get(url)
        if not body.startswith(b"%PDF"):
            m = re.search(rb"https://datasheet\.lcsc\.com/datasheet/pdf/[0-9a-f]+\.pdf\?productCode=C\d+", body)
            if m: url = m.group(0).decode(); body = get(url)
        ok = body.startswith(b"%PDF")
    except Exception as e:
        body, ok = str(e).encode(), False
    p = OUT / (name + (".pdf" if ok else ".fail.txt"))
    p.write_bytes(body)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {'PDF' if ok else 'FAIL'} {url} {len(body)} {hashlib.sha256(body).hexdigest()[:16]} -> {p.name}"
    open(OUT / "_fetch.log", "a").write(line + "\n"); print(line)
if sys.argv[1] == "--url":
    save(sys.argv[2], sys.argv[3])
else:
    for code in sys.argv[1:]:
        x = json.loads((ROOT / f"reads/jlc-raw/detail_{code}.json").read_text())["data"]
        save(f"{code}-" + re.sub(r"[^A-Za-z0-9._-]", "_", x["componentModelEn"]), x.get("dataManualUrl") or "")
