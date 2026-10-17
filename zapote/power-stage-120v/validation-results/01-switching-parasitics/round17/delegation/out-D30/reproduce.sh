#!/bin/sh
# Run from repository root. Uses only standalone rustc and native KiCad.
set -eu
base=zapote/power-stage-120v/prototype-closure/round5/boards
evidence=zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D30
work=$(mktemp -d "${TMPDIR:-/tmp}/temper-d30-reproduce.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
rustc --edition=2021 "$base/partition.rs" -o "$work/partition"
"$work/partition"
python3 "$base/render_central.py"
sh "$base/check.sh"
python3 "$evidence/capture.py"
# Prove the current validator rejects the actual baseline tables, without
# modifying the maintained board or returning the connector to power_out.
rustc --edition=2021 "$base/power_direction.rs" -o "$work/power-direction"
mkdir -p "$work/baseline/central/generated"
for name in central/generated/pins catch-pins bus-pins line-pins pre-pins out-pins tank-pins iproof-pins iline-pins; do
 git show "841a66d9408e16b3fcd71d9e46131b62df00bb65:$base/$name.tsv" > "$work/baseline/$name.tsv"
done
if "$work/power-direction" "$work/baseline" > "$work/baseline-audit.tsv" 2> "$work/baseline-audit.log"; then
 echo 'ERROR: original J9 power_out definitions were accepted' >&2
 exit 1
fi
cat "$work/baseline-audit.log"
grep -q 'connector_without_onboard_source.*central:J9.1' "$work/baseline-audit.log"
grep -q 'connector_without_onboard_source.*central:J9.2' "$work/baseline-audit.log"
