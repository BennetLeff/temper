#!/bin/bash
# Record the frozen legacy strict-checker result for the completed DIODE-SHORT scan.
# This is deliberately separate from run.sh and never changes the event-aware
# reports or promotes a strict-checker result to acceptance.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RUNROOT="$ROOT/faults/settled-diode-short-64"
CASE="$RUNROOT/full-DIODE-SHORT"
POST="$ROOT/faults/settled-diode-postcapture-74/full-DIODE-SHORT"
OUT="$POST/legacy-strict"
RAW="$CASE/raw.trace.raw.gz"
PREFLIGHT="$POST/preflight.json"
SCAN="$POST/prefault-scan.json"

PIGZ=/opt/homebrew/bin/pigz
DECODER=/private/tmp/matrix07-fault-native-decoder-parent
SELECTOR=/private/tmp/matrix07-prefault-selector-parent
NORMALIZE=/private/tmp/matrix07-normalize
CHECKER=/private/tmp/matrix07-checker

# These are the already approved identities used by the parent packet and the
# historical legacy-strict receipt. Do not substitute a locally built binary.
CHECKER_SHA=24c95bea81b44a3d5038a32552297afed17547fcd1b3ddcfd99434e84638b85c

test -f "$RUNROOT/runner.exit"
test -f "$RUNROOT/monitor.exit"
test -f "$CASE/source-identity.json"
test -f "$PREFLIGHT"
test -f "$SCAN"
test -f "$POST/analysis.exit"
test -f "$POST/analysis-receipt.json"
test -r "$RAW"
test ! -e "$OUT"

runner_status=$(tr -d '[:space:]' < "$RUNROOT/runner.exit")
if ! [[ "$runner_status" =~ ^-?[0-9]+$ ]]; then exit 1; fi
test "$(tr -d '[:space:]' < "$RUNROOT/monitor.exit")" -eq 0
test "$(tr -d '[:space:]' < "$POST/analysis.exit")" -eq 0
jq -e '.accepted == false' "$POST/analysis-receipt.json" >/dev/null

check_space() {
  local available
  available=$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')
  case "$available" in ''|*[!0-9]*) exit 1;; esac
  test "$available" -ge 10485760
}
check_space

# run.sh owns the complete-capture/source closure. Require its terminal
# preflight hash and the immutable source identity before opening the archive.
RAW_SHA=$(shasum -a 256 "$RAW" | awk '{print $1}')
RAW_BYTES=$(wc -c < "$RAW" | tr -d '[:space:]')
jq -e --arg sha "$RAW_SHA" --argjson bytes "$RAW_BYTES" \
  '.status == "COMPLETE_CAPTURE_BOUND_FOR_ANALYSIS" and .raw_sha256 == $sha and .raw_bytes == $bytes' \
  "$PREFLIGHT" >/dev/null
python3 - "$CASE" <<'PY'
import hashlib
import json
import pathlib
import sys

case = pathlib.Path(sys.argv[1])
identity = json.loads((case / "source-identity.json").read_text())
manifest = json.loads((case / "manifest.json").read_text())
for item in identity["input_files"]:
    path = case / item["path"]
    digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
    assert digest == item["sha256"], item["path"]
for name, expected in manifest["output_sha256"].items():
    digest = hashlib.file_digest((case / name).open("rb"), "sha256").hexdigest()
    assert digest == expected, name
PY
python3 - "$SCAN" <<'PY'
import json
import sys

# Match the selector's binary64 parameters exactly. jq's decimal comparison
# distinguishes its round-trip f64 rendering from the CLI decimal literal.
with open(sys.argv[1]) as source:
    scan = json.load(source)
assert scan['status'] == 'OK'
assert scan['cutoff_s'] == 0.65
assert scan['max_cutoff_gap_s'] == 1e-6
assert 0 < scan['last_selected_time_s'] <= 0.65
assert 0 <= scan['cutoff_gap_s'] <= 1e-6
assert len(scan['fault_inject_rising_edges']) == 1
PY

shasum -a 256 -c "$ROOT/faults/settled-diode-postcapture-74/tools-parent.sha256" >/dev/null
test -x "$CHECKER"
test "$(shasum -a 256 "$CHECKER" | awk '{print $1}')" = "$CHECKER_SHA"

PREFIX_END=$(jq -er '.last_selected_time_s|numbers' "$SCAN")
mkdir "$OUT"
cleanup() {
  rc=$?
  if test "$rc" -ne 0; then rm -f "$OUT/.running"; fi
  exit "$rc"
}
trap cleanup EXIT
touch "$OUT/.running"
printf '%s\n' "$RAW_SHA" > "$OUT/raw.before.sha256"

set +e
"$PIGZ" -dc "$RAW" 2> "$OUT/pigz.stderr" \
  | "$DECODER" --schema fault42 --byte-order little 2> "$OUT/decoder.stderr" \
  | "$SELECTOR" - - "$OUT/selector.json" .65 1e-6 2> "$OUT/selector.stderr" \
  | "$NORMALIZE" 190 2> "$OUT/normalizer.stderr" \
  | "$CHECKER" --end-s "$PREFIX_END" > "$OUT/checker.stdout" 2> "$OUT/checker.stderr"
codes=("${PIPESTATUS[@]}")
set -e
printf '%s\n' "${codes[*]}" > "$OUT/pipeline.exit"

RAW_AFTER=$(shasum -a 256 "$RAW" | awk '{print $1}')
printf '%s\n' "$RAW_AFTER" > "$OUT/raw.after.sha256"
test "$RAW_SHA" = "$RAW_AFTER"

# Classify only what was observed. In particular, EPIPE/141 upstream of a
# checker rejection is retained as transport fallout and is never acceptance.
if test "${codes[4]}" -eq 1 && rg -q '^REJECTED: line [0-9]+: time not strictly increasing$' "$OUT/checker.stderr"; then
  STATUS=EXPECTED_STRICT_REJECTION
  REASON=REPEATED_TIMESTAMP
elif test "${codes[0]}" -eq 0 && test "${codes[1]}" -eq 0 && test "${codes[2]}" -eq 0 && test "${codes[3]}" -eq 0 && test "${codes[4]}" -eq 0; then
  STATUS=DIAGNOSTIC_PIPELINE_COMPLETE
  REASON=ALL_PIPELINE_STATUSES_ZERO
else
  STATUS=PIPELINE_REVIEW_PENDING
  REASON=UNEXPECTED_PIPELINE_STATUS_OR_CHECKER_TEXT
fi
python3 - "$OUT" "$RAW_SHA" "$RAW_AFTER" "$PREFIX_END" "$runner_status" "$STATUS" "$REASON" <<'PY'
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
codes = [int(value) for value in (out / "pipeline.exit").read_text().split()]
receipt = {
    "status": sys.argv[6],
    "accepted": False,
    "classification_reason": sys.argv[7],
    "raw_before_sha256": sys.argv[2],
    "raw_after_sha256": sys.argv[3],
    "pipeline_status_order": ["pigz", "decoder", "selector", "normalizer", "checker"],
    "pipeline_statuses": codes,
    "checker_stderr": "checker.stderr",
    "prefix_end_s": sys.argv[4],
    "runner_exit": int(sys.argv[5]),
    "transport_failures_are_not_acceptance": True,
}
(out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
PY
rm "$OUT/.running"
