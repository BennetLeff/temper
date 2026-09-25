#!/bin/bash
# Preserve a bounded original-row tail for numerical-abort diagnosis only.
set -euo pipefail
cd /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07
out=faults/sw-short-abort-diagnostic-79
raw=faults/settled-sw-short-59/full-SW-SHORT/raw.trace.raw.gz
set -C
trap 'printf "%s\n" "$?" > "$out/extraction.exit"' EXIT
python3 - <<'PY' > "$out/preflight.json"
from pathlib import Path
import hashlib,json
p=Path('faults/settled-sw-short-59/full-SW-SHORT');s=json.loads((p/'capture-stage1.json').read_text());e=json.loads((p/'native-export-receipt.json').read_text())
assert s['host_success'] and s['pigz_success'] and s['host_rc']==s['pigz_rc']==0
assert (p/'stage1.exit').read_text().strip()=='host_rc=0 pigz_rc=0'
assert e['status']=='complete' and e['rows']==30686230
raw=p/'raw.trace.raw.gz'
with raw.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
assert h==s['raw_trace_sha256'] and raw.stat().st_size==s['raw_trace_bytes']
for file,expected in [('/opt/homebrew/bin/pigz','a05b6a8ff40a84f8c1fa4052e38a70a682e30f142f5fc7486356134572733a80'),('/private/tmp/matrix07-fault-native-decoder-parent','af7d186fa543ebd8158947322b6c9049c17534c1662e8b9e9c2df53606b73658')]:
 assert hashlib.sha256(Path(file).read_bytes()).hexdigest()==expected
print(json.dumps({'raw':str(raw),'bytes':raw.stat().st_size,'sha256':h,'native_rows':e['rows'],'scope':'last256 original data rows, no fault acceptance'},indent=2))
PY
set +e
/opt/homebrew/bin/pigz -dc "$raw" 2> "$out/pigz.stderr" |
 /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2> "$out/decoder.stderr" |
 { IFS= read -r header; printf '%s\n' "$header" > "$out/header.tsv"; tail -n 256 > "$out/last256-data.tsv"; }
codes=("${PIPESTATUS[@]}")
set -e
printf '%s\n' "${codes[*]}" > "$out/pipeline.exit"
for code in "${codes[@]}"; do test "$code" -eq 0; done
python3 - <<'PY' > "$out/receipt.json"
from pathlib import Path
import hashlib,json
p=Path('faults/sw-short-abort-diagnostic-79');pre=json.loads((p/'preflight.json').read_text());r=Path(pre['raw'])
with r.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
assert h==pre['sha256'] and r.stat().st_size==pre['bytes']
assert len((p/'last256-data.tsv').read_text().splitlines())==256
print(json.dumps({'status':'DIAGNOSTIC_TAIL_EXTRACTED','accepted':False,'raw_sha256_before_after':h,'native_rows':pre['native_rows'],'tail_rows':256,'pipeline_exits':[int(x) for x in (p/'pipeline.exit').read_text().split()],'files_sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in ['header.tsv','last256-data.tsv']},'scope':'Exact original rows for root-cause inspection; truncated simulation cannot establish fault response.'},indent=2))
PY
