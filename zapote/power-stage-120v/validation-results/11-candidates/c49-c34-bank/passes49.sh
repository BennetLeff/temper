#!/bin/sh
# Candidate 49 passes (stage 49, c49-c34-bank): the accepted stage-48 copper (frozen; every stage 1-48 patch is already in
# it, so edit_base48 is a no-op), edited by patches21.edit_base49 (the sw_b / res_a B.Cu bank strips re-cut for the P22.5
# B32643B bank, SW_B column x 185.5, rows y 53.2-113.2; line_zc_raw's x 184-203 run moved y 121.27 -> 122.75; place.py
# takes the bank poses), then the open pairs KiCad reports, as gates/passes.sh does, until a pass is clean. Same method as
# c48-ldo-en-ref-watch/passes48.sh.
#   sh passes49.sh BASE.json OUTROOT [FIRST_FILLS.json]
# BASE = stage 48's native-21/layout/copper.json (`git show b8ddef3da:zapote/power-stage-120v/native-21/layout/copper.json`).
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
  echo "== j$k $UN | $(head -1 "$OUT/j$k/barrier.txt" 2>/dev/null) | errors $E | $(grep -E 'still open|Traceback|stage 49|patch (track|via)' "$OUT/j$k.log" | tr '\n' ' ' | cut -c1-400)" | tee -a "$OUT/passes.out"
  case "$UN" in "unconnected 0") [ "$E" = "0" ] && break ;; "") break ;; esac
  ALL="$ALL,$OUT/j$k/drc.json"; FILLS=$OUT/j$k/copper-dump.json
done
