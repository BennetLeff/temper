#!/bin/sh
set -eu
cd "$(dirname "$0")"
UNIT=$(pwd)
STUDY_ROOT=${TEMPER_GLASS_STUDY_ROOT:-$(cd ../.. && pwd)}
# A failed run cannot leave a current success receipt.
rm -f results/run-inputs.sha256
(cd "$STUDY_ROOT" && shasum -a 256 -c "$UNIT/inputs.sha256")
rustfmt --check adapter.rs
RUN=$(mktemp -d /private/tmp/temper-r6-contact.XXXXXX)
trap 'rm -rf "$RUN"' EXIT
mkdir -p "$RUN/revision5/thermal/r5" "$RUN/revision5/mechanical"
cp "$STUDY_ROOT/model.rs" "$RUN/revision5/model.rs"
cp "$STUDY_ROOT/revision5/mechanical/thermal_geometry.csv" "$RUN/revision5/mechanical/thermal_geometry.csv"
# R5 physics remains verbatim inside a module. Only appended adapter is maintained here.
printf '#[allow(dead_code)]\nmod r5 {\n' > "$RUN/revision5/thermal/main.rs"
cat "$STUDY_ROOT/revision5/thermal/main.rs" adapter.rs >> "$RUN/revision5/thermal/main.rs"
printf '\n}\nfn main() -> Result<(), Box<dyn std::error::Error>> { r5::run_r6() }\n' >> "$RUN/revision5/thermal/main.rs"
rustc --edition=2021 -O -D warnings "$RUN/revision5/thermal/main.rs" -o "$RUN/study"
rustc --edition=2021 --test -O -D warnings "$RUN/revision5/thermal/main.rs" -o "$RUN/tests"
if (cd "$RUN/revision5/thermal" && "$RUN/tests") > "$RUN/tests.txt"; then
    :
else
    TEST_STATUS=$?
    cat "$RUN/tests.txt"
    exit "$TEST_STATUS"
fi
clippy-driver --edition=2021 -O -D warnings "$RUN/revision5/thermal/main.rs" -o "$RUN/clippy"
(cd "$RUN/revision5/thermal" && "$RUN/study")
mkdir -p results
cp "$RUN/revision5/thermal/results/"*.csv results/
cp "$RUN/tests.txt" results/tests.txt
{
    cat inputs.sha256
    shasum -a 256 adapter.rs run.sh results/comparison.csv results/baseline.csv results/convergence.csv results/native_lead_sensitivity.csv results/film_path_sensitivity.csv
} > results/run-inputs.sha256
cat results/baseline.csv
