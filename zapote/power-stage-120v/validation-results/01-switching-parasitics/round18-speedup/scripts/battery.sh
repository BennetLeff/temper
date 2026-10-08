#!/bin/bash
# Round 18: run solver variants one after another inside the experiment budget.
#
#   battery.sh LISTFILE
#
# Each non-comment line of LISTFILE is "NAME|PORT KX KY KZ|MESH|run_elmer args".
# Before each variant the script checks the live chain: if any of the chain's
# ElmerSolver_mpi ranks runs in a fine case (tag e0p35 in its working
# directory), it waits (brief §3.3: no experiments during fine cases). It never
# touches the chain's processes. One variant at a time, 2 ranks on CPUs 22,23.
set -u
S=$HOME/temper-fem/speedup
cd "$S" || exit 1
fine_running() {
  for p in $(pgrep -x ElmerSolver_mpi); do
    c=$(readlink "/proc/$p/cwd" 2>/dev/null)
    case "$c" in "$S"*) continue ;; esac          # our own runs
    case "$c" in *e0p35*) return 0 ;; esac
  done
  return 1
}
grep -v '^#' "$1" | grep -v '^\s*$' | while IFS='|' read -r name port mesh args; do
  if [ -f "runs/$name.out" ] && grep -q '"label"' "runs/$name.out"; then echo "SKIP $name (done)"; continue; fi
  while fine_running; do echo "WAIT fine case running $(date +%T)"; sleep 600; done
  while pgrep -f "scripts/variant.sh" > /dev/null; do sleep 60; done   # one variant at a time (ours)
  echo "RUN $name $(date +%T)"
  # shellcheck disable=SC2086
  eval scripts/variant.sh "$name" "$mesh" $port $args
  echo "END $name $(date +%T)"
done
