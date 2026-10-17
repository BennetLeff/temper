#!/bin/sh
# Candidate 50 passes (stage 50, c50-permit-gate): the accepted stage-49 copper (frozen; every stage 1-49 patch is already in
# it, so edit_base48 / edit_base49 are no-ops), edited by patches21.edit_base50 (R135.1 v3v3 -> permit: its F.Cu v3v3 stub
# out, the via kept; a 0.25 mm F.Cu permit stub east to PERMIT's leg-B trace at (33.95, 108.3)), then the open pairs
# KiCad reports, as gates/passes.sh does, until a pass is clean. Same method as
# c49-c34-bank/passes49.sh.
#   sh passes50.sh BASE.json OUTROOT [FIRST_FILLS.json]
# BASE = stage 49's native-21/layout/copper.json (`git show db60f2692:zapote/power-stage-120v/native-21/layout/copper.json`).
# Pass j1 starts from an empty open-pair list; each later pass adds the previous pass's drc.json.
U=$(cd "$(dirname "$0")/../../../.." && pwd)
G=$U/native-21/layout/gates
BASE=$1; OUT=$2; FILLS=${3:-}
mkdir -p "$OUT"; cd "$U"
ALL=$OUT/empty-drc.json
echo '{"violations": [], "unconnected_items": []}' > "$ALL"
for k in 1 2 3 4 5 6; do
  INCR21_FROZEN=1 FILLS=$FILLS sh native-21/layout/incr_iter.sh "$BASE" "$ALL" "$OUT/j$k" > "$OUT/j$k.log" 2>&1
  UN=$(grep "^unconnected" "$OUT/j$k.log")
  E=$(python3 "$G/count_errors.py" "$OUT/j$k/drc.json" 2>/dev/null)
  echo "== j$k $UN | $(head -1 "$OUT/j$k/barrier.txt" 2>/dev/null) | errors $E | $(grep -E 'still open|Traceback|stage 50|patch (track|via)' "$OUT/j$k.log" | tr '\n' ' ' | cut -c1-400)" | tee -a "$OUT/passes.out"
  case "$UN" in "unconnected 0") [ "$E" = "0" ] && break ;; "") break ;; esac
  ALL="$ALL,$OUT/j$k/drc.json"; FILLS=$OUT/j$k/copper-dump.json
done
