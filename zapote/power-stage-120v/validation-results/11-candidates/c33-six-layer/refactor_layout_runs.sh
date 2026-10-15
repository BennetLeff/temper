#!/bin/sh
# Stage-33 refactor proof, layout scripts that the chain does not run (REFACTOR-PROOF.md): run them on fixed inputs and
# write their results to OUT, once with the pre-refactor code and once with the refactored code, then compare OUT dirs.
#   sh refactor_layout_runs.sh OUT PASSDIR [PREVPASS]
#   PASSDIR: a routing pass dir (iN) whose drc.json / copper-dump.json feed incr21 and plan_board_only21
# Writes OUT/incr21.json (+ .log), OUT/route21.json (+ .log), OUT/board_only21.json, OUT/trim_tails.log,
# OUT/test_trim_tails.log, OUT/zone_priority.log, OUT/xfer_spots.log, OUT/return-path.json. Leaves native-21/layout/board_only21.json as committed.
set -e
# incr21 / return_path19 iterate sets of strings: their output order follows Python's per-process hash seed, so two
# runs of the SAME code differ unless it is pinned
export PYTHONHASHSEED=0
OUT=$1; PASS=$2; PREV=${3:-$2}
U=$(cd "$(dirname "$0")/../../.." && pwd)
mkdir -p "$OUT"; cd "$U"
L=native-21/layout
cp $L/board_only21.json "$OUT/.board_only21.keep"
python3 $L/incr21.py $L/copper_base.json "$PREV/drc.json,$PASS/drc.json" "$OUT/incr21.json" "$PREV/copper-dump.json" > "$OUT/incr21.log" 2>&1
python3 - "$OUT/route21.json" > "$OUT/route21.log" 2>&1 <<'PY' || true
import json, sys
# the same in-memory edit for both runs: skip the J7-J10 stud lands (parts removed in stage 21), so the rest of the
# from-scratch router (planes, islands, fan-outs) runs on today's pads
src = open("native-21/layout/route21.py").read()
stud = '"J9": (130.0, 6.5), "J10": (143.0, 6.5), "J7": (130.0, 19.5), "J8": (143.0, 19.5),\n                      '
assert src.count(stud) == 1
g = {"__file__": "native-21/layout/route21.py", "__name__": "route21_proof"}
import os; sys.path.insert(0, os.path.abspath("native-21/layout"))
try:
    exec(compile(src.replace(stud, ""), "route21.py", "exec"), g)
except Exception:
    import traceback; traceback.print_exc()
json.dump({k: g.get(k) for k in ("ZONES", "TRACKS", "VIAS", "ESCAPES", "LINK_LOG", "FANOUT_LOG")}, open(sys.argv[1], "w"), indent=0)
PY
# (route21 from scratch may still stop on today's placement: incr21 uses only its helpers; the log, traceback
# included, and whatever it authored are compared between the two runs)
python3 $L/plan_board_only21.py "$PASS/copper-dump.json" > "$OUT/plan_board_only21.log" 2>&1
cp $L/board_only21.json "$OUT/board_only21.json"; cp "$OUT/.board_only21.keep" $L/board_only21.json
python3 $L/gates/trim_tails.py "$PASS/drc.json" $L/copper.json > "$OUT/trim_tails.log" 2>&1
python3 $L/gates/test_trim_tails.py > "$OUT/test_trim_tails.log" 2>&1
python3 $L/gates/zone_priority_gate.py $L/copper.json > "$OUT/zone_priority.log" 2>&1
python3 $L/gates/xfer_spots.py "$PASS/copper-dump.json" validation-plan/enclosure-fit/native21-courtyards.json 30,125 60,125 > "$OUT/xfer_spots.log" 2>&1
python3 $L/gates/return_path19.py "$PASS/copper-dump.json" --json "$OUT/return-path.json" > "$OUT/return_path19.log" 2>&1
echo done
