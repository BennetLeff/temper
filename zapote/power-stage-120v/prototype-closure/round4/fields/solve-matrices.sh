#!/usr/bin/env bash
# Sequential production campaign; each failed solve stops the campaign.
set -euo pipefail
src=$(cd "$(dirname "$0")" && pwd)
oracle=${1:?oracle path}; elmer=${2:?Elmer installation}; output=${3:?output directory}
ranks=${4:-4}
for mesh_name in B-e4-f4-h1 A-e4-h1; do
  args=()
  for port in 10 11 12 13; do
    work="$output/$mesh_name-np$ranks-p$port"
    bash "$src/solve-one.sh" "$oracle" "$elmer" "$output/$mesh_name.msh" "$port" "$ranks" "$work" > "$work.out" 2>&1
    args+=(--port "$port" "$work")
  done
  "$FEM_PYTHON" "$src/watch.py" --receipt "$output/$mesh_name-matrix-resource.json" --rss-gib 8 --seconds 300 -- \
    "$FEM_PYTHON" "$src/compose.py" --oracle "$oracle" --mesh "$output/$mesh_name.msh" --out "$output/$mesh_name-matrix.json" "${args[@]}" > "$output/$mesh_name-matrix.log" 2>&1
done
