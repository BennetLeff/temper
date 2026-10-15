#!/usr/bin/env python3
"""Check patches/heat-c28-60khz.diff: the patched make_heat_sources.py (model/b3-heat/, run with UNIT = the repo and its
outputs redirected to runs/heat-patch/) must
  * reproduce runs/heat/heat-c28-corrected-deck.json (heat_c28_corrected.py, the deck-charge file of record) row for row within 1e-12 W, and
  * leave the nominal file and every other c28 row identical to the committed inputs.
    python3 verify_heat_patch.py  ->  results/heat_patch_check.json, exit 1 on failure
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEAT_DIR, MODEL, RESULTS, ROUND5, RUNS, UNIT  # noqa: E402

src = (MODEL / "b3-heat/make_heat_sources.py").read_text()
out_dir = RUNS / "heat-patch"
old = 'HERE = Path(__file__).resolve().parent\nUNIT = HERE.parents[3]\n'
assert src.count(old) == 1
src = src.replace(old, f'HERE = Path({str(out_dir)!r})\nUNIT = Path({str(UNIT)!r})\n')
out_dir.mkdir(parents=True, exist_ok=True)
exec(compile(src, "make_heat_sources(patched)", "exec"), {"__name__": "__main__"})

new28 = json.loads((out_dir / "inputs/native21-board-heat-sources-c28.json").read_text())
mine = json.loads((HEAT_DIR / "heat-c28-corrected-deck.json").read_text())
com28 = json.loads((ROUND5 / "b3/inputs/native21-board-heat-sources-c28.json").read_text())
newnom = json.loads((out_dir / "inputs/native21-board-heat-sources.json").read_text())
comnom = json.loads((ROUND5 / "b3/inputs/native21-board-heat-sources.json").read_text())
changed = {p["ref"] for p in mine["parts"] if p["basis"] == "thermal-refine 2026-10-15"}
worst_corr, worst_same, bad = 0.0, 0.0, []
for a, b, c in zip(new28["parts"], mine["parts"], com28["parts"]):
    assert a["ref"] == b["ref"] == c["ref"]
    worst_corr = max(worst_corr, abs(a["watts_nominal"] - b["watts_nominal"]), abs(a["watts_worst"] - b["watts_worst"]))
    if a["ref"] not in changed:
        if a != c:
            bad.append(a["ref"])
nominal_same = newnom == comnom
res = {"pass": worst_corr < 1e-12 and not bad and nominal_same, "max_abs_W_vs_heat_c28_corrected_deck": worst_corr,
       "unchanged_rows_differ": bad, "nominal_file_identical": nominal_same, "changed_rows": sorted(changed),
       "totals_W": new28["totals_W"]}
RESULTS.mkdir(exist_ok=True)
(RESULTS / "heat_patch_check.json").write_text(json.dumps(res, indent=1) + "\n")
print(res)
raise SystemExit(0 if res["pass"] else 1)
