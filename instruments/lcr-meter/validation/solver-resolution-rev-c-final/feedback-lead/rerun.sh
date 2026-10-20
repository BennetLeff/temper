#!/bin/sh
set -eu
cd "$(dirname "$0")"
case "${1:---check}" in
    --check) ;;
    --full) rustc --edition=2021 run.rs -o run; ./run ;;
    *) echo 'usage: rerun.sh [--check|--full]' >&2; exit 2 ;;
esac
rustc --edition=2021 summarize.rs -o summarize
./summarize
shasum -a 256 -c input-hashes.txt
rustc --edition=2021 aggregate.rs -o aggregate
./aggregate
