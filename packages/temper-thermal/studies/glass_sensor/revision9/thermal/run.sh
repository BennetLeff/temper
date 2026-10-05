#!/bin/sh
set -eu
cd "$(dirname "$0")"
UNIT=$(pwd)
# Invalidate before resolving inputs: stale outputs are never a success receipt.
rm -f results/run-inputs.sha256
STUDY_ROOT=${TEMPER_GLASS_STUDY_ROOT:-$(cd ../.. && pwd)}
GEOMETRY=${TEMPER_R9_GEOMETRY:-$STUDY_ROOT/revision7/mechanical/thermal_geometry.csv}
(cd "$STUDY_ROOT" && shasum -a 256 -c "$UNIT/inputs.sha256")
EXPECTED=$(cat geometry.sha256)
ACTUAL=$(shasum -a 256 "$GEOMETRY" | cut -d ' ' -f 1)
[ "$ACTUAL" = "$EXPECTED" ] || { echo 'R9 source geometry hash mismatch' >&2; exit 1; }
rustfmt --check adapter.rs
RUN=$(mktemp -d /private/tmp/temper-r9-thermal.XXXXXX)
RECEIPT=
shasum -a 256 adapter.rs run.sh inputs.sha256 geometry.sha256 > "$RUN/unit-inputs.sha256"
trap 'rm -rf "$RUN"; if [ -n "$RECEIPT" ]; then rm -f "$RECEIPT"; fi' EXIT
mkdir -p "$RUN/revision5/thermal/r5" "$RUN/revision5/mechanical" "$RUN/unit" "$RUN/sources"
cp adapter.rs run.sh inputs.sha256 geometry.sha256 "$RUN/unit/"
(cd "$RUN/unit" && shasum -a 256 -c "$RUN/unit-inputs.sha256")
# Compile only hash-verified snapshots, never a live source after its pin check.
while read -r HASH RELATIVE; do
    mkdir -p "$RUN/sources/$(dirname "$RELATIVE")"
    cp "$STUDY_ROOT/$RELATIVE" "$RUN/sources/$RELATIVE"
done < "$RUN/unit/inputs.sha256"
(cd "$RUN/sources" && shasum -a 256 -c "$RUN/unit/inputs.sha256")
STUDY_ROOT="$RUN/sources"
cp "$STUDY_ROOT/model.rs" "$RUN/revision5/model.rs"
cp "$STUDY_ROOT/revision5/mechanical/thermal_geometry.csv" "$RUN/revision5/mechanical/thermal_geometry.csv"
cp "$GEOMETRY" "$RUN/revision5/mechanical/r7_thermal_geometry.csv"
COPIED=$(shasum -a 256 "$RUN/revision5/mechanical/r7_thermal_geometry.csv" | cut -d ' ' -f 1)
[ "$COPIED" = "$EXPECTED" ] || { echo 'R9 source geometry changed during snapshot' >&2; exit 1; }
printf '#[allow(dead_code)]\nmod r5 {\n' > "$RUN/revision5/thermal/main.rs"
cat "$STUDY_ROOT/revision5/thermal/main.rs" "$STUDY_ROOT/revision6/contact/adapter.rs" "$STUDY_ROOT/revision7/thermal/adapter.rs" "$RUN/unit/adapter.rs" >> "$RUN/revision5/thermal/main.rs"
printf '\n}\nfn main() -> Result<(), Box<dyn std::error::Error>> { r5::run_r9() }\n' >> "$RUN/revision5/thermal/main.rs"
rustc --edition=2021 --test -O -D warnings "$RUN/revision5/thermal/main.rs" -o "$RUN/tests"
if (cd "$RUN/revision5/thermal" && "$RUN/tests") > "$RUN/tests.txt"; then :; else
    TEST_STATUS=$?
    cat "$RUN/tests.txt"
    exit "$TEST_STATUS"
fi
clippy-driver --edition=2021 -O -D warnings "$RUN/revision5/thermal/main.rs" -o "$RUN/clippy"
clippy-driver --edition=2021 --test -O -D warnings "$RUN/revision5/thermal/main.rs" -o "$RUN/clippy-tests"
rustc --edition=2021 -O -D warnings "$RUN/revision5/thermal/main.rs" -o "$RUN/study"
(cd "$RUN/revision5/thermal" && "$RUN/study")
shasum -a 256 -c "$RUN/unit-inputs.sha256"
mkdir -p results
cp "$RUN/revision5/thermal/results/"*.csv results/
sed '${/^$/d;}' "$RUN/tests.txt" > results/tests.txt
{ rustc --version; rustfmt --version; clippy-driver --version; } > results/toolchain.txt
RECEIPT=$(mktemp "$UNIT/results/.run-inputs.XXXXXX")
{
    cat "$RUN/unit/inputs.sha256"
    printf '%s  R7_CAD_thermal_geometry.csv\n' "$ACTUAL"
    cat "$RUN/unit-inputs.sha256"
    shasum -a 256 results/process_sensitivity.csv results/baseline.csv results/convergence.csv results/tests.txt results/toolchain.txt
} > "$RECEIPT"
mv "$RECEIPT" results/run-inputs.sha256
RECEIPT=
cat results/baseline.csv
