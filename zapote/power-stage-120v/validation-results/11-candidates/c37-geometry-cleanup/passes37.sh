#!/bin/sh
# Candidate 37: the stage-37 track-geometry cleanup (native-21/layout/track_cleanup21.py, DECISIONS 43 "Fix (planned)") on
# the board of record's routed copper, then one build of the cleaned copper to read KiCad's DRC before the chain.
#   sh passes37.sh BASE_COPPER.json BASE_EXPORT.json.gz OUTDIR
# BASE_COPPER = stage 35's native-21/layout/copper.json (085c80be...; `git show 8bf12675c:zapote/power-stage-120v/native-21/layout/copper.json`)
# BASE_EXPORT = the all-copper export of the board built from it (native-21/verification/native21s35-all-copper.json.gz,
#               board fba59ef3); the tool refuses an export whose tracks are not BASE_COPPER's segments.
# Writes native-21/layout/copper.json (the cleaned copper), OUTDIR/cleanup.json (the edit report) and OUTDIR/b (the build).
# Then: sh native-21/layout/gates/chain.sh native21s37 OUTDIR/b BUILDDIR.
set -e
U=$(cd "$(dirname "$0")/../../.." && pwd)
BASE=$1; EXPORT=$2; OUT=$3
mkdir -p "$OUT"; cd "$U"
python3 native-21/layout/track_cleanup21.py "$BASE" "$EXPORT" --out native-21/layout/copper.json --report "$OUT/cleanup.json"
sh native-21/layout/incr_iter.sh native-21/layout/copper.json - "$OUT/b" > "$OUT/b.log" 2>&1
grep -E "^unconnected|^violations|barrier" "$OUT/b.log"
echo "errors $(python3 native-21/layout/gates/count_errors.py "$OUT/b/drc.json")"
