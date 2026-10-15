#!/usr/bin/env python3
"""Temperature ratings for the B3 hot spots, each with its primary source, and a verifier that re-reads the downloaded
documents (../dl/<doc>/, untracked, never committed) and asserts every quoted string is on the cited page.

    python3 -I ratings.py [--dl ../dl]  -> ../results/ratings.json   (exit 1 if a quote is not found)

Run with -I: it reads downloaded (untrusted) PDFs, through the system `pdftotext` only.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

JOB = Path(__file__).resolve().parents[1]

DOCS = {
    "kb_ul": dict(file="kb-ul/ul.pdf",
                  url="https://www.kblaminates.com/upload/portal/20260224/202602241024184756.pdf (linked from kblaminates.com/list/28.html)",
                  revision="UL Product iQ reprint, QMTS2, file E123995, Kingboard Laminates Holdings; 'Last Updated on 2026-02-20'"),
    "kb_tds": dict(file="kb-tds/tds.pdf", url="https://www.kblaminates.com/upload/ueditor/20250313/KB-6164,KB-6064.pdf",
                   revision="Kingboard Technical Information KB-6164 / KB-6064 (PDF of 2025-03-13), 1 p."),
    "recom": dict(file="recom/R24C2T25_R.pdf", url="https://recom-power.com/pdf/Econoline/R24C2T25_R.pdf",
                  revision="RECOM R24C2T25/R Series, Rev. 1-2024 (16 pp.)"),
    "irm20": dict(file="irm20/IRM-20-SPEC.pdf", url="https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF",
                  revision="Mean Well IRM-20-SPEC 2025-11-21 (3 pp.)"),
    "tdk_l1": dict(file="tdk-l1/b82726s22x3.pdf", url="https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s22x3.pdf",
                   revision="TDK B82726S22*3A020, PDF created 2026-05-21 (9 pp.)"),
    "bourns": dict(file="bourns-r5/css2h.pdf",
                   url="https://sy-dep-epc-lpc.web.cern.ch/components/datasheets/epc-lpc%20(converters)/CSS2H-2512R-Shunt-Bourns.pdf",
                   revision="Bourns CSS2H-2512, REV. 06/17/20 (CERN-hosted copy; same copy the ledger cites)"),
    "ti_tps7a47": dict(file="ti-tps7a47/tps7a47.pdf", url="https://www.ti.com/lit/ds/symlink/tps7a47.pdf",
                       revision="TI SBVS204G, June 2012, revised May 2026"),
    "tdk_film": dict(file="tdk-film/MKP_B32651_658.pdf",
                     url="https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf",
                     revision="TDK B3265*A/G/J/T film capacitors, June 2026 (81 pp.)"),
}

# Every rating: the quantity it limits, the model quantity it is compared with, and the verbatim evidence.
RATINGS = [
    # ---------------------------------------------------------------- laminate (KB-6164 core / KB-6064 prepreg)
    dict(id="laminate_MOT", refs=["board"], limit_c=130.0, applies_to="board copper / laminate, continuous",
         compare="board 1 mm-block copper peak (and FET-row copper)",
         note="UL QMTS2 'Max Oper Temp' of KB-616(X) (X = 0 or 4: KB-6160 / KB-6164 with KB-6060 / KB-6064 prepreg) "
              "for MULTILAYER PWBs. The same row caps the internal conductor at 35 um (Max Int); the s32 stack has "
              "2 oz (61 um finished) inner layers - see the write-up. A finished PWB's own MOT (JLC's ZPMV2 file "
              "E479892, board type JLC-4) is not published; it cannot exceed the laminate's.",
         doc="kb_ul", quotes=[(6, "Oper"), (7, "KB-616(X)     KB-6160,    KB-6060,     FR-    0.38       17    102      35    50.8     V-0     130"),
                              (7, "KB-6164     KB-6064")]),
    dict(id="laminate_RTI", refs=["board"], limit_c=130.0, applies_to="laminate RTI electrical (mech 140 C at >= 0.63 mm, 130 C at 0.38 mm)",
         compare="board 1 mm-block copper peak",
         note="KB-616(X) industrial-laminate row: RTI Elec 130 / Mech 130 at 0.38 mm, 130 / 140 at 0.63 and 1.40 mm.",
         doc="kb_ul", quotes=[(3, "KB-616(X)                  FR-4.0          YL             0.38   V-0   130   130"),
                              (3, "1.40   V-0   130   140   0   2   4   3")]),
    dict(id="laminate_Tg", refs=["board"], limit_c=140.0, applies_to="glass transition (DSC) - a process/CTE marker, NOT an operating rating",
         compare="information only (DECISIONS 21 compares FET-row copper to 'laminate Tg 150': wrong quantity and wrong value for KB-6164)",
         note="Tg 140 C by DSC; DECISIONS 21's 'Tg 150' is neither KB-6164's Tg nor a continuous-use limit.",
         doc="kb_tds", quotes=[(1, "140"), (1, "Glass Transition (Tg)")]),
    dict(id="laminate_higher_Tg_MOT", refs=["board"], limit_c=130.0,
         applies_to="KB-6165 (JLC 'TG155') and KB-6167F (Tg 170) multilayer MOT - same 130 C",
         compare="fix ranking: a higher-Tg Kingboard grade does not raise the MOT",
         note="Only KB-6169GT (FR-15.1, 0.63 mm build) shows 150 C, and it is not on JLC's menu. Shengyi S1000H / S1000-2M "
              "UL data not retrieved here.",
         doc="kb_ul", quotes=[(6, "KB-6165       KB-6165       KB-6065      FR-     0.38         12     102      54    50.8     V-0         130"),
                              (6, "KB-6167F      KB-6167F     KB-6067F      FR-     0.38         12     102     102    50.8     V-0         130"),
                              (7, "0.63       12    102     102    50.8     V-0     150")]),
    # ---------------------------------------------------------------- U41 / U42 RECOM R24C2T25/R
    dict(id="recom_Tj", refs=["U41", "U42"], limit_c=150.0, applies_to="junction, absolute maximum",
         compare="junction node (theta_JB 25.9 K/W to PGND/VOUT- pads, theta_JC 16.6 K/W + body film to air)",
         note="Over-temperature shutdown 160 +/- 10 C latches the module off (p.8): at the low tolerance it trips at 150 C, "
              "so 150 C is also the availability limit. The 2 W knee at 82 C is an AMBIENT curve on RECOM's 50 x 50 mm "
              "EVM (p.3 note 7) - not comparable with a pad temperature.",
         doc="recom", quotes=[(2, "Junction Temperature"), (2, "+150°C"), (8, "Over Temperature Shutdown Setpoint"), (8, "160°C±10°C"),
                              (8, "junction to board"), (8, "25.9K/W"), (8, "16.6K/W"), (3, "Test with Recom 50x50mm standard EVM board with 70µm copper, double layer"),
                              (1, "1.5W at -40°C to +100°C")]),
    # ---------------------------------------------------------------- U26 TPS7A4700
    dict(id="tps7a47_Tj", refs=["U26"], limit_c=125.0, applies_to="junction, recommended operating maximum",
         compare="junction node (R_thJC(bot) 1.7 K/W to the exposed pad)",
         note="Abs-max table and recommended operating both bound TJ at 125 C; thermal-shutdown reset 150 C.",
         doc="ti_tps7a47", quotes=[(4, "Operating virtual junction, TJ"), (6, "Operating junction temperature"),
                                   (5, "Junction-to-board thermal resistance"), (5, "11.9"), (5, "1.7")]),
    # ---------------------------------------------------------------- R5 Bourns CSS2H-2512R-1L00F
    dict(id="css2h_Top", refs=["R5"], limit_c=170.0, applies_to="operating temperature maximum (element)",
         compare="element node (20 K/W element-to-terminal, derived from the p.3 curve)",
         doc="bourns", quotes=[(1, "Operating Temperature Range"), (1, "-55 to +170 °C")]),
    dict(id="css2h_terminal", refs=["R5"], limit_c=None, applies_to="terminal-temperature power derating: 5 W at 70 C -> 0 W at 170 C",
         compare="pad max cell (terminal) against 170 - 100 * P / (0.8 * 5 W) (repo G6 rule: 20 % power margin)",
         doc="bourns", quotes=[(1, "Power Rating @70 °C"), (1, "1 Terminal temperature"), (3, "Terminal Temperature")]),
    # ---------------------------------------------------------------- L1 TDK B82726S2203A020
    dict(id="b82726_Top", refs=["L1"], limit_c=125.0, applies_to="upper climatic category temperature = max component operating temperature (TA + self-heating)",
         compare="winding node (ASSUMED 5 K/W winding-to-pin)",
         note="Current rating IR 20 A is at TR = 60 C ambient with a derating curve above it (p.4-5): the ledger's 80 % rule "
              "holds to 67.7 C local air.",
         doc="tdk_l1", quotes=[(4, "Climatic category                              40/125/56"), (4, "Rated temperature TR                           +60 °C"),
                               (6, "upper climatic category temperature")]),
    # ---------------------------------------------------------------- PS1 / PS2 Mean Well IRM-20
    dict(id="irm20_ambient", refs=["PS1", "PS2"], limit_c=85.0, applies_to="AMBIENT working temperature, with load derating "
         "(OTHERS: 100 % to 50 C, 50 % at 70 C, ~5 % at 85 C; p.3 curve)",
         compare="local air at the module (not a board or case temperature): PS2 at 44 % load -> <= ~72 C; PS1 at 23 % -> <= ~79 C",
         note="No case or pin temperature rating is published, so B3's PS1/PS2 pad cells (136 / 151 C) have no rating to be "
              "compared with; the verdict is on the bay air.",
         doc="irm20", quotes=[(2, "WORKING TEMP."), (2, "-30 ~ +85℃ (Refer to \"Derating Curve\")"), (3, "Derating Curve"),
                              (3, "AMBIENT TEMPERATURE (℃)")]),
    # ---------------------------------------------------------------- film capacitors C38-C41 (B32652), bank C21-23/151/152 (B32654)
    dict(id="mkp_Top", refs=["C38", "C39", "C40", "C41", "C21", "C22", "C23", "C151", "C152"], limit_c=110.0,
         applies_to="max operating temperature Top = TA + self-heating (upper category temperature 100 C ambient; VDC derates 1.25 %/C above 85 C)",
         compare="body node (ASSUMED lead resistance; bank: board share of the loss only)",
         note="The repo used 105 C for these parts; the current TDK sheet gives Top,max 110 C and Tmax 100 C.",
         doc="tdk_film", quotes=[(2, "Max. operating temperature: 110°C"), (2, "Climatic category (IEC 60068-1): 40/100/56"),
                                 (35, "Max. operating temperature Top,max +110 °C"), (35, "Upper category temperature Tmax               +100 °C"),
                                 (35, "derating for VDC should be 1.25% / °C")]),
    # ---------------------------------------------------------------- 1206 chip resistors (gate R10/R12/R18/R20, R53/54/57/58)
    dict(id="chip1206_Top", refs=["R10", "R12", "R18", "R20", "R53", "R54", "R57", "R58", "R22", "R23", "R24", "R25", "R39",
                                  "R67", "R68", "R69", "R70"], limit_c=155.0,
         applies_to="thick-film 1206 operating maximum (vendor-typical); NOT verified against the fitted MPNs here",
         compare="element node (derived 33 K/W)", note="UniRoyal 1206W4 series is listed at -55 to +155 C on LCSC product pages; "
         "the datasheet download returned HTML. Treat as unverified.", doc=None, quotes=[]),
]


def page_text(pdf: Path, page: int) -> str:
    return subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def verify(dl: Path):
    results, ok = [], True
    for r in RATINGS:
        if not r["doc"]:
            results.append({"id": r["id"], "verified": "no source document (unverified)"})
            continue
        pdf = dl / DOCS[r["doc"]]["file"]
        found = []
        for page, q in r["quotes"]:
            hit = norm(q) in norm(page_text(pdf, page)) if pdf.exists() else False
            found.append({"page": page, "quote": q, "found": hit})
            ok &= hit
        results.append({"id": r["id"], "verified": all(f["found"] for f in found), "quotes": found})
    return ok, results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dl", default=str(JOB / "dl"))
    ap.add_argument("--out", default=str(JOB / "results/ratings.json"))
    a = ap.parse_args()
    ok, res = verify(Path(a.dl))
    out = {"documents": DOCS, "ratings": RATINGS, "verification": res, "all_quotes_found": ok}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    for v in res:
        bad = [q for q in v.get("quotes", []) if not q["found"]]
        print(f"{v['id']:24s} {v['verified']}" + (f"  MISSING {bad}" if bad else ""))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
