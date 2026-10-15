#!/usr/bin/env python3
"""Task 5: UL scope of the s35 / s38 stack (identical native-21/stackup.json; 4 layers, 2 oz inner = 61 um finished) from public pages only.

    python3 -I laminate_scope.py   -> results/laminate_scope.json   (reads dl/ only; every quote asserted)

Sources (dl/, fetched 2026-10-15 without a login):
  jlc-pages/../thermal-ratings ul.html copy is not reused; this study fetched:
  dl/jlc-cert/certifications.html  https://jlcpcb.com/certifications  (Certifications Center; links the PDFs below)
  dl/jlc-ul-cert/ul-certificate.pdf  https://rs.jlcpcb.com/static/file/ul-certificate.pdf (UL Notice of Completion, 2021-08-27)
  dl/jlc-kb6165f/kb-6165f-datasheet.pdf, dl/jlc-kb6164/kb-6164-datasheet.pdf (JLC-hosted Kingboard TDS)
  dl/jlc-pages/copper-weight.html  https://jlcpcb.com/help/article/jlcpcb-copper-weight
  dl/jlc-pages/productiq.html      https://productiq.ulprospector.com/en/search?q=E479892 -> HTTP 403 (login wall)
  dl/kb-ul/ul.pdf  Kingboard UL QMTS2 reprint, file E123995 (the audit's copy, kblaminates.com; public)
  JLC UL article (https://jlcpcb.com/help/article/ul-certification): the audit's fetch, text re-read here from
  ../thermal-ratings/dl/jlc-ul/ul.html is NOT used; the same page is re-fetched to dl/jlc-ul-page/ul.html.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DL, RESULTS, UNIT  # noqa: E402


def text_of(p: Path) -> str:
    s = p.read_text(errors="ignore")
    if p.suffix == ".html":
        s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
        s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s)


def need(t, quote, src):
    assert quote in t, f"{src}: quote not found: {quote!r}"
    return {"source": src, "quote": quote}


def main():
    ev = []
    ul_page = text_of(DL / "jlc-ul-page/ul.html")
    ev.append(need(ul_page, "JLCPCB's UL identification number is E479892", "jlcpcb.com/help/article/ul-certification"))
    ev.append(need(ul_page, "JLC-4 KB-6164 TG135 S1141 TG140 KB-6165 TG155 S1000H TG155 Shengyi S1000-2M - TG170 FR-4 Multi-layer (4-32 layers)",
                   "jlcpcb.com/help/article/ul-certification (type table)"))
    cw = text_of(DL / "jlc-pages/copper-weight.html")
    ev.append(need(cw, "Inner layer 0.5oz (default), 1oz, 2oz Availability depends on total layers and overall thickness",
                   "jlcpcb.com/help/article/jlcpcb-copper-weight"))
    cert = text_of(DL / "jlc-ul-cert/ul-certificate.txt")
    ev.append(need(cert, "File E479892, Volume 1", "rs.jlcpcb.com/static/file/ul-certificate.pdf p.1"))
    ev.append(need(cert, "to type JLC-1. 3.Add CUL recognition to type JLC-1 and JLC-2.", "ul-certificate.pdf p.1 (scope: JLC-1/JLC-2 only)"))
    certs = (DL / "jlc-cert/certifications.html").read_text(errors="ignore")
    for f in ("kb-6164-datasheet.pdf", "kb-6165f-datasheet.pdf", "s1000-2m-tg170-datasheet.pdf", "ul-certificate.pdf"):
        ev.append(need(certs, f, "jlcpcb.com/certifications (hosted file list)"))
    ev.append(need(ul_page, "JLC-1 Nan Ya NP-140F Nan Ya NP-155F FR-4 Multi-layer (4-32 layers)", "jlcpcb.com/help/article/ul-certification (type table)"))
    npr = text_of(DL / "jlc-np155f/nan-ya-np-155f-test-report.txt")
    ev.append(need(npr, "LAMINATE (UL E98983)", "rs.jlcpcb.com/static/file/nan-ya-np-155f-test-report.pdf p.1"))
    stack = json.loads((UNIT / "native-21/stackup.json").read_text())
    assert "Nan Ya NP-155F" in stack["status"] and "JLCPCB may substitute KB or Shengyi" in stack["status"]
    ev.append({"source": "native-21/stackup.json status", "quote": "The laminate is Nan Ya NP-155F ... JLCPCB may substitute KB or Shengyi"})
    kb65f = text_of(DL / "jlc-kb6165f/kb-6165f-datasheet.txt")
    ev.append(need(kb65f, "Laminate: KB-6165F", "rs.jlcpcb.com/static/file/kb-6165f-datasheet.pdf p.1"))
    ev.append(need(kb65f, "UL: E123995", "kb-6165f-datasheet.pdf p.1"))
    ul = (DL / "kb-ul/ul.txt").read_text()
    pages = ul.split("\f")

    def row(prefix):
        for i, p in enumerate(pages, 1):
            for ln in p.splitlines():
                if ln.strip().startswith(prefix):
                    return i, re.sub(r"\s+", " ", ln.strip())
        raise AssertionError(prefix)
    ml = {}
    for name, prefix in (("KB-616(X) (KB-6160, KB-6164)", "KB-616(X)     KB-6160,"), ("KB-6165", "KB-6165       KB-6165       KB-6065"),
                         ("KB-6164F", "KB-6164F     KB-6164F      KB-6064F"), ("KB-6165F", "KB-6165F     KB-6165F      KB-6065F"),
                         ("KB-6167F", "KB-6167F      KB-6167F     KB-6067F")):
        pg, ln = row(prefix)
        nums = re.findall(r"(?<![\w.-])\d+(?:\.\d+)?(?![\w-])", ln.split("FR-")[1])
        # columns after ANSI: Thk, Min Ext, Max Ext, Max Int, ...
        ml[name] = {"pdf_page": pg, "row": ln, "min_thk_mm": float(nums[0]), "max_ext_um": float(nums[2]), "max_int_um": float(nums[3])}
    assert ml["KB-616(X) (KB-6160, KB-6164)"]["max_int_um"] == 35.0 and ml["KB-6165"]["max_int_um"] == 54.0
    assert all(ml[k]["max_int_um"] == 102.0 for k in ("KB-6164F", "KB-6165F", "KB-6167F"))
    piq = (DL / "jlc-pages/productiq.html").read_text(errors="ignore")
    out = {
        "question": "Does JLC's UL recognition (E479892) cover a 4-layer board with 2 oz (61 um finished) inner copper on KB-6164? Which JLC laminate option is in scope?",
        "board": "s35 / s38 (same stackup.json): 4 layers, 2 oz outer, 2 oz inner (61 um finished, native-21/stackup.json), KB-6164 / KB-6064 (JLC 'TG135' option)",
        "evidence": ev,
        "kingboard_QMTS2_multilayer_rows": ml,
        "product_iq": {"url": "https://productiq.ulprospector.com/en/search?q=E479892", "http": 403, "bytes": len(piq),
                       "note": "UL Product iQ (the only public-index source for the ZPMV2 detail of E479892 type JLC-4: "
                               "copper limits, MOT) needs a registered login; per the task rules the search stopped there. "
                               "Shengyi's QMTS2 (S1141 / S1000H / S1000-2M) detail is likewise only in Product iQ."},
        "answer": {
            "which_laminate": "The repo's stack (native-21/stackup.json) is designed to JLC041622-7628 and names Nan Ya NP-155F "
                              "(JLC type JLC-1, Nan Ya UL E98983), with KB or Shengyi as possible JLC substitutes; the audit read "
                              "KB-6164 (JLC-4). Both cases are open: NP-155F's QMTS2 multilayer row (Max Int) is not public "
                              "either (Product iQ, login). Ordering the material explicitly fixes which card and row apply.",
            "jlc_e479892_2oz_inner": "UNDETERMINED from public pages. JLC's public UL article lists type JLC-4 (FR-4 multilayer, "
                                     "4-32 layers) with KB-6164 TG135, S1141, KB-6165 TG155, S1000H and S1000-2M, but gives no copper "
                                     "limits; the public UL letter JLC hosts (2021-08-27) covers JLC-1 / JLC-2 only. The ZPMV2 "
                                     "conductor limits for JLC-4 are in UL Product iQ, which needs a login (HTTP 403).",
            "laminate_constraint": "KB-616(X) (KB-6164) multilayer Max Int 35 um and KB-6165 54 um are both below 61 um, so the "
                                   "s35 / s38 stack on either is outside Kingboard's own QMTS2 multilayer recognition. A board maker can "
                                   "still hold a ZPMV2 card beyond the laminate's ML row on its own UL 796 tests, so only JLC's "
                                   "E479892 JLC-4 detail (Product iQ, login) settles it for KB-6164.",
            "in_scope_option": "KB-6164F, KB-6165F and KB-6167F are recognised to 102 um inner (QMTS2 multilayer table). JLC "
                               "offers none of them by that name, but the datasheet JLC hosts for its 'TG155' option is KB-6165F "
                               "(UL E123995), while its UL article names 'KB-6165 TG155'. If JLC's TG155 stock is KB-6165F, the "
                               "TG155 option is the in-scope Kingboard choice (MOT still 130 C). Confirm the exact grade with JLC "
                               "before a UL-marked build; S1000-2M (TG170, also in JLC-4) needs its Shengyi QMTS2 row (login).",
        },
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "laminate_scope.json").write_text(json.dumps(out, indent=1) + "\n")
    for k, v in ml.items():
        print(f"{k:32s} p.{v['pdf_page']} Max Int {v['max_int_um']:g} um")
    print(json.dumps(out["answer"], indent=1))


if __name__ == "__main__":
    main()
