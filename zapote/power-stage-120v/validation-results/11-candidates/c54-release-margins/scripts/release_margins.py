#!/usr/bin/env python3
"""c54: release-case thermal margins of the thinnest BOM lines, and what same-footprint swaps buy (native-21 s53).

    python3 -I scripts/release_margins.py --extract   # (once) copy the B3 run-file values this study uses into
                                                      # results/b3-inputs-s53.json; needs the gitignored b3-ratings/runs/
    python3 -I scripts/release_margins.py             # everything else, from committed files only

Committed inputs: results/b3-inputs-s53.json (the extract, with each run file's sha256), b3-ratings/margins.json (the
s53 chain output, board 82af7bd9), and b3-ratings/b3_ratings_gate.py (imported for est(), K_MESH and the split-bleed
operating point, so the estimator is the gate's own). Outputs: results/margins-c54.json and results/margins-c54.md.

Steps
 1. Reproduce the scorecard's b3_release_margin_K = +1.3 K (R10, c17.5_h10): est = Q(0.25) + 3 |Q(0.25) - Q(0.5)| +
    (bay - 50) on R10's pad-copper maximum, limit = 155 - 85 P / (0.8 x 1 W), and assert both equal margins.json.
 2. Re-rate R10/R12/R18/R20 with each same-footprint candidate on the SAME basis (the candidate's own derating line,
    abscissa read at the B3 terminal, 80 % power rule). The terminal and element estimates are unchanged: same 68 ohm
    (same charge split, 0.217 W), same 6.35 x 3.20 x 0.55 mm body and terminals (so the same thermal_body chip2512
    r_pad 37.6 K/W, which is derived from those dimensions, not from the power rating).
 3. Split bleed R71/R72/R74/R75 (+R131, same BOM line): pad-copper probe estimate vs the 0603 derating line at
    P = (V_PN - V_SPLIT)^2 / 4.99 k, for the fitted 0603WAF4991T5E and the candidates.
 4. C126-C129 (pad = local-ambient proxy vs category temperature) and U26 (B3 TJ row) with the options found.
 5. The release margin after the recommended swaps = the worst gated release row of margins.json with the R_on
    terminal rows re-rated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
PS = HERE.parents[3]
B3R = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings"
sys.path.insert(0, str(B3R))
import b3_ratings_gate as gate  # noqa: E402  (est, K_MESH, TAMB_MODEL_C, V_PN, V_SPLIT, BASIS)

EXTRACT = STUDY / "results/b3-inputs-s53.json"
CASES = {"c17.5_h10": 61.0, "c22_h10": 55.0, "c28_h10": 55.0}
RELEASE = "c17.5_h10"
R_ON = ("R10", "R12", "R18", "R20")
BLEED = ("R71", "R72", "R74", "R75", "R131")          # R131 shares the 0603WAF4991T5E line (hb_rc / hb_tx, no bleed)
BLEED_POWERED = ("R71", "R72", "R74", "R75")          # p -> src split bleed (b3_ratings_gate MONITOR_SELF['tlvh431'])
CAPS = ("C126", "C127", "C128", "C129")
RULE = 0.8                                            # G6 / DECISIONS 46: dissipation <= 80 % of the curve-derated power

# ---- datasheet lines: (rated W, knee C, zero-power C, abscissa, source). Linear from (knee, 100 %) to (zero, 0 %).
R_ON_PARTS = {
    "25121WF680JT4E": dict(w=1.0, knee=70.0, zero=155.0, axis="ambient", tol="1 %", tcr=100, vmax=200.0, t_max=155.0,
                           lcsc="C50371",
                           src="UniRoyal Thick Film Chip Resistors data sheet V.3 (Feb.12,2019): p.4/9 table 6 2512 1 W at "
                               "70 C; p.5/9 section 7 -55..+155 C, 200 V; p.5/9 section 9 figure 1 (100 % at 70 C to 0 % at "
                               "155 C, ambient); p.4/9 dims L 6.35+-0.10 W 3.20+-0.20 H 0.55+-0.10 A 0.60+-0.25 B 0.50+-0.20 "
                               "(sha256 11cd644d5d8a34a6)"),
    "PS122WF680JT4E": dict(w=2.0, knee=70.0, zero=155.0, axis="ambient", tol="1 %", tcr=100, vmax=500.0, t_max=155.0,
                           lcsc="C2793964", pulse_w_1us=2000.0,
                           src="UniRoyal product catalogue 2023~2024 (LCSC copy, 200 pp, sha256 ef35c54db5ef3b90), "
                               "'High-Precision Anti-Surge Thick Film Chip Resistors - PS' p.23: PS12 2512 power rating 2W; "
                               "Derating Curve 100 % at 70 C to 0 % at 155 C vs 'Ambient temperature'; operating -55~+155 C; "
                               "max working 500 V, max overload 1000 V; dims L 6.35+-0.10 W 3.20+-0.20 H 0.55+-0.10 "
                               "A 0.60+-0.25 B 0.50+-0.20 (B 1.80 only as a special order); 'Curve of Pulse Duration' PS12 "
                               "one-pulse limiting power ~2000 W flat from 1 us to 10 us (read from the plot); AEC-Q200; "
                               "p.24 TCR +-100 ppm/C, ordering code PS12 2W F (1 %)"),
    "RC2512JK-7W68RL": dict(w=2.0, knee=70.0, zero=155.0, axis="ambient", tol="5 %", tcr=200, vmax=200.0, t_max=155.0,
                            lcsc="C876271",
                            src="Yageo RC_L series V.12 (Aug 02, 2022) (sha256 e7dbabb061192522): p.2 '7W = 7 inch dia. Reel "
                                "& 2 x standard power'; p.6 table 2 RC2512 2W, -55 to 155 C, 200 V, 5 % 1 ohm-1 Mohm "
                                "+-200 ppm/C; p.7 Fig. 10-1 (100 % at 70 C to 0 % at 155 C, Tamb), 'RC2512=1W, 2W'; p.4 table "
                                "1 RC2512 L 6.35+-0.10 W 3.10+-0.15 H 0.55+-0.10 I1 0.60+-0.20 I2 0.60+-0.20"),
}
BLEED_PARTS = {
    "0603WAF4991T5E": dict(w=0.10, knee=70.0, zero=155.0, axis="ambient", lcsc="C23046",
                           src="UniRoyal Thick Film Chip Resistors data sheet V.3 (Feb.12,2019) p.4/9 0603 1/10 W at 70 C, "
                               "p.5/9 -55..155 C and section 9 derating (sha256 11cd644d5d8a34a6)"),
    # ERJ-PA3: two published lines; footnote *2 gives the terminal line priority. Gated here on the stricter of the two
    # (the ambient line read at the terminal, the project's convention), the terminal line reported.
    "ERJ-PA3F4991V": dict(w=0.25, knee=105.0, zero=155.0, axis="ambient", lcsc="C4036134",
                          terminal_line=dict(w=0.33, knee=130.0, zero=155.0),
                          src="Panasonic 'Anti-Surge Thick Film Chip Resistors ERJ P, PA, PM type' (29-Sep-23; LCSC copy "
                              "sha256 441511405b982033): p.2 Ratings ERJPA3 (0603) 0.25 W at rated ambient temperature "
                              "105 C, or 0.33 W at rated terminal part temperature 130 C, limiting element voltage 150 V, "
                              "+-1 % 10 ohm-1 Mohm E96, +-100 ppm/K, category -55 to +155 C, AEC-Q200 grade 1; footnote *2 "
                              "'give priority to the rated terminal part temperature'; p.3 Power derating curves (ambient: "
                              "100 % to 105 C, 0 at 155 C; terminal part: 100 % to 130 C, 0 at 155 C)"),
    "RCS06034K99FKEA": dict(w=0.25, knee=70.0, zero=155.0, axis="ambient", lcsc="C4104448",
                            src="Vishay RCS e3 doc 20065 (Rev. 04-Jul-2022; LCSC copy sha256 596179837e4c91bd) p.1 "
                                "RCS0603 P70 0.25 W, film max 155 C, -55..+155 C, 75 V; p.6 derating"),
}
CAP_PARTS = {
    "6SVPC220MV": dict(t_cat=105.0, uf=220, v=6.3, esr_mohm=15, h_max=6.0, lcsc="C128504", stock_ok=True,
                       src="Panasonic OS-CON SVPC AAB8000C256 p.1, p.2: category -55..+105 C, 2000 h at 105 C, 220 uF "
                           "6.3 V, ESR 15 mOhm, 3160 mA rms 100 kHz (ledger; sha 1c506b7474c01158)"),
    "16SVPK220M": dict(t_cat=125.0, uf=220, v=16.0, esr_mohm=22, h_max=6.0, lcsc="C542293", stock_ok=True,
                       src="Panasonic OS-CON SVPK series (LCSC copy, 7 pp, sha256 52d07f7c41c7c080): p.1 Features '125 C "
                           "1000 h', Specifications category -55 to +125 C, endurance +125 C 1000 h rated voltage applied; "
                           "p.1 Dimensions C6: D 6.3, L 5.9 (+0.1/-0.4), W = H 6.6, C 7.3, R 0.6-0.8, P 2.1 mm (= SVPC C6); "
                           "p.2 characteristics list 16SVPK220M: 220 uF, 16 V, C6, ripple 1040 mA (100 kHz, 105 < Tx <= "
                           "125 C) / 3300 mA (Tx <= 105 C), ESR 22 mOhm (100-300 kHz, 20 C), tan d 0.12, LC 704 uA"),
}
U26_TJ = (125.0, "TI SBVS204G p.4 (TPS7A47 TJ -40..125 C; the -Q1 grade TPS7A4701QRGWRQ1 is also -40..125 C)")


def sha16(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def extract():
    runs = B3R / "runs"
    out = {"board_sha256": None, "cases": {}, "note": "values copied verbatim from b3-ratings/runs/<case>_p0p25|p0p5.json "
           "(gitignored; the s53 chain's B3 BASIS solves); est() is applied in release_margins.py"}
    for c, bay in CASES.items():
        cc = {"bay_c": bay, "files": {}}
        for m in ("p0p25", "p0p5"):
            f = runs / f"{c}_{m}.json"
            r = json.loads(f.read_text())
            out["board_sha256"] = out["board_sha256"] or r["board_sha256"]
            if r["board_sha256"] != out["board_sha256"] or r["bay_c"] != bay:
                raise SystemExit(f"{f}: board {r['board_sha256'][:8]} / bay {r['bay_c']} differ")
            parts = {p["ref"]: p for p in r["parts"]}
            cc["files"][m] = {
                "sha256_16": sha16(f),
                "parts": {k: {q: parts[k][q] for q in ("mpn", "watts_into_model", "pad_max_cell_c", "tj_c", "spec")}
                          for k in R_ON + ("U26",)},
                "probes": {k: {q: r["probes"][k][q] for q in ("pad_max_cell_c", "nets")} for k in BLEED + CAPS},
            }
        out["cases"][c] = cc
    EXTRACT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {EXTRACT.relative_to(PS)} (board {out['board_sha256'][:8]})")


def line_limit(p_w, part):
    """Terminal temperature at which p_w is RULE x the curve-derated power of a linear knee -> zero line."""
    return part["zero"] - (part["zero"] - part["knee"]) * p_w / (RULE * part["w"])


def derated_w(t, part):
    return max(0.0, part["w"] * min(1.0, (part["zero"] - t) / (part["zero"] - part["knee"])))


def row(margins, case, prefix):
    hits = [r for r in margins["cases"][case] if r["item"].startswith(prefix)]
    if len(hits) != 1:
        raise SystemExit(f"margins.json {case}: {len(hits)} rows start with {prefix!r}")
    return hits[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    a = ap.parse_args()
    if a.extract:
        extract()
        return
    ex = json.loads(EXTRACT.read_text())
    margins = json.loads((B3R / "margins.json").read_text())
    boards = set(margins["board_sha256"].values())
    assert boards == {ex["board_sha256"]}, (boards, ex["board_sha256"])
    res = {"board_sha256": ex["board_sha256"], "margins_json_sha256_16": sha16(B3R / "margins.json"),
           "gate_sha256_16": sha16(B3R / "b3_ratings_gate.py"), "rule": RULE, "estimator":
           f"Q(0.25) + {gate.K_MESH} |Q(0.25) - Q(0.5)| + (bay - {gate.TAMB_MODEL_C}) (b3_ratings_gate.est)"}
    md = []

    # ---- 1 + 2: R_on
    ron = {}
    worst_old = None
    for c, bay in CASES.items():
        f25, f05 = ex["cases"][c]["files"]["p0p25"], ex["cases"][c]["files"]["p0p5"]
        for ref in R_ON:
            p25, p05 = f25["parts"][ref], f05["parts"][ref]
            assert p25["mpn"] == "25121WF680JT4E" and p25["spec"] == "chip2512", p25
            w = p25["watts_into_model"]
            term = gate.est(p25["pad_max_cell_c"], p05["pad_max_cell_c"], bay)
            elem = gate.est(p25["tj_c"], p05["tj_c"], bay)
            mt, me = row(margins, c, f"{ref}: 2512 terminal"), row(margins, c, f"{ref}: 2512 element")
            lim_fitted = line_limit(w, R_ON_PARTS["25121WF680JT4E"])
            # reproduction: est, limit and margin exactly as the gate rounds them
            assert abs(round(term, 1) - mt["est_c"]) < 0.05 and abs(round(lim_fitted, 1) - mt["limit_c"]) < 0.05, (c, ref)
            assert mt["margin_k"] == round(lim_fitted - term, 1), (c, ref, mt)
            assert abs(round(elem, 1) - me["est_c"]) < 0.05, (c, ref)
            d = {"P_w": round(w, 5), "terminal_est_c": round(term, 2), "element_est_c": round(elem, 2),
                 "element_margin_k": round(155.0 - elem, 1), "parts": {}}
            for mpn, part in R_ON_PARTS.items():
                lim = line_limit(w, part)
                d["parts"][mpn] = {"terminal_limit_c": round(lim, 2), "margin_k": round(lim - term, 1),
                                   "ratio_to_derated": (round(w / derated_w(term, part), 4) if derated_w(term, part) > 0
                                                        else None)}
            ron.setdefault(c, {})[ref] = d
        if c == RELEASE:
            worst_old = min(ron[c].items(), key=lambda kv: kv[1]["parts"]["25121WF680JT4E"]["margin_k"])
    res["r_on"] = ron
    # edge stress for the pulse check: 17 V driver step over 68 ohm (driver R_SRC and Rg,int ignored: an upper bound),
    # energy per edge = window-top dissipation / 60 kHz (make_heat_sources F_WIN)
    p_w = ron[RELEASE]["R10"]["P_w"]
    res["r_on_edge"] = {"step_v": 17.0, "peak_w": round(17.0 ** 2 / 68.0, 3), "energy_uj_per_edge": round(p_w / 60e3 * 1e6, 2),
                        "ps12_one_pulse_w_1_10us": R_ON_PARTS["PS122WF680JT4E"]["pulse_w_1us"],
                        "ratio": round(17.0 ** 2 / 68.0 / R_ON_PARTS["PS122WF680JT4E"]["pulse_w_1us"], 5)}
    rel = ron[RELEASE]
    md.append("## 1. R_on (R10/R12/R18/R20) reproduction and candidates\n")
    md.append(f"Reproduced: release {RELEASE} R10 terminal {rel['R10']['terminal_est_c']:.2f} C, line limit "
              f"155 - 85 x {rel['R10']['P_w']:.4f} / (0.8 x 1 W) = "
              f"{rel['R10']['parts']['25121WF680JT4E']['terminal_limit_c']:.2f} C -> "
              f"{rel['R10']['parts']['25121WF680JT4E']['margin_k']:+.1f} K (= margins.json, = scorecard "
              f"b3_release_margin_K). All 12 R_on terminal / element rows of the three cases match margins.json.\n")
    md.append("| case | ref | P W | terminal C | element C (155) | " + " | ".join(f"{m} limit / margin" for m in R_ON_PARTS)
              + " |")
    md.append("|---|---|---|---|---|" + "---|" * len(R_ON_PARTS))
    for c in CASES:
        for ref in R_ON:
            d = ron[c][ref]
            md.append(f"| {c} | {ref} | {d['P_w']:.3f} | {d['terminal_est_c']:.1f} | {d['element_est_c']:.1f} "
                      f"({d['element_margin_k']:+.1f}) | " + " | ".join(
                          f"{d['parts'][m]['terminal_limit_c']:.1f} / **{d['parts'][m]['margin_k']:+.1f}**" for m in R_ON_PARTS)
                      + " |")

    # ---- 5: release margin after the swap
    rel_rows = [r for r in margins["cases"][RELEASE] if r["gated"]]
    new_rows = []
    for r in rel_rows:
        ref = r["item"].split(":")[0]
        if ref in R_ON and "terminal derating" in r["item"]:
            m = rel[ref]["parts"]["PS122WF680JT4E"]["margin_k"]
            new_rows.append((m, f"{ref}: 2512 terminal derating, PS122WF680JT4E 2 W line"))
        else:
            new_rows.append((r["margin_k"], r["item"]))
    new_rows.sort()
    res["release_after"] = {"b3_release_margin_K_before": margins["metrics"]["b3_release_margin_K"],
                            "b3_release_margin_K_after": new_rows[0][0], "worst_after": new_rows[0][1],
                            "next_rows": [f"{m:+.1f} K {i}" for m, i in new_rows[:6]]}
    md.append(f"\nRelease margin with PS122WF680JT4E: {margins['metrics']['b3_release_margin_K']:+.1f} -> "
              f"**{new_rows[0][0]:+.1f} K**, now bound by '{new_rows[0][1]}' (not a BOM row). Next: "
              + "; ".join(res["release_after"]["next_rows"][1:]) + ".\n")

    # ---- 3: split bleed
    p_bleed = (gate.V_PN - gate.V_SPLIT) ** 2 / 4990.0
    bl = {"P_w": round(p_bleed, 5), "basis": f"(V_PN {gate.V_PN:.3f} - V_SPLIT {gate.V_SPLIT:.4f} V)^2 / 4.99 k "
          "(b3_ratings_gate MONITOR_SELF['tlvh431'] operating point); R131 carries no bleed (signal)", "cases": {}}
    for c, bay in CASES.items():
        f25, f05 = ex["cases"][c]["files"]["p0p25"], ex["cases"][c]["files"]["p0p5"]
        cc = {}
        for ref in BLEED:
            t = gate.est(f25["probes"][ref]["pad_max_cell_c"], f05["probes"][ref]["pad_max_cell_c"], bay)
            p = p_bleed if ref in BLEED_POWERED else 0.0
            cc[ref] = {"pad_est_c": round(t, 2), "P_w": round(p, 5), "nets": f25["probes"][ref]["nets"], "parts": {}}
            for mpn, part in BLEED_PARTS.items():
                lim = line_limit(p, part)
                e = {"terminal_limit_c": round(lim, 2), "margin_k": round(lim - t, 1)}
                if "terminal_line" in part:
                    lt = line_limit(p, part["terminal_line"])
                    e.update(terminal_line_limit_c=round(lt, 2), terminal_line_margin_k=round(lt - t, 1))
                cc[ref]["parts"][mpn] = e
        bl["cases"][c] = cc
    res["split_bleed"] = bl
    md.append("## 2. Split bleed R71/R72/R74/R75 (+R131 on the same line)\n")
    md.append(f"P = {p_bleed:.5f} W each (R71/R72/R74/R75). Gated basis: each part's ambient line read at the pad "
              "(ERJ-PA3's own terminal-part line, which Panasonic says takes priority, in brackets).\n")
    md.append("| case | ref | pad C | " + " | ".join(f"{m} limit / margin" for m in BLEED_PARTS) + " |")
    md.append("|---|---|---|" + "---|" * len(BLEED_PARTS))
    for c in CASES:
        for ref in BLEED:
            d = bl["cases"][c][ref]
            cells = []
            for m in BLEED_PARTS:
                e = d["parts"][m]
                s = f"{e['terminal_limit_c']:.1f} / **{e['margin_k']:+.1f}**"
                if "terminal_line_margin_k" in e:
                    s += f" ({e['terminal_line_limit_c']:.1f} / {e['terminal_line_margin_k']:+.1f})"
                cells.append(s)
            md.append(f"| {c} | {ref} | {d['pad_est_c']:.1f} | " + " | ".join(cells) + " |")

    # ---- 4: caps and U26
    caps = {}
    for c, bay in CASES.items():
        f25, f05 = ex["cases"][c]["files"]["p0p25"], ex["cases"][c]["files"]["p0p5"]
        caps[c] = {}
        for ref in CAPS:
            t = gate.est(f25["probes"][ref]["pad_max_cell_c"], f05["probes"][ref]["pad_max_cell_c"], bay)
            caps[c][ref] = {"pad_est_c": round(t, 2),
                            "margin_k": {m: round(p["t_cat"] - t, 1) for m, p in CAP_PARTS.items()}}
    res["caps"] = caps
    md.append("\n## 3. C126-C129 (pad copper = local-ambient proxy vs category temperature; own ripple heat ~0)\n")
    md.append("| case | ref | pad C | " + " | ".join(f"{m} ({p['t_cat']:.0f} C)" for m, p in CAP_PARTS.items()) + " |")
    md.append("|---|---|---|" + "---|" * len(CAP_PARTS))
    for c in CASES:
        for ref in CAPS:
            d = caps[c][ref]
            md.append(f"| {c} | {ref} | {d['pad_est_c']:.1f} | " + " | ".join(f"{d['margin_k'][m]:+.1f}" for m in CAP_PARTS)
                      + " |")
    u26 = {}
    for c, bay in CASES.items():
        f25, f05 = ex["cases"][c]["files"]["p0p25"], ex["cases"][c]["files"]["p0p5"]
        tj = gate.est(f25["parts"]["U26"]["tj_c"], f05["parts"]["U26"]["tj_c"], bay)
        mr = row(margins, c, "U26: TJ max")
        assert abs(round(tj, 1) - mr["est_c"]) < 0.05, (c, tj, mr)
        u26[c] = {"tj_est_c": round(tj, 2), "limit_c": U26_TJ[0], "margin_k": round(U26_TJ[0] - tj, 1),
                  "P_w": round(f25["parts"]["U26"]["watts_into_model"], 4)}
    res["u26"] = u26
    md.append("\n## 4. U26 TPS7A4700RGWR\n")
    md.append("| case | P W | TJ est C | limit C | margin K |\n|---|---|---|---|---|")
    for c, d in u26.items():
        md.append(f"| {c} | {d['P_w']:.3f} | {d['tj_est_c']:.1f} | {d['limit_c']:.0f} | **{d['margin_k']:+.1f}** |")
    res["datasheets"] = {**{k: v["src"] for k, v in R_ON_PARTS.items()}, **{k: v["src"] for k, v in BLEED_PARTS.items()},
                         **{k: v["src"] for k, v in CAP_PARTS.items()}, "TPS7A4700RGWR": U26_TJ[1]}
    (STUDY / "results/margins-c54.json").write_text(json.dumps(res, indent=1) + "\n")
    (STUDY / "results/margins-c54.md").write_text(
        f"# c54 release margins (generated by scripts/release_margins.py; board {ex['board_sha256'][:8]}, "
        f"margins.json {res['margins_json_sha256_16']})\n\n" + "\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
