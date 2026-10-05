#!/usr/bin/env bash
# Inspect explicit numerical results, since upstream diagnostic scripts exit 0
# even when they print a bad topology. This checks logs, not a field solution.
set -euo pipefail
out=${1:?Usage: check-gates.sh OUTPUT_DIRECTORY}
for leg in A B; do
  sed -n 's/^RESULT //p' "$out/mesh-$leg.log" | tail -1 | jq -se 'length == 1 and (.[0] | .zero_volume_tets == 0 and .skipped_area_mm2 == 0 and (.ports | length == 4) and (.port_leak_A | all(.leak_A == 0)))' >/dev/null
  sed -n 's/^RESULT //p' "$out/pec_columns-$leg.log" | tail -1 | jq -se 'length == 1 and (.[0] | .inner_farfield_triangles == 0)' >/dev/null
  sed -n 's/^RESULT //p' "$out/port_divergence-$leg.log" | tail -1 | jq -se 'length == 1 and (.[0] | length == 4 and all(.port_current_A == 1 and .leak_sum_abs_A <= 1e-9 and (.pec_net_A | fabs) <= 1e-9))' >/dev/null
  sed -n 's/^RESULT //p' "$out/port_loops-$leg.log" | tail -1 | jq -se 'length == 1 and (.[0] | (.ports | length == 4) and (.ports | all(.closed_loop == true and (.components | all(.farfield == false)))) and (.closure_ends | all(.a_body == .b_body and (.a_body | length == 1))))' >/dev/null
 done
printf 'Both-leg mesh topology checks passed; field matrices NOT_SOLVED.\n'
