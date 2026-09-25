#!/bin/bash
set -euo pipefail
cd /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07
PACKET="$PWD/faults/coincident-stress-observability-99"
CASE="$PWD/faults/settled-both-short-65/full-BOTH-SHORT"
POST="$PWD/faults/settled-both-postcapture-75/full-BOTH-SHORT"
OUT="$PACKET/full-BOTH-SHORT"
RAW="$CASE/raw.trace.raw.gz"
export PACKET CASE POST OUT RAW
check_space() { test "$(df -Pk . | awk 'NR==2 {print $4}')" -ge 10485760; }
check_space
test "$(cat "$POST/analysis.exit")" = 0
test ! -e "$OUT"
shasum -a 256 -c "$PACKET/tools-parent.sha256"
mkdir "$OUT"
set -C
record_exit() {
  local analysis_status=$?
  printf '%s\n' "$analysis_status" > "$OUT/analysis.exit"
}
trap record_exit EXIT
python3 - <<'PY' > "$OUT/preflight.json"
from pathlib import Path
import os,json,hashlib
raw=Path(os.environ['RAW']);case=Path(os.environ['CASE']);post=Path(os.environ['POST'])
a=json.loads((post/'analysis-receipt.json').read_text());legacy=json.loads((post/'legacy-strict/receipt.json').read_text())
assert a['status']=='COMPLETE_DIAGNOSTICS_PARENT_REVIEW_REQUIRED' and a['accepted'] is False
assert a['full_rows']==32036953
assert legacy['status']=='EXPECTED_STRICT_REJECTION'
assert a['raw_sha256_before_after']==legacy['raw_after_sha256']=='52b33da8bbb29fd1038e575fd0d79c950ce086f4ad0b619903334164e66f7166'
assert raw.stat().st_size==a['raw_bytes']==5286116925
with raw.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
assert h==a['raw_sha256_before_after']
identity=json.loads((case/'source-identity.json').read_text())
for e in identity['input_files']:
 assert hashlib.sha256((case/e['path']).read_bytes()).hexdigest()==e['sha256']
print(json.dumps({'raw_sha256':h,'raw_bytes':raw.stat().st_size,'rows':a['full_rows'],'accepted':False},indent=2))
PY
check_space
set +e
/opt/homebrew/bin/pigz -dc "$RAW" 2> "$OUT/pigz.stderr" |
 /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2> "$OUT/decoder.stderr" |
 /private/tmp/matrix07-coincident99-parent - "$OUT/observations.json" 2> "$OUT/observe.stderr"
codes=("${PIPESTATUS[@]}")
set -e
printf '%s\n' "${codes[*]}" > "$OUT/pipeline.exit"
for code in "${codes[@]}"; do test "$code" -eq 0; done
python3 - <<'PY' > "$OUT/receipt.json"
from pathlib import Path
import os,json,hashlib
out=Path(os.environ['OUT']);post=Path(os.environ['POST']);raw=Path(os.environ['RAW'])
p=json.loads((out/'preflight.json').read_text());new=json.loads((out/'observations.json').read_text());old=json.loads((post/'post-injection-observations.json').read_text())
extra=new['post_injection'].pop('coincident_currents')
assert new==old, 'Original55 observations changed'
assert new['rows']==p['rows']==32036953 and new['accepted'] is False
with raw.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
assert h==p['raw_sha256'] and raw.stat().st_size==p['raw_bytes']
print(json.dumps({'status':'COMPLETE_COINCIDENT_DIAGNOSTIC_PARENT_REVIEW_REQUIRED','accepted':False,'raw_sha256_before_after':h,'raw_bytes':p['raw_bytes'],'rows':new['rows'],'pipeline_exits':[0,0,0],'all_original55_fields_identical':True,'current_channels':list(extra),'report_sha256':hashlib.sha256((out/'observations.json').read_bytes()).hexdigest(),'limitations':'Same-row sampled observations only, not continuous retention, causality, physical die allocation, protection or hardware qualification.'},indent=2))
PY
