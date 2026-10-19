#!/bin/sh
# Recompile the small standalone Rust guard; never reuse a stale executable.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build=$(mktemp -d "${TMPDIR:-/tmp}/temper-baseline.XXXXXX")
trap 'rm -rf "$build"' EXIT HUP INT TERM
rustc --edition=2021 -D warnings "$root/scripts/check_hardware_baseline.rs" -o "$build/check"
"$build/check" "$root" "$@"
