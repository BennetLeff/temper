#!/bin/bash
# Fixed F2-ZERO saved-archive analysis. No solver and no circuit acceptance.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PACKET="$ROOT/faults/settled-postcapture-58"
RUNROOT="$ROOT/faults/settled-direct-capture-51"
CASE="$RUNROOT/full-F2-ZERO"
OUT="$PACKET/full-F2-ZERO"
RAW="$CASE/raw.trace.raw.gz"
export ROOT RUNROOT CASE OUT RAW
# Completion records belong to the launch wrapper, beside the case directory.
test -f "$RUNROOT/runner.exit"
test -f "$RUNROOT/monitor.exit"
test -f "$CASE/capture-stage1.json"
test -f "$CASE/stage1.exit"
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
import hashlib,json,os,re
case=Path(os.environ['CASE']); run=Path(os.environ['RUNROOT']); raw=Path(os.environ['RAW'])
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
runner=(run/'runner.exit').read_text().strip()
assert re.fullmatch(r'-?\d+',runner), 'invalid terminal runner record'
assert int((run/'monitor.exit').read_text())==0
assert (case/'stage1.exit').read_text().strip()=='host_rc=0 pigz_rc=0'
stage=json.loads((case/'capture-stage1.json').read_text())
assert stage['host_success'] and stage['pigz_success'] and stage['metadata_status']=='valid'
assert stage['host_rc']==stage['pigz_rc']==0
assert digest(case/'manifest.json')=='c569392b818e638c59b4787353803c094ae552cbd1409b08e184da6eacf8c3a6'
m=json.loads((case/'manifest.json').read_text())
assert m['case']=='F2-ZERO' and m['t_fault_s']==.6583333333333 and m['tstop_s']==.682
assert m['runner_kind']=='f2-zero' and m['validator_kind']=='f2-open'
for name,expected in m['output_sha256'].items():assert digest(case/name)==expected,name
identity=json.loads((case/'source-identity.json').read_text())
for item in identity['input_files']:assert digest(case/item['path'])==item['sha256'],item['path']
meta=json.loads((case/'capture-metadata.json').read_text())
export=json.loads((case/'native-export-receipt.json').read_text())
assert export['status']=='complete' and export['schema']=='fault42' and export['columns']==42
assert meta['points']==export['rows'] and export['rows']>0
raw_hash=digest(raw)
assert raw_hash==stage['raw_trace_sha256'] and raw.stat().st_size==stage['raw_trace_bytes']
result=json.loads((case/'result.json').read_text()) if (case/'result.json').exists() else None
print(json.dumps({'status':'COMPLETE_CAPTURE_BOUND_FOR_ANALYSIS','accepted':False,'runner_exit':int(runner),'capture_stage1':stage,'points':meta['points'],'raw_sha256':raw_hash,'raw_bytes':raw.stat().st_size,'runner_result':result,'phase_interval_s':[.6483333333333,.6683333333333],'note':'Terminal electrical/checker failure does not prevent diagnosis of complete raw capture; it is not waived.'},indent=2))
PY
PIGZ=/opt/homebrew/bin/pigz
DECODER=/private/tmp/matrix07-fault-native-decoder-parent
SELECTOR=/private/tmp/matrix07-prefault-selector-parent
AUDIT=/private/tmp/matrix07-normal15-event-audit-host
NORMALIZE=/private/tmp/matrix07-normalize
METRICS=/private/tmp/matrix07-event-metrics-host
PHASE=/private/tmp/matrix07-phase43-parent
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
import json,os
p=Path(os.environ['OUT']);s=json.loads((p/'prefault-scan.json').read_text());pre=json.loads((p/'preflight.json').read_text())
assert s['status']=='OK' and s['full_rows']==pre['points'] and abs(s['last_time_s']-.682)<=1e-9
assert 0<=s['cutoff_gap_s']<=1e-6 and 0<s['last_selected_time_s']<=.65
assert len(s['fault_inject_rising_edges'])==1
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
set +e
"$PIGZ" -dc "$RAW" 2> "$OUT/phase-pigz.stderr" |
 "$DECODER" --schema fault42 --byte-order little 2> "$OUT/phase-decoder.stderr" |
 "$PHASE" --end-s .682 --expected-event-s .6583333333333 --local-start-s .6483333333333 --local-end-s .6683333333333 --kind zero --tolerance .01 > "$OUT/phase.json" 2> "$OUT/phase.stderr"
codes=("${PIPESTATUS[@]}"); set -e
record_codes phase "${codes[@]}"
python3 - <<'PY' > "$OUT/analysis-receipt.json"
from pathlib import Path
import hashlib,json,os
p=Path(os.environ['OUT']);raw=Path(os.environ['RAW'])
pre=json.loads((p/'preflight.json').read_text())
with raw.open('rb') as f:after=hashlib.file_digest(f,'sha256').hexdigest()
assert after==pre['raw_sha256'] and raw.stat().st_size==pre['raw_bytes']
scans=[json.loads((p/n).read_text()) for n in ['prefault-scan.json','audit-selector.json','metrics-selector.json']]
for s in scans[1:]:
 for key in ['full_rows','selected_rows','first_time_s','last_time_s','last_selected_time_s','cutoff_gap_s','fault_inject_rising_edges']:assert s[key]==scans[0][key],key
print(json.dumps({'status':'COMPLETE_DIAGNOSTICS_PARENT_REVIEW_REQUIRED','accepted':False,'raw_sha256_before_after':after,'raw_bytes':pre['raw_bytes'],'full_rows':scans[0]['full_rows'],'selected_rows':scans[0]['selected_rows'],'prefix_endpoint_s':scans[0]['last_selected_time_s'],'pipeline_exits':{k:[int(x) for x in (p/(k+'.exit')).read_text().split()] for k in ['scan','audit','metrics','phase']}},indent=2))
PY
