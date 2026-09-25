#!/bin/sh
# Run from this directory. A successful ERC command does not mean zero findings.
set -eu
run_tmp=$(mktemp -d /tmp/temper16-verify.XXXXXX)
trap 'rm -rf "$run_tmp"' EXIT
rustc --edition 2021 -D warnings capture.rs -o "$run_tmp/capture"
"$run_tmp/capture"
for name in clamp reset; do
    kicad-cli sch export netlist --format kicadsexpr -o "$name.net" "$name.kicad_sch"
    kicad-cli sch erc --format json --output "$name-erc.json" "$name.kicad_sch"
done
rustc --edition 2021 -D warnings auditor.rs -o "$run_tmp/auditor"
"$run_tmp/auditor" .
"$run_tmp/auditor" --self-test .
rustc --edition 2021 -D warnings capture-screen.rs -o "$run_tmp/screen"
"$run_tmp/screen"
rustc --edition 2021 --test capture-screen.rs -o "$run_tmp/screen-tests"
"$run_tmp/screen-tests"
node negative-controls.mjs "$run_tmp/auditor"
