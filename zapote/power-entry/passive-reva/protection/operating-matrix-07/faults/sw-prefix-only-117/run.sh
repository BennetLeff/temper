#!/bin/bash
# SW-SHORT partial-capture prefix diagnostics only. No full-fault acceptance.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PACKET="$ROOT/faults/sw-prefix-only-117"
RUNROOT="$ROOT/faults/settled-sw-short-59"
CASE="$RUNROOT/full-SW-SHORT"
OUT="$PACKET/full-SW-SHORT"
RAW="$CASE/raw.trace.raw.gz"
export ROOT RUNROOT CASE OUT RAW

test -f "$RUNROOT/runner.exit"
test -f "$RUNROOT/monitor.exit"
test -f "$CASE/capture-stage1.json"
test -f "$CASE/stage1.exit"
test -f "$CASE/parent-disposition-80.json"
test ! -e "$OUT"
shasum -a 256 -c "$PACKET/tools-parent.sha256"

check_space() {
  local available
  available=$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')
  case "$available" in ''|*[!0-9]*) return 77;; esac
  test "$available" -ge 10485760
}
check_space
mkdir "$OUT"
set -C
record_exit() {
  local analysis_status=$?
  printf '%s\n' "$analysis_status" > "$OUT/analysis.exit"
}
trap record_exit EXIT

python3 - <<'PY' > "$OUT/preflight.json"
from pathlib import Path
import hashlib, json, os, re

case = Path(os.environ['CASE']); run = Path(os.environ['RUNROOT']); raw = Path(os.environ['RAW'])
def digest(path):
    with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
runner = (run/'runner.exit').read_text().strip()
assert re.fullmatch(r'-?\d+', runner), 'invalid terminal runner record'
assert int((run/'monitor.exit').read_text()) == 0
assert (case/'stage1.exit').read_text().strip() == 'host_rc=0 pigz_rc=0'
stage = json.loads((case/'capture-stage1.json').read_text())
assert stage['host_success'] and stage['pigz_success'] and stage['metadata_status'] == 'valid'
assert stage['host_rc'] == stage['pigz_rc'] == 0
assert digest(case/'manifest.json') == '840b9fbbf83bc91a8138bfd18101b55306146e21445968ccbbaa3864068679ad'
m = json.loads((case/'manifest.json').read_text())
assert m['case'] == 'SW-SHORT' and m['t_fault_s'] == .6541666666667 and m['tstop_s'] == .662
assert m['runner_kind'] == 'switch-short' and m['validator_kind'] == 'switch-short'
params = json.loads((case/'run-parameters.json').read_text())
assert params == {'tstop_s':.662,'kind':'switch-short','mutation_s':.6541666666667,'event_window_s':.002,'expected_fault_s':.6541666666667,'observation_s':.002,'turnoff_s':.000002,'max_gap_s':.000000025,'wall_seconds':3600,'export_timeout_s':900,'bypass':False}
for name, expected in m['output_sha256'].items(): assert digest(case/name) == expected, name
identity = json.loads((case/'source-identity.json').read_text())
for item in identity['input_files']: assert digest(case/item['path']) == item['sha256'], item['path']
meta = json.loads((case/'capture-metadata.json').read_text())
export = json.loads((case/'native-export-receipt.json').read_text())
disp = json.loads((case/'parent-disposition-80.json').read_text())
result = json.loads((case/'result.json').read_text())
verdict = json.loads((case/'campaign-verdict-86.json').read_text())
assert meta['stop_reason'] == 'solver_stopped' and meta['points'] == 30686230 and meta['accepted'] is False
assert export['status'] == 'complete' and export['schema'] == 'fault42' and export['columns'] == 42 and export['rows'] == 30686230
assert disp['status'] == 'REJECTED_INCOMPLETE_NUMERICAL_ABORT' and disp['accepted'] is False
assert disp['observed_stop_s'] == .6544026486296868 and disp['required_end_s'] == .662 and disp['runner_exit'] == int(runner)
assert result['status'] == 'REVIEW_PENDING' and result['acceptance'] is False
assert verdict['campaign_verdict'] == 'INDETERMINATE' and verdict['accepted'] is False
assert digest(raw) == '726acb2f278c1e53fda082da6f4e504b116c9a4b398e4490cfb9ddc4bbac60aa' and raw.stat().st_size == 5088782620
print(json.dumps({'status':'COMPLETE_PARTIAL_CAPTURE_BOUND_PREFIX_ONLY','accepted':False,'runner_exit':int(runner),'monitor_exit':0,'raw_sha256':'726acb2f278c1e53fda082da6f4e504b116c9a4b398e4490cfb9ddc4bbac60aa','raw_bytes':5088782620,'full_rows':30686230,'observed_stop_s':.6544026486296868,'required_end_s':.662,'normal_prefix_cutoff_s':.65,'note':'Incomplete full endpoint is preserved; this packet diagnoses only the complete prefix through .65 s.'}, indent=2))
PY

PIGZ=/opt/homebrew/bin/pigz
DECODER=/private/tmp/matrix07-fault-native-decoder-parent
SELECTOR=/private/tmp/matrix07-prefault-selector-parent
AUDIT=/private/tmp/matrix07-normal15-event-audit-host
NORMALIZE=/private/tmp/matrix07-normalize
METRICS=/private/tmp/matrix07-event-metrics-host
CHECKER=/private/tmp/matrix07-checker
CHECKER_SHA=24c95bea81b44a3d5038a32552297afed17547fcd1b3ddcfd99434e84638b85c

"$PIGZ" -t "$RAW" 2> "$OUT/gzip-integrity.stderr"
printf '0\n' > "$OUT/gzip-integrity.exit"
record_codes() {
  local stage="$1" code
  shift
  printf '%s\n' "$*" > "$OUT/$stage.exit"
  for code in "$@"; do test "$code" -eq 0 || return 1; done
}
check_space
set +e
"$PIGZ" -dc "$RAW" 2> "$OUT/scan-pigz.stderr" |
 "$DECODER" --schema fault42 --byte-order little 2> "$OUT/scan-decoder.stderr" |
 "$SELECTOR" - - "$OUT/prefault-scan.json" .65 1e-6 --scan-only 2> "$OUT/scan-selector.stderr" > /dev/null
codes=("${PIPESTATUS[@]}"); set -e
record_codes scan "${codes[@]}"
python3 - <<'PY'
from pathlib import Path
import json, os
p = Path(os.environ['OUT']); s = json.loads((p/'prefault-scan.json').read_text()); pre = json.loads((p/'preflight.json').read_text())
assert s['status'] == 'OK' and s['full_rows'] == pre['full_rows']
assert abs(s['last_time_s'] - pre['observed_stop_s']) <= 1e-9
assert 0 < s['last_selected_time_s'] <= .65 and 0 <= s['cutoff_gap_s'] <= 1e-6
assert len(s['fault_inject_rising_edges']) == 1
PY
PREFIX_END=$(jq -er '.last_selected_time_s|numbers' "$OUT/prefault-scan.json")

check_space
set +e
"$PIGZ" -dc "$RAW" 2> "$OUT/audit-pigz.stderr" |
 "$DECODER" --schema fault42 --byte-order little 2> "$OUT/audit-decoder.stderr" |
 "$SELECTOR" - - "$OUT/audit-selector.json" .65 1e-6 2> "$OUT/audit-selector.stderr" |
 "$AUDIT" --end-s "$PREFIX_END" --rload 190 --events "$OUT/normal15-events.tsv" > "$OUT/normal15-audit.txt" 2> "$OUT/audit.stderr"
codes=("${PIPESTATUS[@]}"); set -e
record_codes audit "${codes[@]}"

check_space
set +e
"$PIGZ" -dc "$RAW" 2> "$OUT/metrics-pigz.stderr" |
 "$DECODER" --schema fault42 --byte-order little 2> "$OUT/metrics-decoder.stderr" |
 "$SELECTOR" - - "$OUT/metrics-selector.json" .65 1e-6 2> "$OUT/metrics-selector.stderr" |
 "$NORMALIZE" 190 2> "$OUT/metrics-normalize.stderr" |
 "$METRICS" --end-s "$PREFIX_END" > "$OUT/normal-metrics.txt" 2> "$OUT/metrics.stderr"
codes=("${PIPESTATUS[@]}"); set -e
record_codes metrics "${codes[@]}"

check_space
test -x "$CHECKER"
test "$(shasum -a 256 "$CHECKER" | awk '{print $1}')" = "$CHECKER_SHA"
RAW_BEFORE=$(shasum -a 256 "$RAW" | awk '{print $1}')
RAW_BYTES=$(wc -c < "$RAW" | tr -d '[:space:]')
mkdir "$OUT/legacy-strict"
printf '%s\n' "$RAW_BEFORE" > "$OUT/legacy-strict/raw.before.sha256"
set +e
"$PIGZ" -dc "$RAW" 2> "$OUT/legacy-strict/pigz.stderr" |
 "$DECODER" --schema fault42 --byte-order little 2> "$OUT/legacy-strict/decoder.stderr" |
 "$SELECTOR" - - "$OUT/legacy-strict/selector.json" .65 1e-6 2> "$OUT/legacy-strict/selector.stderr" |
 "$NORMALIZE" 190 2> "$OUT/legacy-strict/normalizer.stderr" |
 "$CHECKER" --end-s "$PREFIX_END" > "$OUT/legacy-strict/checker.stdout" 2> "$OUT/legacy-strict/checker.stderr"
codes=("${PIPESTATUS[@]}"); set -e
printf '%s\n' "${codes[*]}" > "$OUT/legacy-strict/pipeline.exit"
RAW_AFTER=$(shasum -a 256 "$RAW" | awk '{print $1}')
printf '%s\n' "$RAW_AFTER" > "$OUT/legacy-strict/raw.after.sha256"
test "$RAW_BEFORE" = "$RAW_AFTER" && test "$RAW_BYTES" = "$(wc -c < "$RAW" | tr -d '[:space:]')"
if test "${codes[4]}" -eq 1 && rg -q '^REJECTED: line [0-9]+: time not strictly increasing$' "$OUT/legacy-strict/checker.stderr"; then
  LEGACY_STATUS=EXPECTED_STRICT_REJECTION; LEGACY_REASON=REPEATED_TIMESTAMP
elif test "${codes[0]}" -eq 0 && test "${codes[1]}" -eq 0 && test "${codes[2]}" -eq 0 && test "${codes[3]}" -eq 0 && test "${codes[4]}" -eq 0; then
  LEGACY_STATUS=DIAGNOSTIC_PIPELINE_COMPLETE; LEGACY_REASON=ALL_PIPELINE_STATUSES_ZERO
else
  LEGACY_STATUS=PIPELINE_REVIEW_PENDING; LEGACY_REASON=UNEXPECTED_PIPELINE_STATUS_OR_CHECKER_TEXT
fi
python3 - "$OUT" "$RAW_BEFORE" "$RAW_AFTER" "$PREFIX_END" "$LEGACY_STATUS" "$LEGACY_REASON" <<'PY'
import json, pathlib, sys
out = pathlib.Path(sys.argv[1]); codes = [int(x) for x in (out/'legacy-strict/pipeline.exit').read_text().split()]
(out/'legacy-strict/receipt.json').write_text(json.dumps({'status':sys.argv[5],'accepted':False,'classification_reason':sys.argv[6],'raw_before_sha256':sys.argv[2],'raw_after_sha256':sys.argv[3],'pipeline_status_order':['pigz','decoder','selector','normalizer','checker'],'pipeline_statuses':codes,'prefix_end_s':sys.argv[4],'transport_failures_are_not_acceptance':True}, indent=2) + '\n')
PY

python3 - <<'PY' > "$OUT/analysis-receipt.json"
from pathlib import Path
import hashlib, json, os
p = Path(os.environ['OUT']); raw = Path(os.environ['RAW']); pre = json.loads((p/'preflight.json').read_text())
after = hashlib.file_digest(raw.open('rb'), 'sha256').hexdigest()
assert after == pre['raw_sha256'] and raw.stat().st_size == pre['raw_bytes']
scans = [json.loads((p/n).read_text()) for n in ['prefault-scan.json','audit-selector.json','metrics-selector.json']]
for s in scans[1:]:
    for key in ['full_rows','selected_rows','first_time_s','last_time_s','last_selected_time_s','cutoff_gap_s','fault_inject_rising_edges']: assert s[key] == scans[0][key], key
legacy = json.loads((p/'legacy-strict/receipt.json').read_text())
print(json.dumps({'status':'COMPLETE_PREFIX_DIAGNOSTIC_PARENT_REVIEW_REQUIRED','accepted':False,'incomplete_full_endpoint_preserved':True,'raw_sha256_before_after':after,'raw_bytes':pre['raw_bytes'],'full_rows':scans[0]['full_rows'],'selected_rows':scans[0]['selected_rows'],'prefix_endpoint_s':scans[0]['last_selected_time_s'],'partial_stop_s':pre['observed_stop_s'],'pipeline_exits':{'scan': [int(x) for x in (p/'scan.exit').read_text().split()],'audit':[int(x) for x in (p/'audit.exit').read_text().split()],'metrics':[int(x) for x in (p/'metrics.exit').read_text().split()],'legacy':[int(x) for x in (p/'legacy-strict/pipeline.exit').read_text().split()]},'legacy_status':legacy['status'],'scope':'Own cold-start normal prefix only; no full-fault endpoint, phase43, observation55, protection acceptance, or hardware claim.'}, indent=2))
PY
