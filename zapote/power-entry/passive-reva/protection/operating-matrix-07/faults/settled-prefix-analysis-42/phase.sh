#!/bin/bash
set -u
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" 2> "$OUT/phase-pigz.stderr" \
 | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2> "$OUT/phase-decoder.stderr" \
 | /private/tmp/matrix07-phase-audit35-parent --end-s .662 --expected-event-s .6541666666667 --local-start-s .65 --local-end-s .6583333333333 --kind crest --tolerance .01 > "$OUT/phase-audit.json" 2> "$OUT/phase-audit.stderr"
codes=("${PIPESTATUS[@]}")
printf '%s\n' "${codes[*]}" > "$OUT/phase.exit"
for code in "${codes[@]}"; do test "$code" -eq 0 || exit 1; done
