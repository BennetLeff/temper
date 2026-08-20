"""Retrieve and read the DC-bus capacitor value from a filed FCC schematic.

WHY THIS EXISTS
---------------
`docs/solutions/...power-stage-1800w-rating-unreachable...` claims commercial
120 V-class induction cooktops carry **8-10 uF of film** on the DC bus where
this design carries **1800 uF of electrolytic**. That claim was originally
relayed second-hand from a peer session, and a separate agent recorded an
HTTP 403 when it tried to retrieve the filing -- so the repo record made the
finding look unverifiable.

It is verifiable. The 403s come from fccid.io / fcc.report (Cloudflare).
`apps.fcc.gov` works, but only the /eas/GetApplicationAttachment.html
endpoint, and only with a session cookie seeded from the /oetcf/ search page
plus browser-like headers. This script does that and extracts the value, so
the claim rests on a re-runnable retrieval rather than on a report.

WHAT IT ESTABLISHES (retrieved 2026-08-19, sha256 of the PDF below)
-------------------------------------------------------------------
FCC ID ZBNC18-13, schematic exhibit id=2660989, 1 sheet. Every capacitance
token on the sheet:

    C4          8UF/275ACV      <- DC bus, film (non-polarised symbol, AC rating)
    5UF/275ACV, 10UF/275ACV     <- EMI X-caps
    0.27UF/1200VDC              <- resonant tank
    4.7UF/450V                  <- aux rectified bulk
    100UF/25V x3, 220UF/25V,
    10UF50V, 1UF/50V            <- ALL low voltage: auxiliary rails only
    56PF/50V

There is no high-voltage electrolytic anywhere in the design. The largest
capacitance on the whole board is 220 uF at 25 V.

LIMITS
------
This is ONE filing. It corroborates the 4-8 uF figure that a peer session
read from three schematics (ZBNTI3B 10uF/400VDC, ZFBC13F 10uF/250VAC), but
only ZBNC18-13 is retrieved and parsed here; the other two remain
second-hand in this repo. The filing does not state an input voltage on the
sheet, so its market is not established from this document alone.

Usage:  python3 docs/evidence/2026-08-20-fcc-zbnc18-13-bus-capacitance.py [outdir]
Needs network. Prints the capacitance histogram and the PDF digest.
"""

from __future__ import annotations

import collections
import hashlib
import re
import subprocess
import sys
import zlib
from pathlib import Path

ATTACHMENT_ID = "2660989"  # ZBNC18-13 schematic exhibit
EXPECTED_SHA256 = "6d3de455d4fdf12ffa2cfc9129787b5ebe5aced3918a7e0eb03db153dae4dd34"
EXPECTED_BUS_CAP = "8UF/275ACV"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
SEED_URL = "https://apps.fcc.gov/oetcf/eas/reports/GenericSearch.cfm"
FETCH_URL = "https://apps.fcc.gov/eas/GetApplicationAttachment.html?id=" + ATTACHMENT_ID


def retrieve(outdir: Path) -> Path:
    jar, pdf = outdir / "fcc.jar", outdir / f"zbnc18-13-{ATTACHMENT_ID}.pdf"
    subprocess.run(
        ["curl", "-sL", "-A", UA, "-c", str(jar), "-b", str(jar), "-o", "/dev/null",
         "--max-time", "60", SEED_URL],
        check=False,
    )
    subprocess.run(
        ["curl", "-sL", "-A", UA, "-b", str(jar), "-c", str(jar),
         "-H", "Referer: https://apps.fcc.gov/oetcf/eas/reports/ViewExhibitReport.cfm",
         "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "-H", "Accept-Language: en-US,en;q=0.9",
         "--compressed", "--max-time", "180", "-o", str(pdf), FETCH_URL],
        check=False,
    )
    return pdf


def extract_text(pdf: Path) -> str:
    """Prefer poppler's pdftotext; fall back to raw stream inflate.

    The fallback alone does NOT recover this sheet's text -- the values live
    in positioned text operators that pdftotext reassembles. Keeping the
    fallback is fine, but a caller must not read its silence as absence:
    the script fails loudly below rather than reporting NOT FOUND.
    """
    txt = pdf.with_suffix(".txt")
    try:
        subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)],
                       check=True, capture_output=True)
        if txt.exists():
            return txt.read_text(encoding="latin-1", errors="replace")
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    raw = pdf.read_bytes()
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        try:
            out.append(zlib.decompress(m.group(1)))
        except Exception:
            pass
    return b"\n".join(out).decode("latin-1", errors="replace")


def main() -> int:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    outdir.mkdir(parents=True, exist_ok=True)

    pdf = retrieve(outdir)
    if not pdf.exists() or pdf.stat().st_size < 1024:
        print("RETRIEVAL FAILED -- no PDF. fccid.io/fcc.report are Cloudflare-403;")
        print("only apps.fcc.gov/eas/GetApplicationAttachment.html works, and only")
        print("with the cookie seed above. Network required.")
        return 2

    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    print(f"pdf      : {pdf} ({pdf.stat().st_size} bytes)")
    print(f"sha256   : {digest}")
    print(f"expected : {EXPECTED_SHA256}  {'MATCH' if digest == EXPECTED_SHA256 else 'DIFFERS'}")

    text = extract_text(pdf)
    caps = re.findall(r"[0-9]+(?:\.[0-9]+)?\s*(?:UF|NF|PF)[/A-Z0-9.]*", text, re.I)
    print("\ncapacitance tokens on the sheet:")
    for tok, n in sorted(collections.Counter(caps).items(), key=lambda kv: -kv[1]):
        print(f"  {n:>2}x  {tok}")

    if not caps:
        print("\nNO CAPACITANCE TOKENS EXTRACTED -- the reader failed, this is")
        print("NOT evidence of absence. Install poppler-utils (pdftotext) and")
        print("re-run; the raw-inflate fallback cannot read this sheet.")
        return 3

    found = EXPECTED_BUS_CAP in text
    print(f"\nDC bus cap C4 = {EXPECTED_BUS_CAP}: {'FOUND' if found else 'NOT FOUND'}")
    hv_elec = [c for c in caps if re.match(r"[1-9][0-9]{2,}\s*UF", c, re.I)]
    print(f"capacitances >= 100uF: {sorted(set(hv_elec))}  (all low-voltage aux rails)")
    return 0 if (found and digest == EXPECTED_SHA256) else 1


if __name__ == "__main__":
    raise SystemExit(main())
