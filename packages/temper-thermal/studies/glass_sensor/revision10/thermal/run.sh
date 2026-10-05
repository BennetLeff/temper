#!/bin/sh
set -eu
cd "$(dirname "$0")"
UNIT=$(pwd)
STUDY_ROOT=${TEMPER_GLASS_STUDY_ROOT:-/Users/bennet/.codex/worktrees/glass-sensor-simulation/temper/packages/temper-thermal/studies/glass_sensor}
rm -f results/run-inputs.sha256
rustfmt --edition 2021 --check adapter.rs
awk 'NF != 2 || length($1) != 64 || $1 ~ /[^0-9a-f]/ || substr($0, 65, 2) != "  " || $2 ~ /\.\./ || $2 ~ /^\// {bad = 1} END {if (NR == 0 || bad) exit 1}' inputs.sha256 || {
    echo 'malformed inherited source manifest' >&2
    exit 1
}
(cd "$STUDY_ROOT" && shasum -a 256 -c "$UNIT/inputs.sha256" >/dev/null)
RUN=$(mktemp -d /private/tmp/temper-r10-thermal.XXXXXX)
RECEIPT=
trap 'rm -rf "$RUN"; if [ -n "$RECEIPT" ]; then rm -f "$RECEIPT"; fi' EXIT
mkdir -p "$RUN/sources" "$RUN/unit" "$RUN/revision5/thermal/r5" "$RUN/revision5/mechanical" "$RUN/results" "$UNIT/results"
shasum -a 256 adapter.rs run.sh inputs.sha256 > "$RUN/unit-inputs.sha256"
cp adapter.rs run.sh inputs.sha256 "$RUN/unit/"
(cd "$RUN/unit" && shasum -a 256 -c "$RUN/unit-inputs.sha256" >/dev/null)
while read -r HASH RELATIVE; do
    mkdir -p "$RUN/sources/$(dirname "$RELATIVE")"
    cp "$STUDY_ROOT/$RELATIVE" "$RUN/sources/$RELATIVE"
done < "$RUN/unit/inputs.sha256"
if [ "${TEMPER_R10_CORRUPT_SNAPSHOT:-0}" = 1 ]; then
    printf '\ncorrupt snapshot negative control\n' >> "$RUN/sources/model.rs"
fi
(cd "$RUN/sources" && shasum -a 256 -c "$RUN/unit/inputs.sha256" >/dev/null)
cp "$RUN/sources/model.rs" "$RUN/revision5/model.rs"
cp "$RUN/sources/revision5/mechanical/thermal_geometry.csv" "$RUN/revision5/mechanical/thermal_geometry.csv"
cp "$RUN/sources/revision7/mechanical/thermal_geometry.csv" "$RUN/revision5/mechanical/r7_thermal_geometry.csv"
cp "$RUN/unit/adapter.rs" "$RUN/adapter.rs"
printf '#[allow(dead_code)]\nmod r5 {\n' > "$RUN/revision5/thermal/main.rs"
cat "$RUN/sources/revision5/thermal/main.rs" "$RUN/sources/revision6/contact/adapter.rs" "$RUN/sources/revision7/thermal/adapter.rs" "$RUN/sources/revision9/thermal/adapter.rs" "$RUN/adapter.rs" >> "$RUN/revision5/thermal/main.rs"
printf '\n}\nfn main() -> Result<(), Box<dyn std::error::Error>> { r5::run_c9() }\n' >> "$RUN/revision5/thermal/main.rs"
rustc --edition=2021 --test -O -D warnings "$RUN/revision5/thermal/main.rs" -o "$RUN/tests"
(cd "$RUN/revision5/thermal" && "$RUN/tests") > "$RUN/results/tests.txt"
rustc --edition=2021 -O -D warnings "$RUN/revision5/thermal/main.rs" -o "$RUN/study"
(cd "$RUN/revision5/thermal" && "$RUN/study")
(cd "$STUDY_ROOT" && shasum -a 256 -c "$UNIT/inputs.sha256" >/dev/null) || {
    # Source may have changed after snapshot; this run is then not attributable.
    echo 'live inherited source changed during run' >&2
    exit 1
}
shasum -a 256 -c "$RUN/unit-inputs.sha256" >/dev/null
cp "$RUN/revision5/thermal/results/c9_conductance_sensitivity.csv" results/
cp "$RUN/results/tests.txt" results/
{ rustc --version; rustfmt --version; } > results/toolchain.txt
RECEIPT=$(mktemp "$UNIT/results/.run-inputs.XXXXXX")
{
    cat "$RUN/unit/inputs.sha256"
    cat "$RUN/unit-inputs.sha256"
    shasum -a 256 results/c9_conductance_sensitivity.csv results/tests.txt results/toolchain.txt
} > "$RECEIPT"
mv "$RECEIPT" results/run-inputs.sha256
RECEIPT=
cat results/c9_conductance_sensitivity.csv
