#!/usr/bin/env python3
"""Download candidate datasheets into dl/<key>/ (one empty directory per file; untrusted data, never executed).

    python3 -I scripts/fetch_datasheets.py            # every JLC detail record in snapshots/jlc-raw + EXTRA below
    python3 -I scripts/fetch_datasheets.py KEY URL    # one extra file

Follows LCSC's script / HTML redirect pages to the PDF. Prints key, bytes, sha256 (also written to dl/SHA256SUMS).
"""
import glob
import hashlib
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DL = os.path.join(ROOT, "dl")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Safari/605.1.15"}
EXTRA = {}


def get(url, depth=0):
    b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
    if b[:4] == b"%PDF" or depth > 3:
        return b
    t = b[:200000].decode("utf-8", "replace")
    m = re.search(r"location\.href='([^']+)'", t) or re.search(r'"(https://[^"]+\.pdf[^"]*)"', t) \
        or re.search(r"(https://datasheet\.lcsc\.com/[^\"' ]+\.pdf[^\"' ]*)", t)
    if not m:
        return b
    return get(m.group(1).replace("\\u0026", "&"), depth + 1)


def save(key, url):
    d = os.path.join(DL, key)
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, key + ".pdf")
    if os.path.exists(out) and open(out, "rb").read(4) == b"%PDF":
        b = open(out, "rb").read()
    else:
        b = get(url)
        open(out, "wb").write(b)
    h = hashlib.sha256(b).hexdigest()
    print(key, len(b), h[:16], "PDF" if b[:4] == b"%PDF" else "NOT-PDF", url)
    return key, h, url, b[:4] == b"%PDF"


def main():
    todo = {}
    if len(sys.argv) == 3:
        todo[sys.argv[1]] = sys.argv[2]
    else:
        for f in sorted(glob.glob(os.path.join(ROOT, "snapshots/jlc-raw/detail_*.json"))):
            d = json.load(open(f)).get("data") or {}
            if d.get("dataManualUrl"):
                todo[d["componentCode"] + "_" + re.sub(r"[^A-Za-z0-9.-]", "-", d.get("componentModelEn") or "")] = d["dataManualUrl"]
        todo.update(EXTRA)
    sums = os.path.join(DL, "SHA256SUMS")
    have = {}
    if os.path.exists(sums):
        for line in open(sums):
            p = line.rstrip("\n").split("  ", 2)
            if len(p) == 3:
                have[p[1]] = line
    for k, u in todo.items():
        try:
            key, h, url, ok = save(k, u)
            if ok:
                have[key] = f"{h}  {key}  {url}\n"
        except Exception as e:  # noqa: BLE001
            print(k, "FAIL", e)
    os.makedirs(DL, exist_ok=True)
    open(sums, "w").write("".join(have[k] for k in sorted(have)))


if __name__ == "__main__":
    main()
