#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
ORACLE_BUILD_DIR=$(mktemp -d)
trap 'rm -rf "$ORACLE_BUILD_DIR"' EXIT HUP INT TERM
rustc --edition=2021 --test return_ratio_oracle.rs -o "$ORACLE_BUILD_DIR/tests"
"$ORACLE_BUILD_DIR/tests" > return-ratio-oracle/tests.txt
rustc --edition=2021 -O return_ratio_oracle.rs -o "$ORACLE_BUILD_DIR/oracle"
"$ORACLE_BUILD_DIR/oracle" > return-ratio-oracle/run.log
if [ "$#" -gt 0 ]; then
    "$ORACLE_BUILD_DIR/oracle" --inspect "$@" >> return-ratio-oracle/run.log
    shasum -a 256 "$@" > return-ratio-oracle/inspected-inputs.sha256
fi
