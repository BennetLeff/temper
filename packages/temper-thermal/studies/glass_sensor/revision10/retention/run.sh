#!/bin/sh
set -eu
unit=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=${TEMPER_REPO_ROOT:-$(git -C "$unit" rev-parse --show-toplevel)}
run=$(mktemp -d "${TMPDIR:-/tmp}/temper-r10-retention.XXXXXX")
trap 'rm -rf "$run"' EXIT HUP INT TERM
rm -f "$unit/results.sha256"
(cd "$unit" && shasum -a 256 budget.rs run.sh inputs.sha256 > "$run/unit-inputs.sha256")
cp "$unit/budget.rs" "$unit/run.sh" "$unit/inputs.sha256" "$run/"
(cd "$run" && shasum -a 256 -c unit-inputs.sha256)
(cd "$repo" && shasum -a 256 -c "$run/inputs.sha256")
rustfmt --check "$run/budget.rs"
rustc --edition=2021 -D warnings --test "$run/budget.rs" -o "$run/tests"
"$run/tests" > "$run/tests.txt"
rustc --edition=2021 -D warnings "$run/budget.rs" -o "$run/budget"
"$run/budget" > "$run/budget.csv"
cp "$run/tests.txt" "$unit/tests.txt"
cp "$run/budget.csv" "$unit/budget.csv"
cat "$run/unit-inputs.sha256" > "$run/receipt"
(cd "$unit" && shasum -a 256 budget.csv tests.txt >> "$run/receipt")
cp "$run/receipt" "$unit/results.sha256.tmp"
mv "$unit/results.sha256.tmp" "$unit/results.sha256"
