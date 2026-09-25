#!/bin/sh
set -eu
cd "$(dirname "$0")"
checker=$(mktemp /private/tmp/ucc06-checks.XXXXXX)
trap 'rm -f "$checker"' EXIT
rustc --edition=2021 --test checks.rs -o "$checker"
"$checker" > checker-tests.txt
rustc --edition=2021 -O checks.rs -o "$checker"
for fixture in functional current-loop soft-start integrated integrated-refined; do
  ngspice -b "$fixture.cir" > "$fixture.log" 2>&1
  mode=$fixture
  [ "$mode" != integrated-refined ] || mode=integrated
  "$checker" "$mode" "$fixture.tsv" > "$fixture-checks.txt"
done
for fixture in pcl-disabled protection-bypassed; do
  ngspice -b "$fixture.cir" > "$fixture.log" 2>&1
  mode=functional
  reason='FAIL PCL never latched'
  if [ "$fixture" = protection-bypassed ]; then
    mode=integrated
    reason='FAIL no external detector fault'
  fi
  if "$checker" "$mode" "$fixture.tsv" > "$fixture-checks.txt" 2>&1; then
    echo "negative control unexpectedly passed: $fixture" >&2
    exit 1
  fi
  rg -Fx "$reason" "$fixture-checks.txt" >/dev/null
 done
"$checker" refinement integrated.tsv integrated-refined.tsv > refinement-checks.txt
printf '%s\n' 'PASS controller functional, current-loop, soft-start, coupled/refined and expected negatives'
