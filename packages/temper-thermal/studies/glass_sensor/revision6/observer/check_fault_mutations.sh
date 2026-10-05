#!/bin/sh
# Real, isolated negative checks of fault assertions; never edits study source.
set -eu
cd "$(dirname "$0")"
TEMPER_MUTATION=$(mktemp -d /private/tmp/temper-r6-observer-mutation.XXXXXX)
trap 'rm -rf "$TEMPER_MUTATION"' EXIT
mkdir -p results
# Replacing the gate expression while retaining the original parameter usage avoids
# confusing an unused-variable compile failure with the intended assertion failure.
awk '/contact && electrical && stamp.is_finite/ {print "    (" $0 ") || true"; next} {print}' main.rs > "$TEMPER_MUTATION/stale.rs"
rustc --edition=2021 --test -O "$TEMPER_MUTATION/stale.rs" -o "$TEMPER_MUTATION/stale"
if "$TEMPER_MUTATION/stale" tests::stale_and_invalid_contact_rejected --exact > results/mutation-stale.txt 2>&1; then
  echo 'ERROR: unconditional gate mutant survived' >&2
  exit 1
fi
grep -q 'tests::stale_and_invalid_contact_rejected ... FAILED' results/mutation-stale.txt
sed 's/p.contact = 0.0;/p.contact = NOMINAL.contact;/' main.rs > "$TEMPER_MUTATION/detach.rs"
rustc --edition=2021 --test -O "$TEMPER_MUTATION/detach.rs" -o "$TEMPER_MUTATION/detach"
if "$TEMPER_MUTATION/detach" tests::warm_detach_remains_blind_if_gate_lies --exact > results/mutation-detach.txt 2>&1; then
  echo 'ERROR: erased detach fault mutant survived' >&2
  exit 1
fi
grep -q 'tests::warm_detach_remains_blind_if_gate_lies ... FAILED' results/mutation-detach.txt
printf '%s\n' 'Both isolated fault mutants rejected by actual test assertions.' > results/mutation-summary.txt
