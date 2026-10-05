#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
shasum -a 256 -c geometry-source.sha256
build_dir=$(mktemp -d /tmp/temper-induction-pr2.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
rustfmt --check topology.rs
rustc --edition=2021 --test -D warnings topology.rs -o "$build_dir/tests"
"$build_dir/tests"
rustc --edition=2021 -O -D warnings topology.rs -o "$build_dir/topology"
"$build_dir/topology"
rustc --version > results/toolchain.txt
shasum -a 256 topology.rs > results/source-sha256.txt
