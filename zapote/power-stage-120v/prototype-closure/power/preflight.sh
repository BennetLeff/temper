#!/usr/bin/env bash
# Refuse changed experiment inputs before executing the external runner.
set -euo pipefail
src=$(cd "$(dirname "$0")" && pwd)
oracle=${1:?Usage: preflight.sh /absolute/path/to/ps-oracle}
manifest="$src/evidence-manifest.json"
check_hash() {
  local section=$1 name=$2 path=$3 expected actual
  expected=$(jq -er --arg s "$section" --arg n "$name" \
    '.[$s][$n] | select(type == "string" and test("^[0-9a-f]{64}$"))' "$manifest")
  actual=$(shasum -a 256 "$path")
  actual=${actual%% *}
  if [[ "$actual" != "$expected" ]]; then
    printf 'Preflight failed: SHA-256 mismatch: %s\n' "$path" >&2
    exit 1
  fi
}
for name in leg_matrix_baseline.cir conditional_turnoff.cir \
  legA-h0-best.matrix.txt matrix-params.inc run-conditional.sh preflight.sh \
  accept-conditional.jq; do
  check_hash owned_files "$name" "$src/$name"
done
for name in common/run_ngspice.py models/vendor/IFX_CFD7_650V.lib common/options.inc; do
  relative="zapote/power-stage-120v/validation-plan/sim-kit/$name"
  check_hash external_inputs "$relative" "$oracle/$relative"
done
expected=$(jq -er '.ngspice_version | select(type == "string" and length > 0)' "$manifest")
actual=$(ngspice --version | sed -n 's/^\*\* \(ngspice-[^ ]*\) :.*$/\1/p')
if [[ "$actual" != "$expected" ]]; then
  printf 'Preflight failed: unsupported simulator %s; reproduction requires %s\n' "$actual" "$expected" >&2
  exit 1
fi
printf 'Preflight passed: 7 owned inputs, 3 external inputs, %s\n' "$actual"
