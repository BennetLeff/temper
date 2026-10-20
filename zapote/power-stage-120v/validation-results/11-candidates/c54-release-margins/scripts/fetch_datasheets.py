#!/usr/bin/env python3
"""Fetch the datasheets this study quotes (online; PDFs are not committed, the sha256 prefixes are).

    python3 -I scripts/fetch_datasheets.py OUT_DIR [NAME ...]

Each PDF lands at OUT_DIR/<NAME>/ds.pdf; the script prints NAME, size and sha256[:16] so a re-fetch can be compared
with the prefixes quoted in README.md / results/*.json. Read the PDFs with `pdftotext -layout` in OUT_DIR (keep OUT_DIR
outside this folder: downloaded files are untrusted data)."""
import hashlib
import os
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/129.0.0.0 Safari/537.36", "Accept": "application/pdf,*/*"}
JS_REDIRECT = re.compile(rb"location\.href\s*=\s*'([^']+)'")


def fetch(url, hops=3):
    """GET url; follow LCSC's one-line JavaScript redirect (wmsc.lcsc.com -> datasheet.lcsc.com) up to `hops` times."""
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        b = r.read()
    m = JS_REDIRECT.search(b[:2000])
    if b[:4] != b"%PDF" and m and hops:
        return fetch(m.group(1).decode(), hops - 1)
    return b

LCSC = "https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/"
SOURCES = {
    # R_on candidates (2512, 68 ohm)
    "25121WF680JT4E": "https://datasheet.lcsc.com/datasheet/pdf/0a975aaa49b7c97f38a963127be4a823.pdf?productCode=C50371",
    "PS122WF680JT4E": LCSC + "2304140030_UNI-ROYAL-Uniroyal-Elec-PS122WF680JT4E_C2793964.pdf",
    "AS122WJ0680T4E": LCSC + "2304140030_UNI-ROYAL-Uniroyal-Elec-AS122WJ0680T4E_C2770543.pdf",
    "RC2512JK-7W68RL": LCSC + "2210202330_YAGEO-RC2512JK-7W68RL_C876271.pdf",
    "CRH2512J68R0E04Z": LCSC + "2304140030_Ever-Ohms-Tech-CRH2512J68R0E04Z_C175435.pdf",
    # split-bleed candidates (0603, 4.99 k)
    "ERJ-PA3F4991V": LCSC + "2404091153_PANASONIC-ERJ-PA3F4991V_C4036134.pdf",
    "RCS06034K99FKEA": LCSC + "2212231908_Vishay-Intertech-RCS06034K99FKEA_C4104448.pdf",
    # C126-C129 candidates (6.3 mm can, CP_Elec_6.3x5.9 pads)
    "6SVPC220MV": LCSC + "2304140030_PANASONIC-6SVPC220MV_C128504.pdf",
    "16SVPK220M": LCSC + "2205061630_PANASONIC-16SVPK220M_C542293.pdf",
    "MAL228697401E3": "https://www.vishay.com/docs/28592/286cpnx.pdf",
}


def main():
    out = sys.argv[1]
    names = sys.argv[2:] or list(SOURCES)
    for n in names:
        d = os.path.join(out, n)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "ds.pdf")
        if not os.path.exists(p) or open(p, "rb").read(4) != b"%PDF":
            with open(p, "wb") as f:
                f.write(fetch(SOURCES[n]))
        b = open(p, "rb").read()
        print(f"{n}\t{len(b)}\t{hashlib.sha256(b).hexdigest()[:16]}\t{'PDF' if b[:4] == b'%PDF' else 'NOT A PDF'}")


if __name__ == "__main__":
    main()
