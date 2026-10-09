#!/bin/bash
# Round 18: one solver variant (variant2: ELMER=<prefix> selects the install, e.g. speedup/elmer-r18) on a small mesh, inside the experiment budget
# (2 logical CPUs, the hyper-thread siblings of the live chain's cores 10/11;
# the chain's ranks own 0-11 and keep their own siblings 12-21).
#
#   variant2.sh NAME MESH PORT KX KY KZ [run_elmer.py args...]
#
# Runs round-17's run_elmer.py unchanged (copied to ../r17scripts; RUNNER=scripts/run_elmer18.py
# for the round-18 extension), with
# --hypre-ams ${NOSING:+} $( [ "${NOSING:-0}" = 1 ] || echo --ams-singular ) --np 2 --vtu, writes runs/NAME/ and runs/NAME.out,
# then deletes the field files (case.result.*, *.vtu, *.pvtu) unless KEEP=1.
# Example: variant.sh noscale-gmres meshes/sA-e3.msh 10 2500 0 0 --hypre-method 8 \
#            --tol 1e-8 --maxit 20000 --solver-line "Linear System Scaling = False"
set -u
source ~/miniconda3/etc/profile.d/conda.sh; conda activate temper-fem
S=$HOME/temper-fem/speedup
name=$1 mesh=$2 port=$3 kx=$4 ky=$5 kz=$6; shift 6
cd "$S" || exit 1
# a finished run is never redone (a queued duplicate would otherwise wipe it)
if [ -f "runs/$name.out" ] && grep -q '"label"' "runs/$name.out"; then echo "SKIP $name (finished)"; exit 0; fi
# The chain's campaign.py waits at the start of every case until NO ElmerSolver_mpi runs
# (ours included), so a run of ours at a case boundary stalls the chain. Found 2026-10-08:
# back-to-back runs held the chain idle ~40 min (08:57-09:3x). Start a run only while the
# chain itself is mid-solve; the chain then waits at most one of our (capped) runs.
chain_solving() {
  for p in $(pgrep -x ElmerSolver_mpi); do
    case "$(readlink "/proc/$p/cwd" 2>/dev/null)" in
      *-e0p*) return 1 ;;                   # fine case (any sub-mm edge): no runs beside it (brief §3.3)
      "$HOME/temper-fem/r17/"*) return 0 ;;
    esac
  done
  return 1
}
until chain_solving; do sleep 20; done
rm -rf "runs/$name"
CPUS=${CPUS:-22,23}
# Open MPI binds ranks to cores by itself (np <= 2: bind-to core) and ignores the taskset
# mask: runs before 2026-10-08 11:45 landed on CPUs 12/13 etc., sharing whichever chain core.
# Binding off keeps the ranks inside the taskset mask.
export OMPI_MCA_hwloc_base_binding_policy=none PRTE_MCA_hwloc_default_binding_policy=none
NP=${NP:-2}
taskset -c "$CPUS" python3 "${RUNNER:-r17scripts/run_elmer.py}" --elmer "${ELMER:-$HOME/temper-fem/elmer-install}" "$mesh" "runs/$name" \
  --pec ${PEC:-2 3} --port "$port" --k "$kx" "$ky" "$kz" --hypre-ams ${NOSING:+} $( [ "${NOSING:-0}" = 1 ] || echo --ams-singular ) --np "$NP" --vtu --label "$name" "$@" \
  > "runs/$name.out" 2>&1 < /dev/null
if [ "${KEEP:-0}" != 1 ]; then
  find "runs/$name" -type f \( -name "case.result*" -o -name "*.vtu" -o -name "*.pvtu" \) -delete
fi
tail -1 "runs/$name.out"
