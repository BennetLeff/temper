#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
ngspice -b ngspice/supply_interface.cir -o supply_interface.log
cargo run --manifest-path rail-contract/Cargo.toml --bin rail-trace -- supply_interface.tsv "$root"
