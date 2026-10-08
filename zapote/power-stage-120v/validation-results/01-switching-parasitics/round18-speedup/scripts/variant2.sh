#!/bin/bash
# Round 18: one solver variant (variant2: ELMER=<prefix> selects the install, e.g. speedup/elmer-r18) on a small mesh, inside the experiment budget
# (2 logical CPUs, the hyper-thread siblings of the live chain's cores 10/11;
# the chain's ranks own 0-11 and keep their own siblings 12-21).
#
#   variant2.sh NAME MESH PORT KX KY KZ [run_elmer.py args...]
#
# Runs round-17's run_elmer.py unchanged (copied to ../r17scripts; RUNNER=scripts/run_elmer18.py
# for the round-18 extension), with
# --hypre-ams --ams-singular --np 2 --vtu, writes runs/NAME/ and runs/NAME.out,
# then deletes the field files (case.result.*, *.vtu, *.pvtu) unless KEEP=1.
# Example: variant.sh noscale-gmres meshes/sA-e3.msh 10 2500 0 0 --hypre-method 8 \
#            --tol 1e-8 --maxit 20000 --solver-line "Linear System Scaling = False"
set -u
source ~/miniconda3/etc/profile.d/conda.sh; conda activate temper-fem
S=$HOME/temper-fem/speedup
name=$1 mesh=$2 port=$3 kx=$4 ky=$5 kz=$6; shift 6
cd "$S" || exit 1
rm -rf "runs/$name"
CPUS=${CPUS:-22,23}
NP=${NP:-2}
taskset -c "$CPUS" python3 "${RUNNER:-r17scripts/run_elmer.py}" --elmer "${ELMER:-$HOME/temper-fem/elmer-install}" "$mesh" "runs/$name" \
  --pec 2 3 --port "$port" --k "$kx" "$ky" "$kz" --hypre-ams --ams-singular --np "$NP" --vtu --label "$name" "$@" \
  > "runs/$name.out" 2>&1 < /dev/null
if [ "${KEEP:-0}" != 1 ]; then
  find "runs/$name" -type f \( -name "case.result*" -o -name "*.vtu" -o -name "*.pvtu" \) -delete
fi
tail -1 "runs/$name.out"
