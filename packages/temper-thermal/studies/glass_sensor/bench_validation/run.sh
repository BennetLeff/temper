#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
build_dir=$(mktemp -d /tmp/temper-bench.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
out=${1:-evidence}
mkdir -p "$out"
rustfmt --check bench.rs synthetic.rs
rustc --edition 2021 -D warnings --test bench.rs -o "$build_dir/tests"
"$build_dir/tests" > "$out/software-tests.txt"
rustc --edition 2021 -D warnings -O bench.rs -o "$build_dir/bench"
rustc --edition 2021 -D warnings -O synthetic.rs -o "$build_dir/synthetic"
"$build_dir/synthetic" "$build_dir/data"
for case in holdout weak_contact hidden_dynamics; do
  "$build_dir/bench" calibrate "$build_dir/data/SYNTHETIC-fit.csv" "$build_dir/data/SYNTHETIC-fit.txt" "$build_dir/data/SYNTHETIC-$case.csv" "$build_dir/data/SYNTHETIC-$case.txt" > "$out/SYNTHETIC-calibration-$case.txt"
done
"$build_dir/bench" thermal "$build_dir/data/SYNTHETIC-biased_fast.csv" "$build_dir/data/SYNTHETIC-biased_fast.txt" > "$out/SYNTHETIC-biased-fast-response.txt"
for case in mechanical_return mechanical_stuck; do
  "$build_dir/bench" mechanical "$build_dir/data/SYNTHETIC-$case.csv" "$build_dir/data/SYNTHETIC-$case.txt" > "$out/SYNTHETIC-$case-result.txt"
done
rg -q 'return_to_0p02mm_s=0.110000' "$out/SYNTHETIC-mechanical_return-result.txt"
rg -q 'return_to_0p02mm_s=NOT_RETURNED' "$out/SYNTHETIC-mechanical_stuck-result.txt"
rg -q 'max_hysteresis_n=0.100000' "$out/SYNTHETIC-mechanical_return-result.txt"
# Assertions exercise full import path, separate closed-form fixtures, and negative controls.
rg -q 'SURROGATE_WITHIN_DECLARED_UNCERTAINTY' "$out/SYNTHETIC-calibration-holdout.txt"
rg -q 'REJECT_TRANSFER' "$out/SYNTHETIC-calibration-weak_contact.txt"
rg -q 'REJECT_TRANSFER' "$out/SYNTHETIC-calibration-hidden_dynamics.txt"
rg -q 't90_imposed_pan_step_s=NOT_REACHED' "$out/SYNTHETIC-biased-fast-response.txt"
rg -q 'error_screen=PROPOSED_SCREEN_FAIL' "$out/SYNTHETIC-biased-fast-response.txt"
reject() {
  if "$build_dir/bench" "$@" > "$build_dir/rejected.stdout" 2> "$build_dir/rejected.stderr"; then
    printf 'Expected rejection: %s\n' "$*" >&2
    exit 1
  fi
  printf 'REJECTED %s: ' "$1" >> "$out/negative-controls.txt"
  cat "$build_dir/rejected.stderr" >> "$out/negative-controls.txt"
}
: > "$out/negative-controls.txt"
reject thermal templates/samples.csv templates/run.txt
reject calibrate "$build_dir/data/SYNTHETIC-fit.csv" "$build_dir/data/SYNTHETIC-fit.txt"
reject calibrate "$build_dir/data/SYNTHETIC-fit.csv" "$build_dir/data/SYNTHETIC-fit.txt" "$build_dir/data/SYNTHETIC-fit.csv" "$build_dir/data/SYNTHETIC-fit.txt"
for key in reference_id reference_calibration_id u_error_c; do
  sed "/^$key=/d" "$build_dir/data/SYNTHETIC-fit.txt" > "$build_dir/incomplete.txt"
  reject thermal "$build_dir/data/SYNTHETIC-fit.csv" "$build_dir/incomplete.txt"
done
sed 's/u_error_c=0.2/u_error_c=0/' "$build_dir/data/SYNTHETIC-fit.txt" > "$build_dir/zero.txt"
reject thermal "$build_dir/data/SYNTHETIC-fit.csv" "$build_dir/zero.txt"
sed 's/time_s/time_ms/' "$build_dir/data/SYNTHETIC-fit.csv" > "$build_dir/units.csv"
reject thermal "$build_dir/units.csv" "$build_dir/data/SYNTHETIC-fit.txt"
awk 'NR==3 {$0="0,25,25,25,0.4,0.6,0,0,thermal,1"} {print}' "$build_dir/data/SYNTHETIC-fit.csv" > "$build_dir/repeated.csv"
reject thermal "$build_dir/repeated.csv" "$build_dir/data/SYNTHETIC-fit.txt"
reject budget templates/uncertainty.csv
sed 's/plateau_start_s=60/plateau_start_s=1/' "$build_dir/data/SYNTHETIC-fit.txt" > "$build_dir/chronology.txt"
reject thermal "$build_dir/data/SYNTHETIC-fit.csv" "$build_dir/chronology.txt"
sed 's/evidence_kind=SYNTHETIC/evidence_kind=MEASURED/' "$build_dir/data/SYNTHETIC-fit.txt" > "$build_dir/laundered.txt"
reject thermal "$build_dir/data/SYNTHETIC-fit.csv" "$build_dir/laundered.txt"
sed 's/u_error_c=0.2/u_error_c=0.4/' "$build_dir/data/SYNTHETIC-fit.txt" > "$build_dir/guardband.txt"
"$build_dir/bench" thermal "$build_dir/data/SYNTHETIC-fit.csv" "$build_dir/guardband.txt" > "$out/SYNTHETIC-guardband.txt"
rg -q 'error_screen=INDETERMINATE' "$out/SYNTHETIC-guardband.txt"
cp "$build_dir/data"/SYNTHETIC-* "$out/"
{
  printf 'evidence_kind=SYNTHETIC\nphysical_validation=NOT_RUN\n'
  rustc --version
  shasum -a 256 bench.rs synthetic.rs run.sh
} > "$out/software-provenance.txt"
cat "$out/software-tests.txt" "$out/SYNTHETIC-calibration-holdout.txt" "$out/SYNTHETIC-calibration-weak_contact.txt"
