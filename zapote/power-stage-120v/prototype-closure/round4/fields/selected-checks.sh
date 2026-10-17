#!/usr/bin/env bash
# Additional actual solves after both primary matrices. One solve at a time.
set -euo pipefail
src=$(cd "$(dirname "$0")" && pwd)
oracle=${1:?oracle checkout}; elmer=${2:?qualified Elmer installation}; out=${3:?output directory}
test -f "$out/A-e4-h1-matrix.json" && test -f "$out/B-e4-f4-h1-matrix.json"
for label in A-pair-10-12 A-e2-h1-selected-p10 A5-e4-f4-h1-selected-p10 A5-e4-f4-h1-selected-p14; do
  test ! -e "$out/$label" || { echo "Refusing existing run: $label" >&2; exit 1; }
done
run="$out/A-pair-10-12"
bash "$src/solve-one.sh" "$oracle" "$elmer" "$out/A-e4-h1.msh" 10 4 "$run" 12 > "$run.out" 2>&1
cp "$out/A-e4-h1-matrix.log" "$out/A-e4-h1.matrix.txt"
"$FEM_PYTHON" "$src/check-pair.py" --oracle "$oracle" --tag "$out/A-e4-h1" --run "$run" --ports 10 12 > "$out/A-pair-check.log" 2>&1

run="$out/A-e2-h1-selected-p10"
bash "$src/solve-one.sh" "$oracle" "$elmer" "$out/A-e2-h1.msh" 10 4 "$run" > "$run.out" 2>&1
"$FEM_PYTHON" "$src/watch.py" --receipt "$out/A-selected-refinement-compose-resource.json" --rss-gib 4 --seconds 300 -- \
  "$FEM_PYTHON" "$src/compose.py" --oracle "$oracle" --mesh "$out/A-e2-h1.msh" --out "$out/A-selected-refinement-matrix.json" --port 10 "$run" > "$out/A-selected-refinement-matrix.log" 2>&1

for port in 10 14; do
  run="$out/A5-e4-f4-h1-selected-p$port"
  bash "$src/solve-one.sh" "$oracle" "$elmer" "$out/A5-e4-f4-h1.msh" "$port" 4 "$run" > "$run.out" 2>&1
done
"$FEM_PYTHON" "$src/watch.py" --receipt "$out/A5-selected-bulk-compose-resource.json" --rss-gib 4 --seconds 300 -- \
  "$FEM_PYTHON" "$src/compose.py" --oracle "$oracle" --mesh "$out/A5-e4-f4-h1.msh" --out "$out/A5-selected-bulk-matrix.json" \
  --port 10 "$out/A5-e4-f4-h1-selected-p10" --port 14 "$out/A5-e4-f4-h1-selected-p14" > "$out/A5-selected-bulk-matrix.log" 2>&1
