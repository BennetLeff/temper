#!/bin/sh
# Candidate 48 passes (stage 48, c48-ldo-en-ref-watch): the accepted stage-47 copper (frozen; every stage 1-47 patch is
# already in it), edited by patches21.edit_base48 (the EN-to-IN ties of U3 / U37 / U38 / U39 and U3's / C48's old copper
# out; the EN dividers, the REF25 watchdog, U14's VDD / OUTB and U3's / C48's new copper in; bus_fault_hot re-laid above
# U3; place.py takes the poses from patches21.S48_PARTS / S48_MOVES), then the open pairs KiCad reports, as
# gates/passes.sh does, until a pass is clean. Same method as c44-selv-spine/passes44.sh.
#   sh passes48.sh BASE.json OUTROOT [FIRST_FILLS.json]
# BASE = stage 47's native-21/layout/copper.json (`git show 2f7241f61:zapote/power-stage-120v/native-21/layout/copper.json`).
# Pass j1 starts from an empty open-pair list; each later pass adds the previous pass's drc.json.
U=$(cd "$(dirname "$0")/../../.." && pwd)
G=$U/native-21/layout/gates
BASE=$1; OUT=$2; FILLS=${3:-}
mkdir -p "$OUT"; cd "$U"
ALL=$OUT/empty-drc.json
echo '{"violations": [], "unconnected_items": []}' > "$ALL"
for k in 1 2 3 4 5 6; do
  INCR21_FROZEN=1 FILLS=$FILLS sh native-21/layout/incr_iter.sh "$BASE" "$ALL" "$OUT/j$k" > "$OUT/j$k.log" 2>&1
  UN=$(grep "^unconnected" "$OUT/j$k.log")
  E=$(python3 "$G/count_errors.py" "$OUT/j$k/drc.json" 2>/dev/null)
  echo "== j$k $UN | $(head -1 "$OUT/j$k/barrier.txt" 2>/dev/null) | errors $E | $(grep -E 'still open|Traceback|stage 4[48]|patch (track|via)' "$OUT/j$k.log" | tr '\n' ' ' | cut -c1-400)" | tee -a "$OUT/passes.out"
  case "$UN" in "unconnected 0") [ "$E" = "0" ] && break ;; "") break ;; esac
  ALL="$ALL,$OUT/j$k/drc.json"; FILLS=$OUT/j$k/copper-dump.json
done
