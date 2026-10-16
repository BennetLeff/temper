#!/bin/sh
# Candidate 39 passes (stage 42): the accepted stage-41 copper (frozen; every stage 1-41 patch is already in it), edited
# by patches21.edit_base42 (the four gate runs re-laid round the 68 ohm 2512 turn-on resistors, which place.py turns
# 180 deg on the same centre; the 0603 pull-downs 0.5 mm west and north, their source vias 0.5 mm west except R11's,
# which goes to (59.6, 13.3) with R11 turned 180 deg; R10's redundant sw_a stub via removed), then the open pairs KiCad reports, as gates/passes.sh does, until a pass is clean. Same method as
# c36-tank-copper/passes41.sh.
#   sh passes42.sh BASE.json OUTROOT [FIRST_FILLS.json]
# BASE = stage 41's native-21/layout/copper.json (77f3e994...; `git show 18187575d:zapote/power-stage-120v/native-21/layout/copper.json`).
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
  echo "== j$k $UN | $(head -1 "$OUT/j$k/barrier.txt" 2>/dev/null) | errors $E | $(grep -E 'still open|Traceback|stage 4[12]|patch (track|via)' "$OUT/j$k.log" | tr '\n' ' ' | cut -c1-400)" | tee -a "$OUT/passes.out"
  case "$UN" in "unconnected 0") [ "$E" = "0" ] && break ;; "") break ;; esac
  ALL="$ALL,$OUT/j$k/drc.json"; FILLS=$OUT/j$k/copper-dump.json
done
