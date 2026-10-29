#!/bin/sh
# Run one loop_matrix mode as N parallel shards and concatenate the rows in shard order (the
# README's manual procedure), then drop the per-case scratch files the run leaves behind unless
# KEEP=1. Usage (from anywhere):
#   sh validation/rev-f-floorplan/run_matrix.sh MODE [N]      e.g. revfestcng100 8
# Writes validation/stability-full-chain/matrix-final_MODE.md. Needs rustc and ngspice 45.2.
set -eu
MODE=$1
N=${2:-8}
cd "$(dirname "$0")/../stability-full-chain"
BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT HUP INT TERM
rustc --edition=2021 -Awarnings -O loop_matrix.rs -o "$BUILD/matrix"
start=$(date +%s)
i=0
while [ "$i" -lt "$N" ]; do
  SHARD="$i/$N" "$BUILD/matrix" "final_$MODE" > "$BUILD/shard$i.log" 2>&1 &
  i=$((i + 1))
done
wait
out="matrix-final_$MODE.md"
head -6 "matrix-final_$MODE-shard0of$N.md" > "$out"
i=0
while [ "$i" -lt "$N" ]; do
  grep '^| final_' "matrix-final_$MODE-shard${i}of$N.md" >> "$out"
  rm "matrix-final_$MODE-shard${i}of$N.md"
  i=$((i + 1))
done
echo "$MODE: $(grep -c '^| final_' "$out") rows in $(( $(date +%s) - start )) s -> $out"
