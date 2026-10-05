#!/bin/sh
set -eu
cd "$(dirname "$0")"
UNIT=$(pwd)
STUDY_ROOT=${TEMPER_GLASS_STUDY_ROOT:-/Users/bennet/.codex/worktrees/glass-sensor-simulation/temper/packages/temper-thermal/studies/glass_sensor}
CHECK=$(mktemp -d /private/tmp/temper-r10-runner-check.XXXXXX)
trap 'rm -rf "$CHECK"' EXIT
mkdir -p "$CHECK/results"
cp adapter.rs run.sh inputs.sha256 "$CHECK/"
cp results/c9_conductance_sensitivity.csv "$CHECK/results/"
cp results/run-inputs.sha256 "$CHECK/results/"
cp inputs.sha256 "$CHECK/base-inputs.sha256"
cp results/c9_conductance_sensitivity.csv "$CHECK/expected.csv"
cp results/run-inputs.sha256 "$CHECK/seed-receipt.sha256"

# Invalid inherited pin must fail before compilation and invalidate success.
awk 'NR == 1 {$1 = "0000000000000000000000000000000000000000000000000000000000000000"} {printf "%s  %s\n", $1, $2}' \
    "$CHECK/base-inputs.sha256" > "$CHECK/inputs.sha256"
if (cd "$CHECK" && TEMPER_GLASS_STUDY_ROOT="$STUDY_ROOT" sh run.sh >/dev/null 2>&1); then
    echo 'bad-source-hash unexpectedly passed' >&2
    exit 1
fi
[ ! -e "$CHECK/results/run-inputs.sha256" ]
cmp "$CHECK/expected.csv" "$CHECK/results/c9_conductance_sensitivity.csv"
printf 'bad_source_hash,PASS,old_receipt_removed,physics_csv_unchanged\n'

cp "$CHECK/base-inputs.sha256" "$CHECK/inputs.sha256"
cp "$CHECK/seed-receipt.sha256" "$CHECK/results/run-inputs.sha256"
if (cd "$CHECK" && TEMPER_GLASS_STUDY_ROOT="$STUDY_ROOT" TEMPER_R10_CORRUPT_SNAPSHOT=1 sh run.sh >/dev/null 2>&1); then
    echo 'corrupt-consumed-snapshot unexpectedly passed' >&2
    exit 1
fi
[ ! -e "$CHECK/results/run-inputs.sha256" ]
cmp "$CHECK/expected.csv" "$CHECK/results/c9_conductance_sensitivity.csv"
printf 'corrupt_consumed_snapshot,PASS,old_receipt_removed,physics_csv_unchanged\n'
