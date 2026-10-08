#!/bin/bash
# Round 18: WHOLE-MACHINE test for the user to schedule (needs the box idle: no chain).
# ~1.5 h. Question: is 1 x 12 ranks the best use of the 12 cores, or do concurrent
# smaller solves (2 x 6, 3 x 4) or hyper-threads give more port-solves per hour?
#
# Mesh: the native-19 leg-B coarse mesh (b19c, 2,496,597 tets, ~15 GB at 12 ranks),
# P1_C40, scaling off, a FIXED 500 iterations so wall time compares directly.
# Each configuration prints Krylov seconds per iteration; for concurrent runs the
# throughput is (number of concurrent solves) / (their mean s per iteration).
#   bash scaling_test.sh > ~/temper-fem/speedup/logs/scaling_test.log 2>&1
set -u
S=$HOME/temper-fem/speedup
cd "$S" || exit 1
if pgrep -x ElmerSolver_mpi > /dev/null; then echo "machine not idle: ElmerSolver_mpi running"; exit 1; fi
M=$HOME/temper-fem/r17/b19c/legB-h1-e1p0-n19.msh
A=(10 2500 0 0)                                        # P1_C40 drive as in campSB19 (campB19 receipts: +2500 A/m along x)
ARGS='--hypre-method 8 --tol 1e-12 --maxit 500 --solver-line "Linear System Scaling = False"'
one() {   # name np cpus [extra mpirun MCA env]
  local name=$1 np=$2 cpus=$3
  eval NP=$np CPUS=$cpus scripts/variant2.sh "scale-$name" "$M" "${A[@]}" $ARGS < /dev/null > /dev/null
}
report() { for n in "$@"; do
  t=$(grep -o "Solution time (method [0-9]*): [0-9.]*" "runs/scale-$n/solver.log" | awk '{print $NF}')
  echo "$n s_per_it=$(echo "$t / 500" | bc -l | cut -c1-6)"; done; }
# single solves, 12 physical cores = CPUs 0-11 (siblings 12-23)
for np in 2 4 6 8 12; do one np$np $np "0-$((np - 1))"; report np$np; done
PRTE_MCA_hwloc_default_use_hwthread_cpus=1 OMPI_MCA_hwloc_base_use_hwthreads_as_cpus=1 one np24ht 24 0-23; report np24ht   # hyper-threads
# concurrent: two solves on the two CCDs (cores 0-5 and 6-11), then three of four cores
one cc2a 6 0-5 & one cc2b 6 6-11 & wait; report cc2a cc2b
one cc3a 4 0-3 & one cc3b 4 4-7 & one cc3c 4 8-11 & wait; report cc3a cc3b cc3c
find runs -path "runs/scale-*" -type f \( -name "case.result*" -o -name "*.vtu" -o -name "*.pvtu" \) -delete
