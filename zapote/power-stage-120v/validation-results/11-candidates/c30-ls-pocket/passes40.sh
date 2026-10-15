#!/bin/sh
# Candidate 30 passes (stage 40): the accepted stage-38 copper (frozen; every stage 1-38 patch is already in it), pruned
# where parts moved (incr21 INCR21_PRUNE: U44 / C159 / C160 / D18 and the new D20 / R135 / C168; SELV copper is kept and
# edited by hand) and edited by patches21.add_stage40, then the open pairs KiCad reports, as gates/passes.sh does, until
# a pass is clean. Same method as c23-supply-topology/passes38.sh.
#   sh passes40.sh BASE.json OUTROOT [FIRST_FILLS.json]
# BASE = stage 38's native-21/layout/copper.json (`git show f8cca7d21:zapote/power-stage-120v/native-21/layout/copper.json`),
# with BASE's stem + "_pads.json" beside it: stage 38's pads (`dump_pads.py` on the s38 board), which the prune compares.
U=$(cd "$(dirname "$0")/../../.." && pwd)
G=$U/native-21/layout/gates
BASE=$1; OUT=$2; FILLS=${3:-}
mkdir -p "$OUT"; cd "$U"
ALL=$OUT/empty-drc.json
echo '{"violations": [], "unconnected_items": []}' > "$ALL"
for k in 1 2 3 4 5; do
  INCR21_FROZEN=1 INCR21_PRUNE=1 FILLS=$FILLS sh native-21/layout/incr_iter.sh "$BASE" "$ALL" "$OUT/j$k" > "$OUT/j$k.log" 2>&1
  UN=$(grep "^unconnected" "$OUT/j$k.log")
  E=$(python3 "$G/count_errors.py" "$OUT/j$k/drc.json" 2>/dev/null)
  echo "== j$k $UN | $(head -1 "$OUT/j$k/barrier.txt" 2>/dev/null) | errors $E | $(grep -E 'still open|Traceback|stage 40|patch (track|via)' "$OUT/j$k.log" | tr '\n' ' ' | cut -c1-400)" | tee -a "$OUT/passes.out"
  case "$UN" in "unconnected 0") [ "$E" = "0" ] && break ;; "") break ;; esac
  ALL="$ALL,$OUT/j$k/drc.json"; FILLS=$OUT/j$k/copper-dump.json
done
