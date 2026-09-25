#!/bin/bash
set -u
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" 2> "$OUT/metrics-pigz.stderr" \
 | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2> "$OUT/metrics-decoder.stderr" \
 | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/metrics-selector.json" .65 1e-6 2> "$OUT/metrics-selector.stderr" \
 | /private/tmp/matrix07-normalize 190 2> "$OUT/metrics-normalize.stderr" \
 | /private/tmp/matrix07-event-metrics-host --end-s "$PREFIX_END" > "$OUT/normal-metrics.txt" 2> "$OUT/metrics.stderr"
codes=("${PIPESTATUS[@]}")
printf '%s\n' "${codes[*]}" > "$OUT/metrics.exit"
for code in "${codes[@]}"; do test "$code" -eq 0 || exit 1; done
