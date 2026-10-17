#!/usr/bin/env bash
# One bounded, hash-bound field solve. WORK must be new; no stale-result reuse.
set -euo pipefail
src=$(cd "$(dirname "$0")" && pwd)
oracle=${1:?oracle path}; elmer=${2:?Elmer install}; mesh=${3:?mesh path}
port=${4:?physical port}; ranks=${5:?local MPI ranks}; work=${6:?new work directory}
second_port=${7:-}
fem_python=${FEM_PYTHON:?set FEM_PYTHON to the existing qualified environment Python}
runner_rel=zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/scripts/run_elmer.py
expected=$(jq -er --arg p "$runner_rel" '.[$p]' "$src/../../round2/d17/upstream-inputs.json")
actual=$(shasum -a 256 "$oracle/$runner_rel"); actual=${actual%% *}
[[ "$actual" = "$expected" ]] || { echo 'Solver runner hash mismatch' >&2; exit 1; }
for binary_key in ElmerSolver_mpi ElmerGrid libelmersolver MagnetoDynamics ResultOutputSolve libHYPRE libmpi; do
  case "$binary_key" in
    ElmerSolver_mpi|ElmerGrid) binary_path="$elmer/bin/$binary_key" ;;
    libelmersolver) binary_path="$elmer/lib/elmersolver/libelmersolver.dylib" ;;
    libHYPRE|libmpi) binary_path="$(dirname "$fem_python")/../lib/$binary_key.dylib" ;;
    *) binary_path="$elmer/share/elmersolver/lib/$binary_key.dylib" ;;
  esac
  expected_binary=$(jq -er --arg n "$binary_key" '.binary_and_source_sha256[$n]' "$src/environment.json")
  actual_binary=$(shasum -a 256 "$binary_path"); actual_binary=${actual_binary%% *}
  [[ "$actual_binary" = "$expected_binary" ]] || { echo "Unqualified solver binary: $binary_key" >&2; exit 1; }
done
[[ ! -e "$work" ]] || { echo 'Work directory already exists; refusing reuse' >&2; exit 1; }
mesh_name=$(basename "${mesh%.msh}")
expected_mesh=$(jq -er --arg n "$mesh_name" '.meshes[] | select(.name == $n) | .mesh_sha256' "${FIELD_GEOMETRY:-$src/geometry.json}")
actual_mesh=$(shasum -a 256 "$mesh"); actual_mesh=${actual_mesh%% *}
[[ "$expected_mesh" = "$actual_mesh" ]] || { echo 'Unregistered or changed geometry' >&2; exit 1; }
record=$(sed -n 's/^RESULT //p' "${mesh%.msh}.log" | tail -1)
expected_record=$(jq -Sc --arg n "$mesh_name" '.meshes[] | select(.name == $n) | .mesh' "${FIELD_GEOMETRY:-$src/geometry.json}")
actual_record=$(printf '%s\n' "$record" | jq -Sc .)
[[ "$expected_record" = "$actual_record" ]] || { echo 'Mesh/port record differs from registered geometry' >&2; exit 1; }
printf '%s\n' "$record" | jq -e '.zero_volume_tets == 0 and .skipped_area_mm2 == 0 and (.port_leak_A | all(.leak_A == 0))' >/dev/null
k=()
while IFS= read -r value; do k+=("$value"); done < <(printf '%s\n' "$record" | jq -er --argjson port "$port" '.ports[] | select(.physical == $port) | .k_A_per_m as $m | .direction[] * $m')
[[ ${#k[@]} = 3 ]] || { echo 'Missing or ambiguous physical port' >&2; exit 1; }
pair=()
if [[ -n "$second_port" ]]; then
  [[ "$port" != "$second_port" ]] || { echo 'Duplicate paired port' >&2; exit 1; }
  k2=()
  while IFS= read -r value; do k2+=("$value"); done < <(printf '%s\n' "$record" | jq -er --argjson port "$second_port" '.ports[] | select(.physical == $port) | .k_A_per_m as $m | .direction[] * $m')
  [[ ${#k2[@]} = 3 ]] || { echo 'Missing or ambiguous second port' >&2; exit 1; }
  pair=(--port2 "$second_port" --k2 "${k2[@]}")
fi
export PATH="$(dirname "$fem_python"):$PATH"
restart=${FIELD_GMRES_RESTART:-$(jq -r --arg n "$mesh_name" --arg p "$port" '.[$n].gmres_restart_by_port[$p] // .[$n].gmres_restart // 100' "$src/solver-config.json")}
rss_limit=${FIELD_RSS_GIB:-$(jq -r --arg n "$mesh_name" --arg p "$port" '.[$n].rss_gib_by_port[$p] // 8' "$src/solver-config.json")}
max_iterations=${FIELD_MAXIT:-18000}
[[ "$max_iterations" =~ ^[1-9][0-9]*$ ]] || { echo 'Invalid iteration limit' >&2; exit 1; }
[[ "$restart" = 100 || "$restart" = 200 ]] || { echo 'Unqualified GMRES restart' >&2; exit 1; }
runner=("$oracle/$runner_rel")
case "${FIELD_POSTPROCESS:-full}" in
  full) ;;
  elemental) runner=("$src/run-elemental.py" --oracle "$oracle") ;;
  *) echo 'Unknown postprocessing profile' >&2; exit 1 ;;
esac
exec "$fem_python" "$src/watch.py" --receipt "$work-resource.json" --rss-gib "$rss_limit" --seconds "${FIELD_SECONDS:-3600}" --solver-result "$work/result.json" -- "$fem_python" "${runner[@]}" "$mesh" "$work" --pec 2 3 --port "$port" --k "${k[@]}" "${pair[@]}" --hypre-ams --hypre-method 8 --ams-singular --solver-line "HYPRE GmRes Dimension = Integer $restart" --tol 1e-7 --maxit "$max_iterations" --np "$ranks" --vtu --elmer "$elmer"
