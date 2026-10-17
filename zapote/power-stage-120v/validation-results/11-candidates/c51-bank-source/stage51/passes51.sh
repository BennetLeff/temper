#!/bin/sh
# Candidate 51 passes (stage 51, c51-bank-source): the accepted stage-50 copper (frozen; every stage 1-50 patch is already
# in it, so edit_base48 / 49 / 50 are no-ops), with the bank re-footprinted (place.py S51_BANK; parts.json
# Bank_Film_DualPitch_P22.5_P27.5_Radial: pad 1 at x 163.0, pad-2 holes at x 185.5 and x 190.5, both on sw_b). No copper
# edit: the second SW_B hole sits on the widened s49 sw_b B.Cu strip (x 183-200.6, bottom y 114.4 at x 183-192). Then the
# open pairs KiCad reports, as gates/passes.sh does, until a pass is clean. Same method as c50-permit-gate/stage50/passes50.sh.
#   sh passes51.sh BASE.json OUTROOT [FIRST_FILLS.json]
# BASE = stage 50's native-21/layout/copper.json (`git show 29f16fd77:zapote/power-stage-120v/native-21/layout/copper.json`).
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
  echo "== j$k $UN | $(head -1 "$OUT/j$k/barrier.txt" 2>/dev/null) | errors $E | $(grep -E 'still open|Traceback|stage 5[01]|patch (track|via)' "$OUT/j$k.log" | tr '\n' ' ' | cut -c1-400)" | tee -a "$OUT/passes.out"
  case "$UN" in "unconnected 0") [ "$E" = "0" ] && break ;; "") break ;; esac
  ALL="$ALL,$OUT/j$k/drc.json"; FILLS=$OUT/j$k/copper-dump.json
done
