#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$here" rev-parse --show-toplevel)
cd "$root"
shasum -a 256 -c "$here/inputs.sha256"
bin=$(mktemp -d /private/tmp/temper-d22-round2.XXXXXX)
trap 'rm -rf "$bin"' EXIT HUP INT TERM
rustc --edition=2021 --test "$here/runner.rs" -o "$bin/tests"
"$bin/tests"
rustc --edition=2021 -O "$here/runner.rs" -o "$bin/runner"
out="$root/output/temper-prototype-closure/round2/d22/replay-$(date +%Y%m%d-%H%M%S)-$$"
"$bin/runner" "$here/line-model.cir" "$out"
printf 'Evidence: %s\n' "$out"
