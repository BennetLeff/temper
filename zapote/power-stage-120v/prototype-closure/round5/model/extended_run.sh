#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../../../.." && pwd)
out=${1:?new output directory}
bin=${2:?verified co-simulation binary}
case "$out" in "$root/output/temper-prototype-closure/round5/model/"*) ;; *) exit 2;; esac
mkdir "$out"
model="$root/zapote/power-stage-120v/prototype-closure/round5/model"
shasum -a256 "$model/averaged.cir" "$bin" "$model/extended_run.sh" > "$out/inputs.sha256"
for step in 1.25 .625; do
 sed -e 's/@VRMS@/120/g' -e 's/@RT@/2/g' -e 's/@CL@/1u/g' -e 's/@RP1@/25/g' -e 's/@RP2@/25/g' -e 's/@FAULT@/0/g' -e 's/@FT@/.4/g' -e "s/@STEP@/${step}u/g" -e 's/@END@/1.5/g' "$model/averaged.cir" > "$out/long-${step}us.cir"
 "$bin" "$out/long-${step}us.cir" "$out/long-${step}us" study 2 120 25 25 20 1.5
done
shasum -a256 -c "$out/inputs.sha256" > "$out/input-recheck.log"
