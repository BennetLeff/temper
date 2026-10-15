#!/bin/zsh
# thermal-refine (2026-10-15): reproduce every number in results*/ from the repo (git objects at pinned commits, never the
# live worktree) and dl/. Board of record s38 (DECISIONS 50) -> runs-s38/, results-s38/; s35 (the board the task was set on,
# DECISIONS 46) -> runs/, results/. About 2 h per board on 4 workers on a loaded 12-core Mac (~100 body-model solves;
# 0.25 mm dominates); cached solves are skipped.
set -euo pipefail
cd "${0:A:h}/scripts"
export PYTHONDONTWRITEBYTECODE=1
python3 -I recom_curve.py ..               # U41/U42 row vs the RECOM R24C2T25/R p.2 curves (reads dl/) -> results/recom_curve.json
for board in s38 s35; do
  export THERMAL_REFINE_BOARD=$board
  python3 freeze.py                        # frozen/<board>/ = git archive of the files read, at the board's pin
  python3 a4_fields.py                     # + the gitignored A4 heat fields, checked against the pinned A4 JSONs
  python3 prepare.py                       # model[-board]/ = pin + patches/*.diff; geometry sha; part bodies vs P&P; fet_case
  python3 sink_model.py                    # FET case temperature corners (S8 sink) -> results*/sink_model.json
  python3 heat_c28_corrected.py            # corrected c28 heat files (deck 382.6 nC = record; 740 nC; datasheet 374.1 nC)
  python3 verify_heat_patch.py             # patched make_heat_sources.py reproduces the deck-charge file of record
  python3 plan.py base                     # -> runs*/jobs-base.json
  if [[ $board == s35 ]]; then rd=runs; else rd=runs-$board; fi
  python3 solve.py ../$rd/jobs-base.json --workers 4
  python3 controls.py                      # K1-K4 (committed margins, G = 0, energy, analytic disc)
  python3 report.py                        # tasks 1-3 -> results*/summary.json, results*/TABLES.md
  python3 targets.py                       # task 4 -> results*/targets.json
  python3 confirm.py deck                  # direct solves at the task-4 answers, record basis -> results*/confirm-deck.json
  python3 confirm.py dsq                   # same on the datasheet-Q file (superposition check at q = 1) -> results*/confirm-dsq.json
  python3 e2e.py                           # patches applied to a scratch copy; repo entry points reproduce the record
  python3 -I laminate_scope.py             # task 5 (reads dl/ and the frozen stackup.json) -> results*/laminate_scope.json
done
