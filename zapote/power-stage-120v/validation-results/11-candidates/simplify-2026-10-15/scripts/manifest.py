#!/usr/bin/env python3
"""Datasheet manifest: URL, revision and sha256 of every download in dl/ (untrusted data, read only as text).
    python3 -I scripts/manifest.py   -> dl/MANIFEST.json"""
import hashlib, json
from pathlib import Path
DL = Path(__file__).resolve().parent.parent / "dl"
SRC = {
    "2edr8259.pdf": ("https://www.infineon.com/assets/row/public/documents/24/49/infineon-eicedriver-2edr8259h-2edrx259x-2edrx258x-datasheet-en.pdf",
                     "Infineon EiceDRIVER 2EDR8259H, 2EDRx259X, 2EDRx258X datasheet Rev. 1.7, 2026-04-09 (same file as the repo ledger, sha f49391ca00e15397)"),
    "tps3700.pdf": ("https://www.ti.com/lit/ds/symlink/tps3700.pdf", "TI SBVS187G, Feb 2012, revised Feb 2019"),
    "tps3701.pdf": ("https://www.ti.com/lit/ds/symlink/tps3701.pdf", "TI SBVS240C, Nov 2014, revised Feb 2019"),
    "tlv3201.pdf": ("https://www.ti.com/lit/ds/symlink/tlv3201.pdf", "TI SBOS561C (TLV3201, TLV3202), Mar 2012, revised May 2024"),
    "lm339b.pdf": ("https://www.ti.com/lit/ds/symlink/lm339b.pdf", "TI SLCS006Z, Oct 1979, revised May 2025"),
    "tl431.pdf": ("https://www.ti.com/lit/ds/symlink/tl431.pdf", "TI SLVS543S, Aug 2004, revised May 2024"),
    "tps7a47.pdf": ("https://www.ti.com/lit/ds/symlink/tps7a47.pdf", "TI SBVS204G, Jun 2012, revised May 2026"),
}
out = {}
for f, (url, rev) in SRC.items():
    p = DL / f
    out[f] = {"url": url, "revision": rev, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "fetched": "2026-10-15"}
json.dump(out, open(DL / "MANIFEST.json", "w"), indent=1)
for f, v in out.items():
    print(f, v["sha256"][:16], v["revision"])
