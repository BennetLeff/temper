#!/bin/sh
# Candidate 23 passes (stage 38): the accepted stage-35 copper (frozen; every stage 1-35 patch is already in it), edited
# by patches21.edit_base (PS1 / v15_selv copper removed, L_FILT / N_FILT re-laid to F2 / J11), then the open pairs KiCad
# reports, as gates/passes.sh does, until a pass is clean. Same method as c35-smt-terminals/passes35.sh.
#   sh passes38.sh BASE.json OUTROOT [FIRST_FILLS.json]
# BASE = stage 35's native-21/layout/copper.json (`git show 0aecdc56f:zapote/power-stage-120v/native-21/layout/copper.json`).
# Pass j1 starts from an empty open-pair list (the frozen base has no DRC of its own on the s38 netlist); each later
# pass adds the previous pass's drc.json. FIRST_FILLS (optional) = a previous build's copper-dump.json.
U=$(cd "$(dirname "$0")/../../.." && pwd)
G=$U/native-21/layout/gates
BASE=$1; OUT=$2; FILLS=${3:-}
mkdir -p "$OUT"; cd "$U"
ALL=$OUT/empty-drc.json
echo '{"violations": [], "unconnected_items": []}' > "$ALL"
for k in 1 2 3 4 5; do
  INCR21_FROZEN=1 FILLS=$FILLS sh native-21/layout/incr_iter.sh "$BASE" "$ALL" "$OUT/j$k" > "$OUT/j$k.log" 2>&1
  UN=$(grep "^unconnected" "$OUT/j$k.log")
  E=$(python3 "$G/count_errors.py" "$OUT/j$k/drc.json" 2>/dev/null)
  echo "== j$k $UN | $(head -1 "$OUT/j$k/barrier.txt" 2>/dev/null) | errors $E | $(grep -E 'still open|Traceback|stage 3[58]|patch (track|via)' "$OUT/j$k.log" | tr '\n' ' ' | cut -c1-400)" | tee -a "$OUT/passes.out"
  case "$UN" in "unconnected 0") [ "$E" = "0" ] && break ;; "") break ;; esac
  ALL="$ALL,$OUT/j$k/drc.json"; FILLS=$OUT/j$k/copper-dump.json
done
