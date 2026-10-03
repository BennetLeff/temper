#!/bin/zsh
set -euo pipefail

cd ${0:A:h}
label=${1:?coax label required}
log="raw/fixtures/$label-palace.log"
exit_record="raw/fixtures/$label-palace.exit-code"
matrix="raw/fixtures/$label-palace/terminal-M.csv"
test -s "$log"
test -s "$exit_record"

# Palace can write a finite terminal matrix even after PCG says it failed.
# The solver warning is authoritative over the existence of that CSV.
if rg -qi 'did NOT converge|Linear solver did not converge|diverged|Verification failed' "$log"; then
  print -u2 "REJECTED: solver nonconvergence in $log"
  exit 1
fi
if [[ $(cat "$exit_record") != 0 ]]; then
  print -u2 "REJECTED: launch wrapper exit was nonzero in $exit_record"
  exit 1
fi
if ! test -s "$matrix"; then
  print -u2 "REJECTED: terminal matrix missing: $matrix"
  exit 1
fi
print "Structural checks passed for $label; numerical acceptance requires fixture comparison"
