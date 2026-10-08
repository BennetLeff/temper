#!/usr/bin/env bash
# Explicit follow-on job; NOT evidence that any listed case has been solved.
# Run on an otherwise idle qualified macOS host with >=64 GiB RAM.
# The watchdog uses macOS ps/sysctl/vm_stat; Linux needs separately tested monitoring.
# No remote dispatch/upload.
set -euo pipefail
src=$(cd "$(dirname "$0")" && pwd)
oracle=${1:?oracle checkout}; elmer=${2:?qualified Elmer install}; out=${3:?new output directory}
"$FEM_PYTHON" - <<'PY'
import os
ram = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
if ram < 64 * 1024**3:
    raise SystemExit('This follow-on profile requires at least 64 GiB physical RAM; no job launched.')
PY
test ! -e "$out" || { echo 'Output exists; refusing stale case reuse' >&2; exit 1; }
mkdir -p "$out"
export FIELD_RSS_GIB=48 FIELD_SECONDS=14400 FIELD_MAXIT=40000
export PATH="$(dirname "$FEM_PYTHON"):$PATH"
extraction="$src/../../round2/d17/evidence/extraction"
# height:near-edge:dz:margin:air. Far edge4 remains fixed. These comparisons
# distinguish closure-height, horizontal/vertical discretization, and crop.
for leg in A B; do
  for tuple in 1:2:1:20:10 2:2:1:20:10 3:2:1:20:10 1:1:1:20:10 1:2:0.5:20:10 1:0.5:0.25:20:10 1:2:1:30:10 1:2:1:20:20; do
    IFS=: read -r height edge dz margin air <<< "$tuple"
    case_name="$leg-h$height-e$edge-dz$dz-m$margin-a$air"
    mesh="$out/$case_name.msh"
    "$FEM_PYTHON" "$src/mesh.py" --oracle "$oracle" --extraction "$extraction" --leg "$leg" --out "$mesh" --height "$height" --edge "$edge" --dz "$dz" --far 4 --margin "$margin" --air "$air" > "${mesh%.msh}.log" 2>&1
    export FIELD_GEOMETRY="$out/$case_name-geometry.json"
    "$FEM_PYTHON" "$src/register-mesh.py" --oracle "$oracle" --mesh "$mesh" --closures "$extraction/closures-leg$leg.json" --out "$FIELD_GEOMETRY"
    ports=()
    for port in 10 11 12 13; do
      run="$out/$case_name-p$port"
      bash "$src/solve-one.sh" "$oracle" "$elmer" "$mesh" "$port" 4 "$run" > "$run.out" 2>&1
      ports+=(--port "$port" "$run")
    done
    "$FEM_PYTHON" "$src/watch.py" --receipt "$out/$case_name-compose-resource.json" --rss-gib 24 --seconds 600 -- \
      "$FEM_PYTHON" "$src/compose.py" --oracle "$oracle" --mesh "$mesh" --out "$out/$case_name-matrix.json" "${ports[@]}" > "$out/$case_name-matrix.log" 2>&1
  done
done
# This job does not invent a loaded-Kelvin, bulk/cross-leg, device-package, or
# installed catch mode. Those require additional physically closed geometry.
