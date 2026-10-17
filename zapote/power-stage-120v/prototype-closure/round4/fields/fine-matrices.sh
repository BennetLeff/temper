#!/usr/bin/env bash
# A new sequential fine campaign, permitted only after profile qualification.
# No existing run is overwritten; each numerical/resource rejection halts it.
set -euo pipefail
src=$(cd "$(dirname "$0")" && pwd)
oracle=${1:?oracle checkout}; elmer=${2:?qualified local Elmer}; out=${3:?output directory}
"$FEM_PYTHON" - "$src" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
if os.sysconf('SC_PHYS_PAGES')*os.sysconf('SC_PAGE_SIZE') < 64*1024**3:
    raise SystemExit('The 32 GiB postprocessing profile was resource-stopped; this follow-on requires >=64 GiB. No job launched.')
src=Path(sys.argv[1]); q=json.loads((src/'elemental-qualification.json').read_text())
assert q['status']=='QUALIFIED_NATIVE_REFERENCE', 'Output profile qualification incomplete'
assert q['adapter_sha256']==hashlib.sha256((src/'run-elemental.py').read_bytes()).hexdigest()
PY
export FIELD_POSTPROCESS=elemental
export FIELD_RSS_GIB=${FIELD_RSS_GIB:-48} FIELD_SECONDS=${FIELD_SECONDS:-7200}
for item in A:10 B:10 A:11 A:12 A:13 B:11 B:12 B:13; do
  IFS=: read -r leg port <<< "$item"
  tag="fine-$leg-e1-dz025-h1"; run="$out/$tag-elemental-p$port"
  test ! -e "$run" || { echo "Refusing existing run: $run" >&2; exit 1; }
  "$FEM_PYTHON" - "$out" "$run-headroom.json" <<'PY'
import json,re,shutil,subprocess,sys
text=subprocess.check_output(['memory_pressure','-Q'],text=True)
match=re.search(r'System-wide memory free percentage: (\d+)%',text)
if not match: raise SystemExit('Could not read memory headroom; no solver launched')
free=shutil.disk_usage(sys.argv[1]).free
record={'memory_pressure_output':text,'free_disk_bytes':free,'minimum_headroom_percent':55,'minimum_disk_gib':12}
open(sys.argv[2],'w').write(json.dumps(record,indent=2)+'\n')
if int(match[1])<55 or free<12*1024**3: raise SystemExit('Insufficient observed headroom/disk; no solver launched')
PY
  bash "$src/solve-one.sh" "$oracle" "$elmer" "$out/$tag.msh" "$port" 4 "$run" > "$run.out" 2>&1
  if [[ "$port" = 10 ]]; then
    "$FEM_PYTHON" "$src/watch.py" --receipt "$out/$tag-elemental-diagonal-resource.json" --rss-gib 4 --seconds 300 -- \
      "$FEM_PYTHON" "$src/compose.py" --oracle "$oracle" --mesh "$out/$tag.msh" --out "$out/$tag-elemental-diagonal.json" --port 10 "$run" > "$out/$tag-elemental-diagonal.log" 2>&1
  fi
  if [[ "$port" = 13 ]]; then
    args=()
    for p in 10 11 12 13; do args+=(--port "$p" "$out/$tag-elemental-p$p"); done
    "$FEM_PYTHON" "$src/watch.py" --receipt "$out/$tag-elemental-matrix-resource.json" --rss-gib 8 --seconds 600 -- \
      "$FEM_PYTHON" "$src/compose.py" --oracle "$oracle" --mesh "$out/$tag.msh" --out "$out/$tag-elemental-matrix.json" "${args[@]}" > "$out/$tag-elemental-matrix.log" 2>&1
  fi
done
