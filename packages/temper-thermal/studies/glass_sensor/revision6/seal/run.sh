#!/bin/sh
set -eu
cd "$(dirname "$0")"
# Invalidate the old success receipt before any check can fail.
rm -f results/inputs.sha256
bin=$(mktemp -d /private/tmp/temper-r6-seal.XXXXXX)
trap 'rm -rf "$bin"' EXIT
rustfmt --check main.rs
rustc --edition=2021 -D warnings --test main.rs -o "$bin/tests"
mkdir -p results
"$bin/tests" > "$bin/tests.log"
cp "$bin/tests.log" results/tests.txt
clippy-driver --edition=2021 -D warnings main.rs -o "$bin/clippy"
rustc --edition=2021 -O -D warnings main.rs -o "$bin/model"
"$bin/model"
shasum -a 256 main.rs run.sh results/*.csv > results/inputs.sha256
