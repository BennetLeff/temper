#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CASE="$ROOT/faults/settled-direct-capture-51/full-F2-ZERO"
OUT="$ROOT/faults/settled-postcapture-58/full-F2-ZERO"
RAW="$CASE/raw.trace.raw.gz"
test -r "$CASE/runner.exit"; test -r "$CASE/monitor.exit"; test -r "$CASE/raw-gzip.stderr"
runner_status=$(tr -d '[:space:]' < "$CASE/runner.exit")
case "$runner_status" in ''|*[!0-9-]*) exit 1;; esac
test "$(tr -d '[:space:]' < "$CASE/monitor.exit")" -eq 0
jq -e '.t_fault_s == 0.6583333333333 and .tstop_s == 0.682 and .runner_kind == "f2-zero" and .validator_kind == "f2-open"' "$CASE/manifest.json" >/dev/null
jq -e '.output_sha256["case.cir"] == "b704ebd646dce1da7cf03518478ac1956e3a0bffbae804bd28ff383f4a6fb6c1" and .t_fault_s == 0.6583333333333 and .tstop_s == 0.682' "$CASE/manifest.json" >/dev/null
jq -e '.input_files | map(select(.path == "case.cir" and .sha256 == "b704ebd646dce1da7cf03518478ac1956e3a0bffbae804bd28ff383f4a6fb6c1")) | length == 1' "$CASE/source-identity.json" >/dev/null
test -s "$RAW"
test ! -s "$CASE/raw-gzip.stderr"

PIGZ=/opt/homebrew/bin/pigz
DECODER=/private/tmp/matrix07-fault-native-decoder-parent
SELECTOR=/private/tmp/matrix07-prefault-selector-parent
AUDIT=/private/tmp/matrix07-normal15-event-audit-host
NORMALIZE=/private/tmp/matrix07-normalize
METRICS=/private/tmp/matrix07-event-metrics-host
PHASE=/private/tmp/matrix07-phase43-parent
declare -A TOOL_SHA=(
  ["$PIGZ"]="a05b6a8ff40a84f8c1fa4052e38a70a682e30f142f5fc7486356134572733a80"
  ["$DECODER"]="af7d186fa543ebd8158947322b6c9049c17534c1662e8b9e9c2df53606b73658"
  ["$SELECTOR"]="c45bfa25ee4468deb2e39e924e4e7c65e89cba22f84d1d708507f2247addd884"
  ["$AUDIT"]="be237328571b5c71c3f5e9f43234a6745941fef4eb6f1baa5b96863a31168ce6"
  ["$NORMALIZE"]="37f294b9ce4171c665318f857f9d672280e08b4bcf51990d0f29eea9d5cb59ff"
  ["$METRICS"]="85085e0ade874d198e603a07f387be8440f0436747caea91b3adba38f7285c7c"
  ["$PHASE"]="e546ddfb84c53b73303e465574fa29fdff7753768c3a71efda1f8b5f185be965"
)
for tool in "${!TOOL_SHA[@]}"; do test -x "$tool"; test "$(shasum -a 256 "$tool" | awk '{print $1}')" = "${TOOL_SHA[$tool]}"; done

mkdir "$OUT"
trap 'rc=$?; if (( rc != 0 )); then rm -f "$OUT/.running"; fi; exit "$rc"' EXIT
touch "$OUT/.running"
shasum -a 256 "$RAW" >"$OUT/raw.before.sha256"

set +e
"$PIGZ" -dc "$RAW" 2>"$OUT/scan-pigz.stderr" |
  "$DECODER" --schema fault42 --byte-order little 2>"$OUT/scan-decoder.stderr" |
  "$SELECTOR" - - "$OUT/prefault-scan.json" .65 1e-6 --scan-only 2>"$OUT/scan-selector.stderr" >/dev/null
codes=("${PIPESTATUS[@]}"); set -e
printf '%s\n' "${codes[*]}" >"$OUT/scan.exit"
for code in "${codes[@]}"; do test "$code" -eq 0; done
jq -e '.status == "OK" and .last_selected_time_s > 0 and .last_selected_time_s <= 0.65 and .cutoff_gap_s >= 0 and .cutoff_gap_s <= 1e-6 and (.fault_inject_rising_edges|length) == 1' "$OUT/prefault-scan.json" >/dev/null
PREFIX_END=$(jq -er '.last_selected_time_s|numbers' "$OUT/prefault-scan.json")

set +e
"$PIGZ" -dc "$RAW" 2>"$OUT/audit-pigz.stderr" | "$DECODER" --schema fault42 --byte-order little 2>"$OUT/audit-decoder.stderr" | "$SELECTOR" - - "$OUT/audit-selector.json" .65 1e-6 2>"$OUT/audit-selector.stderr" | "$AUDIT" --end-s "$PREFIX_END" --rload 190 --events "$OUT/normal15-events.tsv" >"$OUT/normal15-audit.txt" 2>"$OUT/audit.stderr"
codes=("${PIPESTATUS[@]}"); set -e; printf '%s\n' "${codes[*]}" >"$OUT/audit.exit"; for code in "${codes[@]}"; do test "$code" -eq 0; done

set +e
"$PIGZ" -dc "$RAW" 2>"$OUT/metrics-pigz.stderr" | "$DECODER" --schema fault42 --byte-order little 2>"$OUT/metrics-decoder.stderr" | "$SELECTOR" - - "$OUT/metrics-selector.json" .65 1e-6 2>"$OUT/metrics-selector.stderr" | "$NORMALIZE" 190 2>"$OUT/metrics-normalize.stderr" | "$METRICS" --end-s "$PREFIX_END" >"$OUT/normal-metrics.txt" 2>"$OUT/metrics.stderr"
codes=("${PIPESTATUS[@]}"); set -e; printf '%s\n' "${codes[*]}" >"$OUT/metrics.exit"; for code in "${codes[@]}"; do test "$code" -eq 0; done

set +e
"$PIGZ" -dc "$RAW" 2>"$OUT/phase-pigz.stderr" | "$DECODER" --schema fault42 --byte-order little 2>"$OUT/phase-decoder.stderr" | "$PHASE" --end-s .682 --expected-event-s .6583333333333 --local-start-s .65 --local-end-s .6583333333333 --kind zero --tolerance .01 >"$OUT/phase.json" 2>"$OUT/phase.stderr"
codes=("${PIPESTATUS[@]}"); set -e; printf '%s\n' "${codes[*]}" >"$OUT/phase.exit"; for code in "${codes[@]}"; do test "$code" -eq 0; done

shasum -a 256 "$RAW" >"$OUT/raw.after.sha256"
cmp -s "$OUT/raw.before.sha256" "$OUT/raw.after.sha256"
rm "$OUT/.running"
