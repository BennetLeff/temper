#!/bin/bash
# Round 18 proposed native-21 chain: replaces chain_n21.sh from a case boundary.
# What changes (README "Recommendations"):
#   R1 every solve with "Linear System Scaling = False" (Elmer otherwise hands AMS a
#      diagonally scaled matrix with unscaled G/Pi; ~3x fewer iterations, qualified in README);
#   R2 fine extraction at h = 1 mm only (round 17's h1-only recipe, already used for leg B19);
#   R3 a memory guard: a mesh whose estimate (6.1 kB/tet) exceeds MAXMEM GB is not solved
#      (it would swap or OOM the box); the chain reports it and goes on;
#   R5 optional (B21_CORR_ON_MAC=1): leg B21's four coarse corrections run on the Mac
#      (mac_b21corr.sh) while this box runs leg A21's; their matrices land in r17/b21corr-mac/;
#   R4 GMRES restart 30 instead of 100 for the fine cases (smaller Krylov basis), only if
#      README says the ns-thin-k30 test passed: set FINE_EXTRA below accordingly.
# Coarse cases already finished by chain_n21.sh are reused as they are (their matrices
# exist; they were solved at 1e-8 with the old scaling, which is qualified too).
#
# Launch (remote), after stopping ONLY the chain_n21.sh bash process (not campaign.py or
# ElmerSolver_mpi; the running case then finishes on its own and this script waits for it):
#   cp -r <worktree>/.../round18-speedup ~/temper-fem/vr/01-switching-parasitics/
#   nohup setsid bash ~/temper-fem/vr/01-switching-parasitics/round18-speedup/chain_n21_v2.sh \
#     > ~/temper-fem/r17/chain_n21_v2.out 2>&1 &
set -u
source ~/miniconda3/etc/profile.d/conda.sh; conda activate temper-fem
VR=$HOME/temper-fem/vr/01-switching-parasitics
V=$VR/round17
C=$VR/round18-speedup/scripts/campaign18.py
export R17_SCRIPTS=$V/scripts
X=$HOME/temper-fem/r17/n21/native21-all-copper.json.gz
R=$HOME/temper-fem/r17
EXTRA="Linear System Scaling = False"
FINE_EXTRA=${FINE_EXTRA:-}            # e.g. "HYPRE GmRes Dimension = Integer 30" (R4)
MAXMEM=${MAXMEM:-56}
while pgrep -f "round17/scripts/campaign.py|campaign18.py" > /dev/null || pgrep -x ElmerSolver_mpi > /dev/null; do
  sleep 60                                     # the old chain's last case finishes first
done
clean() {
  local d=$1 tag=$2
  grep -q "^RESULT" "$d/$tag.matrix.txt" 2>/dev/null || return 1
  find "$d" -path "*/$tag-P*/mesh/*" -type f \( -name "case.result.*" -o -name "*.vtu" -o -name "*.pvtu" \) -delete
  echo "CLEANED $tag" >> "$d/campaign.log"
}
run() {
  local d=$1 leg=$2 extra2=$3; shift 3
  local -a sl=(--solver-line "$EXTRA")
  [ -n "$extra2" ] && sl+=(--solver-line "$extra2")
  mkdir -p "$d"
  cd "$d" && python -u "$C" "$d" --leg $leg --np 12 --elmer $HOME/temper-fem/elmer-install \
    --export $X --closures $V/closures-leg${leg:0:1}-n21.json --tag-suffix=-n21 \
    --max-mem-gb "$MAXMEM" "${sl[@]}" "$@" >> campaign.log 2>&1
}
step() {   # dir leg tag fatal extra2 args...: run one case (or reuse it), clean
  local d=$1 leg=$2 tag=$3 fatal=$4 extra2=$5; shift 5
  if grep -q "^RESULT" "$d/$tag.matrix.txt" 2>/dev/null; then
    clean "$d" "$tag"; echo "REUSED $tag"; return 0
  fi
  run "$d" $leg "$extra2" "$@"
  if clean "$d" "$tag"; then echo "DONE $tag $(date -u +%FT%TZ)"; return 0; fi
  echo "FAIL $tag $(date -u +%FT%TZ): $(grep -E "^FAIL" "$d/campaign.log" | tail -1)" | tee -a "$d/campaign.log"
  [ "$fatal" = 1 ] && { echo "chain stopped"; exit 1; }
  return 1
}
for L in A21 B21; do step $R/${L,,}c $L leg$L-h1-e1p0-n21 1 "" --cases 1:1.0; done
echo BASE_DONE
for L in A21 B21; do
  if [ "$L" = B21 ] && [ "${B21_CORR_ON_MAC:-0}" = 1 ]; then
    echo "B21 corrections on the Mac (mac_b21corr.sh -> $R/b21corr-mac/)"; continue
  fi
  for h in 0.5 2 3; do step $R/${L,,}corr $L leg$L-h${h/./p}-e1p0-n21 1 "" --cases $h:1.0; done
  step $R/${L,,}corr $L leg$L-h1-e1p0-m20-a10-n21 1 "" --cases 1:1.0 --margin 20
done
echo CORR_DONE
# R2: fine h = 1 mm only. Leg B first: estimated 9.4 M tets / ~57 GB (fits only with R4 or at
# the guard's edge); leg A estimated 11.6 M tets / ~71 GB: refused by the guard unless the
# machine gets more memory (README "Needs the whole machine / the user").
step $R/campB21 B21 legB21-h1-e0p35-n21 0 "$FINE_EXTRA" --cases 1:0.35
step $R/campA21 A21 legA21-h1-e0p35-n21 0 "$FINE_EXTRA" --cases 1:0.35
echo FINE_DONE
