#!/usr/bin/env python3
"""Datasheet manifest: URL, revision, sha256 of every PDF in ../dl (untrusted data).  -> dl/MANIFEST.json"""
import hashlib, json
from pathlib import Path
DL = Path(__file__).resolve().parent.parent / "dl"
SRC = {
 "tl431.pdf": ("https://www.ti.com/lit/ds/symlink/tl431.pdf", "TI SLVS543S, Aug 2004, revised May 2024"),
 "lm339b.pdf": ("https://www.ti.com/lit/ds/symlink/lm339b.pdf", "TI SLCS006Z, Oct 1979, revised May 2025"),
 "tlvh431.pdf": ("https://www.ti.com/lit/ds/symlink/tlvh431.pdf", "TI SLVS555N, Nov 2004, revised Jun 2024"),
 "tps7a47.pdf": ("https://www.ti.com/lit/ds/symlink/tps7a47.pdf", "TI SBVS204G, Jun 2012, revised May 2026"),
 "tps3701.pdf": ("https://www.ti.com/lit/ds/symlink/tps3701.pdf", "TI SBVS240C, Nov 2014, revised Feb 2019"),
 "lm4040.pdf": ("https://www.ti.com/lit/ds/symlink/lm4040.pdf", "TI SLOS456Q, Jan 2005, revised Apr 2026"),
 "R24C2T25_R.pdf": ("https://recom-power.com/pdf/Econoline/R24C2T25_R.pdf", "RECOM R24C2T25/R Rev. 1-2024 (= ledger sha 2e8133d2)"),
 "2edr8259.pdf": ("https://www.infineon.com/assets/row/public/documents/24/49/infineon-eicedriver-2edr8259h-2edrx259x-2edrx258x-datasheet-en.pdf",
                  "Infineon 2EDR8259H/2EDRx259X/2EDRx258X Rev. 1.7, 2026-04-09 (= ledger sha f49391ca)"),
 "yageo_rt.pdf": ("https://datasheet.lcsc.com/datasheet/pdf/46d7760c582640714d605308a25a220a.pdf?productCode=C95204",
                  "Yageo RT series product specification V.16, May 06 2025 (LCSC copy for C95204)"),
 "viking_arg.pdf": ("https://datasheet.lcsc.com/datasheet/pdf/ec3e308e963624b453a77b63220f4bbf.pdf?productCode=C1509631",
                    "Viking Tech ARG series REV. A3, 19-Jul-2016 (LCSC copy for C1509631)"),
 "vishay_tnpw.pdf": ("https://www.vishay.com/docs/28758/tnpw_e3.pdf", "Vishay TNPW e3, document 28758, revision 10-Apr-2026"),
}
out = {}
for f, (u, rev) in SRC.items():
    p = DL / f
    out[f] = {"url": u, "revision": rev, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "fetched": "2026-10-15"}
out["ipw65r018cfd7.pdf (repo copy, not downloaded)"] = {
    "path": "validation-results/03-loss-thermal-budget/round3/sources/ipw65r018cfd7.pdf", "revision": "Infineon Rev.2.0, 2021-04-19",
    "sha256": "c364050a04a434bd173da6486fd51f4baf540ee9e4e1ebbe07aed57e279943f2"}
json.dump(out, open(DL / "MANIFEST.json", "w"), indent=1)
for k, v in out.items():
    print(f"{k:28s} {v['sha256'][:16]}  {v['revision']}")
