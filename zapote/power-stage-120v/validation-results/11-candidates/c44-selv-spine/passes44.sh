#!/bin/sh
# Candidate 44 passes (stage 44, SELV-spine lane): the accepted stage-43 copper (frozen; every stage 1-43 patch is already
# in it), edited by patches21.edit_base44 (C169-C175 SELV transfer caps and their plane vias, the bus_fault drop via
# moved down its trunk, the bias_good In2 leg run on to its leg-A drop and the edge via removed; place.py takes the cap
# poses from patches21.S44_CAPS), then the open pairs KiCad reports, as gates/passes.sh does, until a pass is clean.
# Same method as c39-gate-network/passes42.sh.
#   sh passes44.sh BASE.json OUTROOT [FIRST_FILLS.json]
# BASE = stage 43's native-21/layout/copper.json (e5f7f90e...; `git show cb48a12e6:zapote/power-stage-120v/native-21/layout/copper.json`).
# Pass j1 starts from an empty open-pair list; each later pass adds the previous pass's drc.json.
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
  echo "== j$k $UN | $(head -1 "$OUT/j$k/barrier.txt" 2>/dev/null) | errors $E | $(grep -E 'still open|Traceback|stage 4[34]|patch (track|via)' "$OUT/j$k.log" | tr '\n' ' ' | cut -c1-400)" | tee -a "$OUT/passes.out"
  case "$UN" in "unconnected 0") [ "$E" = "0" ] && break ;; "") break ;; esac
  ALL="$ALL,$OUT/j$k/drc.json"; FILLS=$OUT/j$k/copper-dump.json
done
