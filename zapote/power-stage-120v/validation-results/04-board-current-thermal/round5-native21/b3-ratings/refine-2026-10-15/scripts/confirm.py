#!/usr/bin/env python3
"""Direct solves at the task-4 answers (results/targets.json) to confirm the superposition numbers.

  * on the corrected model of record (deck-charge heat file heat-c28-corrected-deck.json + central lead path), or with
    the argument 'dsq' on the datasheet-Q file (q = 1, a check of the superposition at the end of its heat axis):
  * fix targets f_lam for c22 / c28 (R5 x1 and x0.5), bay 55
  * still-air ceilings (committed gate set and with the proposed rows): the 0.5 A step at or below the superposed
    ceiling, at bay 55 and 61
    python3 confirm.py [deck|dsq] -> results/confirm-<basis>.json (superposed vs direct margins; pass if |diff| <= 0.05 K)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, RUNS  # noqa: E402
import evaluate as E  # noqa: E402
import plan  # noqa: E402
import solve  # noqa: E402
import targets  # noqa: E402
import superposition as S  # noqa: E402


def main():
    basis = sys.argv[1] if len(sys.argv) > 1 else "deck"
    sfx, heat = {"deck": ("_deck", plan.HEAT_DECK), "dsq": ("_dsq", plan.HEAT_DSQ)}[basis]
    q = {"deck": json.loads((RESULTS / "heat-corrections.json").read_text())["q_deck_weight"], "dsq": 1.0}[basis]
    pre = "" if basis == "dsq" else basis          # config folder prefix (dsq kept unprefixed: its solves came first)
    tg = json.loads((RESULTS / "targets.json").read_text())
    jobs, checks = [], []
    for key, v in tg["fix_targets"].items():
        f = v.get("f_lam")
        if not key.endswith(sfx) or f is None or f >= 1.0:
            continue
        case, r5 = key[:-len(sfx)].split("_R5x")
        ceil = targets.CASE_CEIL[case]
        name = f"CF{pre}_{case}_R5x{r5}_f{f:g}".replace(".", "p")
        ps = {"R5": float(r5)} if float(r5) != 1.0 else {}
        jobs += plan.config(name, heat, cases={case: ceil}, tank_factor=f, part_scale=ps)
        checks.append((name, case, 55.0, ("fix", key, f, ceil, float(r5))))
    for bay in (55.0, 61.0):
        for crit in ("min_gated", "min_gated_ext", "min_gated_ext_noder"):
            c = tg["ceilings"].get(f"b{bay:g}_{crit}{sfx}")
            if c is None:
                continue
            c2 = math.floor(c * 2) / 2
            case = f"c{c2:g}_h10".replace(".", "p")
            name = f"CC{pre}_b{bay:g}_{case}"
            if any(j["config"] == name for j in jobs):
                continue
            jobs += plan.config(name, heat, cases={case: c2}, bay=bay)
            checks.append((name, case, bay, ("ceiling", crit, c2)))
    solve.run_jobs(jobs, 4)
    B = S.bases()
    out = []
    for name, case, bay, what in checks:
        direct = E.compact(E.evaluate(RUNS / name, bay, (case,)))[case]
        if what[0] == "fix":
            _, key, f, ceil, r5 = what
            sup = targets.margins(B, ceil, f, r5, bay, q=q)["detail"]
        else:
            sup = targets.margins(B, what[2], 1.0, 1.0, bay, q=q)["detail"]
        diffs = {k: round(direct[k] - sup[k], 3) for k in ("lam_block", "lam_fet_row", "min_gated", "min_gated_ext", "R5_el", "R5_term", "C38", "C40", "gateR_el", "gateR_der", "U26", "U42")
                 if direct[k] is not None and sup[k] is not None}
        out.append({"config": name, "what": what, "bay": bay, "direct": direct, "superposed": sup, "diff_K": diffs,
                    "pass": all(abs(d) <= 0.05 for d in diffs.values())})
        print(name, diffs, "direct lam", direct["lam_block"], direct["lam_fet_row"], "min gated", direct["min_gated"], direct["min_gated_ext"])
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"confirm-{basis}.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    raise SystemExit(0 if all(o["pass"] for o in out) else 1)


if __name__ == "__main__":
    main()
