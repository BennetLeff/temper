#!/bin/sh
set -eu
cd "$(dirname "$0")"
export NGSPICE=${NGSPICE:-$(command -v ngspice)}
BUILD=$(mktemp -d /tmp/temper-lcr-fixed-local.XXXXXX)
trap 'rm -rf "$BUILD"' EXIT HUP INT TERM
case "${1:---check}" in
  --check) shasum -a 256 -c SHA256SUMS > "$BUILD/hashes.txt" ;;
  --full)
    shasum -a 256 -c MODEL-SHA256SUMS
    for program in run supplemental ac_sweep stage53; do
      rustc --edition=2021 -O "$program.rs" -o "$BUILD/$program"
      "$BUILD/$program" > "$program-progress.log"
    done ;;
  *) echo 'Usage: ./rerun.sh --check|--full (run --full in a copy to retain captured evidence)' >&2; exit 2 ;;
esac
rustc --edition=2021 --test strict_order.rs -o "$BUILD/order-tests"
"$BUILD/order-tests" > "$BUILD/order-tests.txt"
for pair in 'summarize check-pulse' 'supplemental_check check-supplemental' 'stage53_check check-stage53'; do
  set -- $pair
  rustc --edition=2021 -O "$1.rs" -o "$BUILD/$1"
  "$BUILD/$1" > "$2.txt"
  cat "$2.txt"
done
