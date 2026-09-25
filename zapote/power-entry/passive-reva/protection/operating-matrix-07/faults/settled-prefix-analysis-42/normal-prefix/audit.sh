#!/bin/bash
set -u
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" 2> "$OUT/audit-pigz.stderr" \
 | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2> "$OUT/audit-decoder.stderr" \
 | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/audit-selector.json" .65 1e-6 2> "$OUT/audit-selector.stderr" \
 | /private/tmp/matrix07-normal15-event-audit-host --end-s "$PREFIX_END" --rload 190 --events "$OUT/normal15-events.tsv" > "$OUT/normal15-audit.txt" 2> "$OUT/audit.stderr"
codes=("${PIPESTATUS[@]}")
printf '%s\n' "${codes[*]}" > "$OUT/audit.exit"
for code in "${codes[@]}"; do test "$code" -eq 0 || exit 1; done
