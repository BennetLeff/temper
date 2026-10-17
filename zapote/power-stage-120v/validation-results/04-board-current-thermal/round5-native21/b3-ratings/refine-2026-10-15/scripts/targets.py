#!/usr/bin/env python3
"""Task 4 on the corrected model (corrected c28 heat + central drain-lead path), by exact superposition
(superposition.py, validated against direct solves):

  * fix targets: the factor f on the A4 tank-current copper rows (every run_study.cases() row but the two line rows; the
    audit's "x on the A4 tank rows" sensitivity) that brings the laminate margin (1 mm-block peak and FET-row copper,
    MOT 130 C) to >= 0 at c22_h10 and c28_h10, bay 55 C; alone and with the 0.5 mOhm shunt (R5 loss x0.5). Also the f
    that clears every gated row (committed gate) and every gated + proposed row (evaluate.py).
  * min_gated_ext_noder: gated + proposed rows without the gate-resistor terminal-derating line (see margins()).
  * still-air ceiling: the highest commissioned ceiling c (I_t = 1.05 c, inlet 11.1 A, case temperature from
    sink_model central at c) whose every gated row is >= 0, at bay 55 and 61 C; committed gate set and with the
    proposed rows.
    python3 targets.py  ->  results/targets.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BAYS, RESULTS  # noqa: E402
import evaluate as E  # noqa: E402
import sink_model  # noqa: E402
import superposition as S  # noqa: E402

CASE_CEIL = {"c22_h10": 22.0, "c28_h10": 28.0}


def margins(B, ceil, f=1.0, R=1.0, bay=55.0, name="tmp", q=0.0):
    k = S.k_of(ceil)
    t = sink_model.t_case(ceil, "central")[0]["Q3"] - bay
    case = "cX_h10"
    per = {p: b.combine(k * f, k, R, t, q)[0] for p, b in B.items()}
    d = S.write(name, case, per)
    ev = E.evaluate(d, bay, (case,))
    s = E.compact(ev)[case]
    lam = min(s["lam_block"], s["lam_fet_row"])
    # every gated + proposed row except the gate-resistor terminal-derating line, which depends on the gate-drive loss
    # (60 kHz x Q) and not on tank current, so no copper or ceiling change can clear it (needs a larger package)
    noder = min([s["min_gated"]] + [r["margin_k"] for r in ev["ext"][case] if "terminal derating" not in r["item"]])
    gr = [{"ref": r["item"].split(":")[0], "P_W": float(r["item"].split(" at ")[1].split(" W")[0]), "T_term_c": r["est_c"]}
          for r in ev["ext"][case] if "terminal derating" in r["item"] and r["item"].split(":")[0] in ("R10", "R12", "R18", "R20")]
    return {"lam": lam, "min_gated": s["min_gated"], "min_gated_ext": s["min_gated_ext"], "min_gated_ext_noder": noder, "detail": s,
            "gateR_on_terminal": gr,
            "worst_rows": sorted([r for r in ev["gate"]["cases"][case] if r["gated"]] + ev["ext"][case], key=lambda r: r["margin_k"])[:5]}


def bisect(fun, lo, hi, tol=0.002):
    """Largest x in [lo, hi] with fun(x) >= 0, fun decreasing in x. None if fun(lo) < 0."""
    if fun(lo) < 0:
        return None
    if fun(hi) >= 0:
        return hi
    while hi - lo > tol:
        m = 0.5 * (lo + hi)
        lo, hi = (m, hi) if fun(m) >= 0 else (lo, m)
    return lo


def main():
    B = S.bases()
    assert all(b.dQ is not None for b in B.values())
    hc = json.loads((RESULTS / "heat-corrections.json").read_text())
    qd = hc["q_deck_weight"]
    out = {"basis": "drain-lead path central (G 0.0845 W/K, T_case sink_model central) + corrected heat. Suffix '_deck' = "
                    "the file of record heat-c28-corrected-deck.json (as-built deck gate charge 382.6 nC; q = "
                    f"{qd:.6f}); no suffix = heat-c28-corrected.json (740 nC allocation, upper bound); '_dsq' = the "
                    "datasheet-Q file (374.1 nC)", "q_deck": qd,
           "validation": S.validate(B), "fix_targets": {}, "ceilings": {}, "anchors": {}}
    assert out["validation"]["pass"], out["validation"]
    for q, sfx in ((qd, "_deck"), (0.0, ""), (1.0, "_dsq")):
        for case, ceil in CASE_CEIL.items():
            for R in (1.0, 0.5):
                key = f"{case}_R5x{R:g}{sfx}"
                res = {"at_f1": margins(B, ceil, 1.0, R, q=q)}
                for crit in ("lam", "min_gated", "min_gated_ext", "min_gated_ext_noder"):
                    f = bisect(lambda x: margins(B, ceil, x, R, q=q)[crit], 0.0, 1.0)
                    res[f"f_{crit}"] = None if f is None else round(f, 3)
                    if f is not None:
                        res[f"at_f_{crit}"] = margins(B, ceil, f, R, q=q)
                out["fix_targets"][key] = res
                print(key, {k: v for k, v in res.items() if k.startswith("f_")}, "lam@f1", res["at_f1"]["lam"], flush=True)
        for bay in BAYS:
            for crit in ("lam", "min_gated", "min_gated_ext", "min_gated_ext_noder"):
                c = bisect(lambda x: margins(B, x, 1.0, 1.0, bay, q=q)[crit], 10.0, 28.0, tol=0.01)
                out["ceilings"][f"b{bay:g}_{crit}{sfx}"] = None if c is None else round(c, 2)
            for c in (16.0, 18.0, 20.0, 22.0, 24.0):
                out["anchors"][f"b{bay:g}_c{c:g}{sfx}"] = margins(B, c, 1.0, 1.0, bay, q=q)
            print("bay", bay, sfx or "(allocation)", {c: out["ceilings"][f"b{bay:g}_{c}{sfx}"] for c in ("lam", "min_gated", "min_gated_ext", "min_gated_ext_noder")}, flush=True)
    # gate-resistor package at the record ceilings (deck basis; the derating line at the fitted 1206's terminal
    # temperature, so conservative for a larger body); FH General Thick Film V11.0 p.2 ratings, curve 2
    import report
    out["gateR_package_at_ceiling"] = {}
    for bay in BAYS:
        c = out["ceilings"][f"b{bay:g}_min_gated_ext_noder_deck"]
        if c is None:
            continue
        m = margins(B, c, 1.0, 1.0, bay, q=qd)
        w = max(m["gateR_on_terminal"], key=lambda r: r["T_term_c"] + 85.0 * r["P_W"] / 0.2)
        out["gateR_package_at_ceiling"][f"b{bay:g}"] = {
            "ceiling_A": c, **w, "margin_k": {k: round(155.0 - 85.0 * (w["P_W"] / n) / (0.8 * wr) - w["T_term_c"], 1)
                                              for k, (wr, n) in report.PKG.items()}}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "targets.json").write_text(json.dumps(out, indent=1, default=float) + "\n")


if __name__ == "__main__":
    main()
