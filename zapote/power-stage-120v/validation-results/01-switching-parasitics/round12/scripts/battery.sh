#!/bin/zsh
# Round 12: run each iterative candidate on every exact fixture.
set -u
R9=${R9:?}; R10=${R10:?}; OUT=${OUT:?}
P=/Users/bennet/Miniforge3/bin/python3; S=${0:A:h}/run_elmer_fixture.py
for cand in "I1 BiCGStabl ILU1" "I2 GCR ILU2" "I3 BiCGStab ILU2"; do
  set -- ${=cand}; c=$1; m=$2; pc=$3
  $P $S $R9/sect-h0p25.msh  $OUT/$c-sect-boundary --pec 2 --port 4 --k 0 0 100 --iterative $m --precond $pc --label $c-sect-boundary
  $P $S $R9/secti-h0p25.msh $OUT/$c-sect-interior --pec 2 --port 4 --k 0 0 100 --iterative $m --precond $pc --label $c-sect-interior
  $P $S $R10/sect2.msh $OUT/$c-sect2-11 --pec 2 --port 4 --k 0 0 100 --iterative $m --precond $pc --label $c-sect2-L11
  $P $S $R10/sect2.msh $OUT/$c-sect2-22 --pec 2 --port 5 --k 0 0 100 --iterative $m --precond $pc --label $c-sect2-L22
  $P $S $R10/sect2.msh $OUT/$c-sect2-12 --pec 2 --port 4 --k 0 0 100 --port2 5 --k2 0 0 100 --iterative $m --precond $pc --label $c-sect2-both
  $P $S $R10/thick-m40-h0p5.msh  $OUT/$c-thick-h0p5  --pec 2 --port 4 --k 0 0 100 --iterative $m --precond $pc --label $c-thick-h0p5
  $P $S $R10/thick-m40-h0p35.msh $OUT/$c-thick-h0p35 --pec 2 --port 4 --k 0 0 100 --iterative $m --precond $pc --label $c-thick-h0p35
done
