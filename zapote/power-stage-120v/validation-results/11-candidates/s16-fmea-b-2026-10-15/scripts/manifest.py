#!/usr/bin/env python3
"""Write dl/MANIFEST.json: URL, document id and revision, sha256 of every downloaded file (fetched 2026-10-15).
Downloads are untrusted data; this script only hashes them.     python3 -I scripts/manifest.py"""
import hashlib, json, os, sys
sys.dont_write_bytecode = True
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DL = os.path.join(ROOT, "dl")
DOCS = {
    "tps3701/tps3701.pdf": ("https://www.ti.com/lit/ds/symlink/tps3701.pdf", "TI SBVS240C, Nov 2014, revised Feb 2019", "datasheet"),
    "tps3700/tps3700.pdf": ("https://www.ti.com/lit/ds/symlink/tps3700.pdf", "TI SBVS187G", "datasheet (pin-compatible sibling)"),
    "tl431/tl431.pdf": ("https://www.ti.com/lit/ds/symlink/tl431.pdf", "TI SLVS543S, Aug 2004, revised May 2024", "datasheet"),
    "lm339b/lm339b.pdf": ("https://www.ti.com/lit/ds/symlink/lm339b.pdf", "TI SLCS006Z, Oct 1979, revised May 2025", "datasheet"),
    "tps709/tps709.pdf": ("https://www.ti.com/lit/ds/symlink/tps709.pdf", "TI SBVS186H, Mar 2012, revised Jul 2021", "datasheet (local 5 V LDO, sliver question)"),
    "tps7a47/tps7a47.pdf": ("https://www.ti.com/lit/ds/symlink/tps7a47.pdf", "TI SBVS204G, Jun 2012, revised May 2026", "datasheet (ANY-OUT pins, test-hook question)"),
    "snva914/snva914.pdf": ("https://www.ti.com/lit/pdf/snva914 (-> /lit/fs/snva914/snva914.pdf)", "TI SNVA914 'TL43x-Q1 Functional Safety FIT Rate and Failure Mode Distribution' (no revision letter printed; PDF created 2021-12-03)", "TI functional-safety FIT/FMD (TL431-Q1 / TL432-Q1)"),
    "slca004/slca004.pdf": ("https://www.ti.com/lit/pdf/slca004 (-> /lit/fs/slca004/slca004.pdf)", "TI SLCA004, Feb 2023", "TI functional-safety FIT/FMD/pin FMA (LM2901, LM2901B, LM2901V, LM2901AV; SOIC-14 / TSSOP-14)"),
    "slvaem2a/slvaem2a.pdf": ("https://www.ti.com/lit/pdf/slvaem2a (-> /lit/fs/slvaem2a/slvaem2a.pdf)", "TI SLVAEM2A, Jan 2020, revised Mar 2021", "TI functional-safety FIT/FMD/pin FMA (TPS3700-Q1, DDC and DSE)"),
    "sffs074/sffs074.pdf": ("https://www.ti.com/lit/pdf/sffs074 (-> /lit/fs/sffs074/sffs074.pdf)", "TI SFFS074, Mar 2021", "TI functional-safety FIT/FMD/pin FMA (TPS3702, DDC)"),
    "sbva070/sbva070.pdf": ("https://www.ti.com/lit/pdf/sbva070 (-> /lit/fs/sbva070a/sbva070a.pdf)", "TI SBVA070A, Dec 2019, revised Mar 2021", "TI functional-safety FIT/FMD/pin FMA (TPS3702-Q1, DDC)"),
    "sffs944/sffs944.pdf": ("https://www.ti.com/lit/pdf/sffs944 (-> /lit/fs/sffs944/sffs944.pdf)", "TI SFFS944, Jul 2024", "TI functional-safety FIT/FMD/pin FMA (TPS3703, DSE)"),
    "ti-estimator/est_TPS3701DDCR.html": ("https://www.ti.com/quality/docs/estimator.tsp?opn=TPS3701DDCR&cpn=&partNumber=TPS3701DDCR", "TI MTBF/FIT estimator page as served 2026-10-15", "TI reliability (HTOL-based) FIT"),
    "ti-estimator/est_TL431AIDBZR.html": ("https://www.ti.com/quality/docs/estimator.tsp?opn=TL431AIDBZR&cpn=&partNumber=TL431AIDBZR", "as above", "TI reliability (HTOL-based) FIT"),
    "ti-estimator/est_TL431BIDBZR.html": ("https://www.ti.com/quality/docs/estimator.tsp?opn=TL431BIDBZR&cpn=&partNumber=TL431BIDBZR", "as above", "TI reliability (HTOL-based) FIT"),
    "ti-estimator/est_LM339BIDR.html": ("https://www.ti.com/quality/docs/estimator.tsp?opn=LM339BIDR&cpn=&partNumber=LM339BIDR", "as above", "TI reliability (HTOL-based) FIT"),
}


def main():
    out = {}
    for rel, (url, rev, kind) in sorted(DOCS.items()):
        path = os.path.join(DL, rel)
        h = hashlib.sha256(open(path, "rb").read()).hexdigest()
        out[rel] = {"url": url, "revision": rev, "kind": kind, "sha256": h, "bytes": os.path.getsize(path),
                    "fetched": "2026-10-15"}
    json.dump(out, open(os.path.join(DL, "MANIFEST.json"), "w"), indent=1, sort_keys=True)
    print(f"{len(out)} files hashed -> dl/MANIFEST.json")


if __name__ == "__main__":
    main()
