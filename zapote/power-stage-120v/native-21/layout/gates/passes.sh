#!/bin/sh
# Native-21 incremental routing passes (copper_base.json + patches21 + cumulative DRC open pairs).
#   sh native-21/layout/gates/passes.sh OUTROOT [HISTORY_ROOT ...]
# Pass 0 builds the base alone to collect its open pairs; passes 1..6 route, each fed every earlier
# drc.json (history roots first). Stops once a pass >= 2 is clean. Writes OUTROOT/passes.out.
U=$(cd "$(dirname "$0")/../../.." && pwd)
G=$U/native-21/layout/gates
OUT=$1; shift
mkdir -p "$OUT"; cd "$U"
. "$G/laps.sh"; laps_init passes "$OUT/steps.jsonl"
drcs() { for D in "$@" "$OUT"; do ls -d "$D"/i[0-9]*/drc.json 2>/dev/null | awk -F'/i' '{n=$NF; sub(/\/drc.json/,"",n); print n" "$0}' | sort -n | cut -d' ' -f2; done | tr '\n' ',' | sed 's/,$//'; }
ALL=$(drcs "$@")
if [ -z "$ALL" ]; then sh native-21/layout/incr_iter.sh native-21/layout/copper_base.json - "$OUT/i0" > "$OUT/i0.log" 2>&1; fi
lap i0
for k in 1 2 3 4 5 6; do
  ALL=$(drcs "$@")
  PREV=$(echo "$ALL" | tr ',' '\n' | tail -1 | xargs dirname)
  FILLS=$PREV/copper-dump.json sh native-21/layout/incr_iter.sh native-21/layout/copper_base.json "$ALL" "$OUT/i$k" > "$OUT/i$k.log" 2>&1
  UN=$(grep "^unconnected" "$OUT/i$k.log")
  B=$(head -1 "$OUT/i$k/barrier.txt" 2>/dev/null)
  E=$(python3 "$G/count_errors.py" "$OUT/i$k/drc.json" 2>/dev/null)
  echo "== i$k $UN | $B | errors $E | $(grep -E 'still open|Traceback|patch (track|via)' "$OUT/i$k.log" | tr '\n' ' ' | cut -c1-160)" | tee -a "$OUT/passes.out"
  lap "i$k"
  case "$UN" in "unconnected 0") [ "$k" -ge 2 ] && [ "$E" = "0" ] && break ;; "") break ;; esac
done
