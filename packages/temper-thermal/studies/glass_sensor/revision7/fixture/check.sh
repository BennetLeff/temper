#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -f results/negative-inputs.sha256
work=$(mktemp -d "${TMPDIR:-/tmp}/temper-r7-fixture-negative.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
mkdir -p "$work/broken/results" results
cp main.rs run.sh "$work/broken/"
sed 's/assert_eq!(remaining_elastic_mn(3.0, 3.0, 4.0), 0.0);/assert_eq!(remaining_elastic_mn(3.0, 3.0, 4.0), 1.0);/' main.rs > "$work/broken/main.rs"
printf 'stale success receipt\n' > "$work/broken/results/run-inputs.sha256"
set +e
"$work/broken/run.sh" > "$work/broken.log" 2>&1
failure_status=$?
set -e
if [ "$failure_status" -eq 0 ] || [ -e "$work/broken/results/run-inputs.sha256" ] || [ -e "$work/broken/results/pressure_bounds.csv" ]; then
    cat "$work/broken.log"
    exit 1
fi
if [ "$failure_status" -ne 101 ]; then
    cat "$work/broken.log"
    exit 1
fi
rustc --edition=2021 -D warnings main.rs -o "$work/model"
printf 'not a directory\n' > "$work/output-file"
set +e
"$work/model" "$work/output-file" > "$work/write.log" 2>&1
write_status=$?
set -e
if [ "$write_status" -eq 0 ]; then exit 1; fi
printf 'case,observed_exit,expected_result,analytical_status,physical_result\nfailed_test,%s,nonzero_no_receipt_no_csv,VERIFIED,NOT_RUN\noutput_write_error,%s,nonzero,VERIFIED,NOT_RUN\n' "$failure_status" "$write_status" > results/negative-checks.csv
shasum -a 256 main.rs run.sh check.sh results/negative-checks.csv > "$work/receipt"
mv "$work/receipt" results/negative-inputs.sha256
