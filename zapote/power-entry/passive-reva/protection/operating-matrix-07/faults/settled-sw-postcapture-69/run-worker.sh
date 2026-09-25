#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RUNROOT="$ROOT/faults/settled-sw-short-59"
CASE="$RUNROOT/full-SW-SHORT"
OUT="$ROOT/faults/settled-sw-postcapture-69/full-SW-SHORT"
RAW="$CASE/raw.trace.raw.gz"
RESULT="$CASE/result.json"
STAGE1="$CASE/capture-stage1.json"
EXPORT="$CASE/native-export-receipt.json"

test -r "$RUNROOT/runner.exit"; test -r "$RUNROOT/monitor.exit"
runner_status=$(tr -d '[:space:]' < "$RUNROOT/runner.exit")
case "$runner_status" in ''|*[!0-9-]*) exit 1;; esac
test "$(tr -d '[:space:]' < "$RUNROOT/monitor.exit")" -eq 0
test -r "$RESULT"; test -r "$STAGE1"; test -r "$EXPORT"; test -s "$RAW"
jq -e '.transport_complete == true and .raw_trace == "raw.trace.raw.gz" and (.raw_trace_bytes|type == "number" and .raw_trace_bytes > 0) and (.raw_trace_sha256|type == "string" and test("^[a-f0-9]{64}$"))' "$RESULT" >/dev/null
jq -e '.host_success == true and .pigz_success == true and .host_rc == 0 and .pigz_rc == 0 and .metadata_status == "valid" and (.raw_trace_bytes|type == "number" and .raw_trace_bytes > 0) and (.raw_trace_sha256|type == "string" and test("^[a-f0-9]{64}$"))' "$STAGE1" >/dev/null
jq -e '.status == "complete" and .schema == "fault42" and .columns == 42 and (.rows|type == "number" and .rows >= 2) and .copy_avoidance_only == true' "$EXPORT" >/dev/null
jq -e '.case == "SW-SHORT" and .t_fault_s == 0.6541666666667 and .tstop_s == 0.662 and .runner_kind == "switch-short" and .validator_kind == "switch-short"' "$CASE/manifest.json" >/dev/null
jq -e '.output_sha256["case.cir"] == "3ba13389962a9550edcc7ca5486109f4793c6082e94a50fe18f0bc1f6f889ace"' "$CASE/manifest.json" >/dev/null
test "$(stat -f %z "$RAW")" = "$(jq -er '.raw_trace_bytes|tostring' "$RESULT")"
test "$(jq -er '.raw_trace_bytes' "$RESULT")" = "$(jq -er '.raw_trace_bytes' "$STAGE1")"
test "$(jq -er '.raw_trace_sha256' "$RESULT")" = "$(jq -er '.raw_trace_sha256' "$STAGE1")"
test "$(shasum -a 256 "$RAW" | awk '{print $1}')" = "$(jq -er '.raw_trace_sha256' "$RESULT")"

verify_sha() { test -x "$1"; test "$(shasum -a 256 "$1" | awk '{print $1}')" = "$2"; }
PIGZ=/opt/homebrew/bin/pigz; DECODER=/private/tmp/matrix07-fault-native-decoder-parent
SELECTOR=/private/tmp/matrix07-prefault-selector-parent; AUDIT=/private/tmp/matrix07-normal15-event-audit-host
NORMALIZE=/private/tmp/matrix07-normalize; METRICS=/private/tmp/matrix07-event-metrics-host; PHASE=/private/tmp/matrix07-phase43-parent
verify_sha "$PIGZ" a05b6a8ff40a84f8c1fa4052e38a70a682e30f142f5fc7486356134572733a80
verify_sha "$DECODER" af7d186fa543ebd8158947322b6c9049c17534c1662e8b9e9c2df53606b73658
verify_sha "$SELECTOR" c45bfa25ee4468deb2e39e924e4e7c65e89cba22f84d1d708507f2247addd884
verify_sha "$AUDIT" be237328571b5c71c3f5e9f43234a6745941fef4eb6f1baa5b96863a31168ce6
verify_sha "$NORMALIZE" 37f294b9ce4171c665318f857f9d672280e08b4bcf51990d0f29eea9d5cb59ff
verify_sha "$METRICS" 85085e0ade874d198e603a07f387be8440f0436747caea91b3adba38f7285c7c
verify_sha "$PHASE" e546ddfb84c53b73303e465574fa29fdff7753768c3a71efda1f8b5f185be965

mkdir "$OUT"
cleanup() { local rc=$?; if (( rc != 0 )); then rm -f "$OUT/.running"; fi; exit "$rc"; }
trap cleanup EXIT
touch "$OUT/.running"
shasum -a 256 "$RAW" > "$OUT/raw.before.sha256"

set +e
"$PIGZ" -dc "$RAW" 2>"$OUT/scan-pigz.stderr" | "$DECODER" --schema fault42 --byte-order little 2>"$OUT/scan-decoder.stderr" | "$SELECTOR" - - "$OUT/prefault-scan.json" .65 1e-6 --scan-only 2>"$OUT/scan-selector.stderr" >/dev/null
codes=("${PIPESTATUS[@]}"); set -e; printf '%s\n' "${codes[*]}" > "$OUT/scan.exit"; for code in "${codes[@]}"; do test "$code" -eq 0; done
jq -e '.status == "OK" and .last_selected_time_s > 0 and .last_selected_time_s <= 0.65 and .cutoff_gap_s >= 0 and .cutoff_gap_s <= 1e-6 and (.fault_inject_rising_edges|length) == 1' "$OUT/prefault-scan.json" >/dev/null
PREFIX_END=$(jq -er '.last_selected_time_s|numbers' "$OUT/prefault-scan.json")

set +e
"$PIGZ" -dc "$RAW" 2>"$OUT/audit-pigz.stderr" | "$DECODER" --schema fault42 --byte-order little 2>"$OUT/audit-decoder.stderr" | "$SELECTOR" - - "$OUT/audit-selector.json" .65 1e-6 2>"$OUT/audit-selector.stderr" | "$AUDIT" --end-s "$PREFIX_END" --rload 190 --events "$OUT/normal15-events.tsv" >"$OUT/normal15-audit.txt" 2>"$OUT/audit.stderr"
codes=("${PIPESTATUS[@]}"); set -e; printf '%s\n' "${codes[*]}" > "$OUT/audit.exit"; for code in "${codes[@]}"; do test "$code" -eq 0; done

set +e
"$PIGZ" -dc "$RAW" 2>"$OUT/metrics-pigz.stderr" | "$DECODER" --schema fault42 --byte-order little 2>"$OUT/metrics-decoder.stderr" | "$SELECTOR" - - "$OUT/metrics-selector.json" .65 1e-6 2>"$OUT/metrics-selector.stderr" | "$NORMALIZE" 190 2>"$OUT/metrics-normalize.stderr" | "$METRICS" --end-s "$PREFIX_END" >"$OUT/normal-metrics.txt" 2>"$OUT/metrics.stderr"
codes=("${PIPESTATUS[@]}"); set -e; printf '%s\n' "${codes[*]}" > "$OUT/metrics.exit"; for code in "${codes[@]}"; do test "$code" -eq 0; done

set +e
"$PIGZ" -dc "$RAW" 2>"$OUT/phase-pigz.stderr" | "$DECODER" --schema fault42 --byte-order little 2>"$OUT/phase-decoder.stderr" | "$PHASE" --end-s .662 --expected-event-s .6541666666667 --local-start-s .65 --local-end-s .6583333333333 --kind crest --tolerance .01 >"$OUT/phase.json" 2>"$OUT/phase.stderr"
codes=("${PIPESTATUS[@]}"); set -e; printf '%s\n' "${codes[*]}" > "$OUT/phase.exit"; for code in "${codes[@]}"; do test "$code" -eq 0; done

shasum -a 256 "$RAW" > "$OUT/raw.after.sha256"; cmp -s "$OUT/raw.before.sha256" "$OUT/raw.after.sha256"
rm "$OUT/.running"
