#!/bin/sh
# Candidate 35 passes: the accepted stage-32 copper (frozen, all stage 1-32 patches already in it) plus only the stage-35
# terminal land vias (patches21.add_stage35; J2 / J5 are the REDCUBE SMT 7466004R), then the open pairs KiCad reports,
# as gates/passes.sh does, until a pass is clean. Same method as c33-six-layer/passes33.sh, on the four-layer stack.
#   sh passes35.sh BASE.json OUTROOT FIRST_DRC.json FIRST_FILLS.json
# BASE = stage 32's native-21/layout/copper.json (d6f55dfe...; `git show 27e946580:zapote/power-stage-120v/native-21/layout/copper.json`).
U=$(cd "$(dirname "$0")/../../.." && pwd)
G=$U/native-21/layout/gates
BASE=$1; OUT=$2; ALL=$3; FILLS=$4
mkdir -p "$OUT"; cd "$U"
for k in 1 2 3 4 5; do
  INCR21_FROZEN=1 FILLS=$FILLS sh native-21/layout/incr_iter.sh "$BASE" "$ALL" "$OUT/j$k" > "$OUT/j$k.log" 2>&1
  UN=$(grep "^unconnected" "$OUT/j$k.log")
  E=$(python3 "$G/count_errors.py" "$OUT/j$k/drc.json" 2>/dev/null)
  echo "== j$k $UN | $(head -1 "$OUT/j$k/barrier.txt" 2>/dev/null) | errors $E | $(grep -E 'still open|Traceback|stage 35|patch (track|via)' "$OUT/j$k.log" | tr '\n' ' ' | cut -c1-400)" | tee -a "$OUT/passes.out"
  case "$UN" in "unconnected 0") [ "$E" = "0" ] && break ;; "") break ;; esac
  ALL="$ALL,$OUT/j$k/drc.json"; FILLS=$OUT/j$k/copper-dump.json
done
