#!/bin/bash
set -u
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" 2> "$OUT/scan-pigz.stderr" \
 | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2> "$OUT/scan-decoder.stderr" \
 | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/prefault-scan.json" .65 1e-6 --scan-only 2> "$OUT/scan-selector.stderr" > /dev/null
codes=("${PIPESTATUS[@]}")
printf '%s\n' "${codes[*]}" > "$OUT/scan.exit"
for code in "${codes[@]}"; do test "$code" -eq 0 || exit 1; done
jq -e '.status == "OK" and .full_rows == 32237324 and .last_time_s > 0.661999999 and .last_time_s < 0.662000001 and .cutoff_gap_s >= 0 and .cutoff_gap_s <= 1e-6 and .last_selected_time_s > 0 and .last_selected_time_s <= 0.65 and (.fault_inject_rising_edges|length) == 1' "$OUT/prefault-scan.json"
