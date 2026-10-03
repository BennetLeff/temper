#!/bin/zsh
set -euo pipefail

HERE=${0:A:h}
BIN=/tmp/ps-r8-palace-build4/palace-build/palace-arm64.bin
binary_sha=d581869906ca59b2f9fa479f41155df6ceca5a4b11bfe941b4aae360e4a30cfd
label=${1:?coax label required}
case "$label" in
  coax-port0p10-vol0p30)
    expected=4fca7a2431cdf2032fbc40f141fc3a423af2efcbe8dc6fbc039f9620eb3f4e39
    ;;
  coax-port0p08-vol0p25)
    expected=0bfac7659ce47553e083c1f21b4bcafbe96856a3c790305af90147937c52e947
    ;;
  *)
    print -u2 "Unknown accepted coax mesh: $label"
    exit 2
    ;;
esac

cd "$HERE"
test -s "$BIN"
actual_binary=$(shasum -a 256 "$BIN" | awk '{print $1}')
if [[ "$actual_binary" != "$binary_sha" ]]; then
  print -u2 "Palace binary SHA mismatch: $actual_binary"
  exit 1
fi
mesh="raw/fixtures/$label-ascii.msh"
config="$label.json"
log="raw/fixtures/$label-palace.log"
test -s "$mesh"
test ! -e "$log"
actual=$(shasum -a 256 "$mesh" | awk '{print $1}')
if [[ "$actual" != "$expected" ]]; then
  print -u2 "Coax mesh SHA mismatch for $label"
  exit 1
fi

env OMPI_MCA_btl=self OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 "$BIN" -dry-run "$config" \
  > "raw/fixtures/$label-dryrun.log" 2>&1
ulimit -s 65520
set +e
env OMPI_MCA_btl=self OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  VECLIB_MAXIMUM_THREADS=1 /usr/bin/time -l "$BIN" "$config" \
  > "$log" 2>&1
run_rc=$?
set -e
print -r -- "$run_rc" > "raw/fixtures/$label-palace.exit-code"
exit "$run_rc"
