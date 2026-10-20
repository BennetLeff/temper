#!/bin/sh
set -eu
cd "$(dirname "$0")"
case "${1:---check}" in --check|--full) ;; *) echo 'usage: rerun.sh [--check|--full]' >&2; exit 2;; esac
for source in op_guard verify_final summarize_corners before_after_stats verify_extended rerun; do
    rustc --edition=2021 "$source.rs" -o "$source"
done
rustc --edition=2021 --test strict_order.rs -o strict_order_tests
./strict_order_tests
./rerun "${1:---check}"
