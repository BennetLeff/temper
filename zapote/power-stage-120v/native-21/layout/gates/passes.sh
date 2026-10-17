#!/bin/sh
# Native-21 incremental routing passes on a frozen base: BASE + the open pairs KiCad reports, until a pass is clean.
#   sh native-21/layout/gates/passes.sh OUTROOT [BASE.json [FIRST_FILLS.json]]
# BASE defaults to the accepted native-21/layout/copper.json, snapshotted to OUTROOT/base.json first (every pass
# rewrites copper.json, so each pass starts from the same base). The base is routed frozen (INCR21_FROZEN: nothing of
# it is removed or moved); INCR21_PRUNE=1 also drops base copper of parts moved since, with BASE's stem + "_pads.json"
# beside it (incr21.load). Pass k joins the open pairs of passes 1..k-1. Test points stay off the board while routing
# (BOARD_ONLY21_NO_TEST_POINTS): they sit on copper of the last pass and chain.sh re-plans them. Stops at the first pass
# with 0 unconnected and 0 errors, else after 5. The pass builds check without the creepage constraints (DRC_FAST,
# gates/drc_rules_fast.py; DRC_FAST= runs the full rules); chain.sh's build runs them all. reference-labels.json is
# restored at the end (the test-point labels move while the test points are off). Each pass can repair pour cuts
# before its DRC when INCR21_SETTLE=N is set (incr_iter.sh; off by default, gates/README.md). Writes OUTROOT/passes.out; the
# last pass's copper is left in native-21/layout/copper.json (copy it aside before any git checkout).
# Stage 33 replaced the stage 1-32 method (copper_base.json + every patch, which no longer builds: unknown net rect_p);
# the candidates' passes33/38/40.sh copies of that method are this script with their own BASE.
U=$(cd "$(dirname "$0")/../../.." && pwd)
G=$U/native-21/layout/gates
OUT=$1; BASE=${2:-}; FILLS=${3:-}
mkdir -p "$OUT"; cd "$U"
. "$G/laps.sh"; laps_init passes "$OUT/steps.jsonl"
if [ -z "$BASE" ]; then BASE=$OUT/base.json; cp native-21/layout/copper.json "$BASE"; fi
ALL=$OUT/empty-drc.json
echo '{"violations": [], "unconnected_items": []}' > "$ALL"
export INCR21_FROZEN=1 BOARD_ONLY21_NO_TEST_POINTS=1 DRC_FAST=${DRC_FAST-1} INCR21_SETTLE=${INCR21_SETTLE-0}
cp native-21/reference-labels.json "$OUT/reference-labels.json"
trap 'cp "$OUT/reference-labels.json" native-21/reference-labels.json' EXIT
for k in 1 2 3 4 5; do
  FILLS=$FILLS sh native-21/layout/incr_iter.sh "$BASE" "$ALL" "$OUT/i$k" > "$OUT/i$k.log" 2>&1
  UN=$(grep "^unconnected" "$OUT/i$k.log")
  E=$(python3 "$G/count_errors.py" "$OUT/i$k/drc.json" 2>/dev/null)
  echo "== i$k $UN | $(head -1 "$OUT/i$k/barrier.txt" 2>/dev/null) | errors $E | $(grep -E 'still open|Traceback|patch (track|via)' "$OUT/i$k.log" | tr '\n' ' ' | cut -c1-400)" | tee -a "$OUT/passes.out"
  lap "i$k"
  case "$UN" in "unconnected 0") [ "$E" = "0" ] && break ;; "") break ;; esac
  ALL="$ALL,$OUT/i$k/drc.json"; FILLS=$OUT/i$k/copper-dump.json
done
