#!/usr/bin/env python3
"""S21 temperature rows (b3-ratings/temp-ratings-2026-10-15) re-evaluated at airflow cases, plus U3 TJ (S19), J1 and PS2.

    python3 -I s21_airflow.py --case uniform:c28_h45@61 [--case ...] [--out FILE]

Adapted from the committed scripts/temp_ratings.py (copied, with its vendor gate, to S21SCRIPTS/scripts; that copy's
../snap -> the s21 input snapshot of PS HEAD: margins / ledger / BOM by `git show HEAD:`, runs = the chain's BASIS run
files). The 73 lines and their refs come from the committed results.json (the pre-S21 ledger left them unrated; the
HEAD ledger now rates them, so unrated_lines() would find none). temp_ratings.evaluate() is used unchanged with its
CASES / REL rebound to the asked cases.

Control: the same code on the three BASIS cases reproduces the committed results.json release / c22 / c28 rows (asserted
to 0.05 K on every line's worst ref).
U3 TJ (OPEN-ITEMS S19; s20-286v-recite README-analysis 1.6): pad + psiJB 38.7 K/W x 0.160 W (max) - the pad is the gate
estimator on U3's probe pad maximum; the README's 106.7 / 124.3 C pads (pre-S18 runs) are compared, not asserted.
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
A = Path("/Users/bennet/Desktop/temper/worktrees/runs-native21/airflow28")
S21 = A / "s21-scripts/scripts"
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
COMMITTED = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings/temp-ratings-2026-10-15/results.json"
sys.argv = [sys.argv[0]] + sys.argv[1:]
_ap = argparse.ArgumentParser()
_ap.add_argument("--case", action="append", default=[], help="MODE:CASE@BAY (MODE uniform|top|jet)")
_ap.add_argument("--out")
ARGS = _ap.parse_args()
import os  # noqa: E402
os.environ["TEMP_RATINGS_SNAP"] = str(A / "s21snap")      # the vendor gate's BOM_CSV (PS HEAD default.csv)
sys.path.insert(0, str(S21 / "vendor"))
import b3_ratings_gate  # noqa: E402,F401  the S18 (HEAD) vendor gate, cached before temp_ratings would add vendor/s47
sys.path.insert(0, str(S21))
import temp_ratings as tr  # noqa: E402  (imported: its own argparse takes defaults; snap = S21/../snap -> s21snap)
assert tr.gate is b3_ratings_gate and "MODULES" in dir(tr.gate)
import power_table as pt  # noqa: E402
import ratings_table as rt  # noqa: E402

PSI_JB, P_U3 = 38.7, 0.160


def load(mode_case):
    mode, _, cb = mode_case.partition(":")
    c, _, b = cb.partition("@")
    d = A / "runs" / mode / f"bay{int(float(b))}" if mode != "basis" else A / "s21snap/runs"
    return f"{mode}:{c}@{b}", float(b), [json.loads((d / f"{c}_p0p{m}.json").read_text()) for m in ("25", "5")]


def rows_at(cases):
    """cases: {key: (bay, [r25, r05])}. Returns per line the worst ref per case."""
    tr.CASES = {k: v[0] for k, v in cases.items()}
    tr.REL = next(iter(cases))
    data = {k: v[1] for k, v in cases.items()}
    P = pt.resistor_powers()
    P.update(pt.ic_powers(rt.DS))
    com = json.loads(COMMITTED.read_text())
    out = []
    for ln in com["lines"]:
        line = {"mpn": ln["mpn"], "refs": ln["refs"]}
        rows, worst = tr.evaluate(line, data, P)
        out.append({"mpn": ln["mpn"], "refs": ln["refs"], "committed": {k: ln[k] for k in ("release", "c28") if k in ln},
                    "cases": {k: {"ref": w["ref"], **w["cases"][k]} for k, w in worst.items()}})
    return out


def u3(cases):
    out = {}
    for k, (bay, (a, b)) in cases.items():
        pad = tr.gate.est(a["probes"]["U3"]["pad_max_cell_c"], b["probes"]["U3"]["pad_max_cell_c"], bay)
        tj = pad + PSI_JB * P_U3
        out[k] = {"pad_c": round(pad, 1), "tj_c": round(tj, 1), "margin_k": round(125.0 - tj, 1)}
    return out


def main():
    basis = {}
    for x in ("basis:c17.5_h10@61", "basis:c22_h10@55", "basis:c28_h10@55"):
        k, bay, rr = load(x)
        basis[k] = (bay, rr)
    ctl = rows_at(basis)
    dmax = 0.0
    names = {"basis:c17.5_h10@61": "release", "basis:c28_h10@55": "c28"}
    for r in ctl:
        for k, nm in names.items():
            dmax = max(dmax, abs(r["cases"][k]["margin_k"] - r["committed"][nm]["margin_k"]))
    u3b = u3(basis)
    assert dmax <= 0.05, dmax
    # the S20 analysis pads (106.7 / 124.3 C) are pre-S18 run files; S18 moved PS2's neighbours toward margin, so the
    # difference is reported, not asserted (expected small and negative)
    u3b["s20_readme_pad_diff_k"] = {"c17.5@61": round(u3b["basis:c17.5_h10@61"]["pad_c"] - 106.7, 1),
                                    "c28@55": round(u3b["basis:c28_h10@55"]["pad_c"] - 124.3, 1)}
    print(f"control: {len(ctl)} lines reproduce committed results.json (max |d margin| {dmax:.3f} K); U3 pads {u3b}")
    cases = {}
    for x in ARGS.case:
        k, bay, rr = load(x)
        cases[k] = (bay, rr)
    res = {"control": {"lines": len(ctl), "max_abs_margin_diff_k": dmax, "u3_basis": u3b}, "cases": list(cases)}
    if cases:
        rows = rows_at(cases)
        res["lines"] = rows
        res["u3"] = u3(cases)
        for k in cases:
            bad = sorted([r for r in rows if r["cases"][k]["margin_k"] < 10], key=lambda r: r["cases"][k]["margin_k"])
            print(f"\n{k}: lines under +10 K (worst ref):")
            for r in bad:
                w = r["cases"][k]
                print(f"  {r['mpn'][:22]:22} {w['ref']:5} {w['est_c']:6.1f} / {w['limit_c']:6.1f}  {w['margin_k']:+6.1f} K"
                      f"   (c28@55 still air {r['committed']['c28']['margin_k']:+.1f})")
            print(f"  U3 TJ {res['u3'][k]}")
    if ARGS.out:
        Path(ARGS.out).write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
