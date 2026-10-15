#!/bin/bash
# STATUS 2026-10-14: NOT RUN. Item 1 is DEFERRED (six layers not adopted on price; FEM only if a stack-envelope
# route is reopened). Prepared and mesh-gated locally (mesh-gates/); see ../README.md section 1.
# DECISIONS 39 item 1 on the remote FEM box: round 17's native-21 coarse reference (h 1 mm arch, 1.0 mm edges,
# 10 mm crop margin, 12 ranks, Hypre GMRES(100) + singular AMS; the set-up behind leg A 37.6 / leg B 24.5 nH,
# round17/native21-setup/chain_n21.sh step 1) on s32 (four layers, board 2fb346dc) and s33 (six layers, 710c0a45).
# s32 runs with the committed four-layer table (MESH_STACKUP unset); s33 with MESH_STACKUP=stackup-6L.json.
# Closures: round 17's, with R5's two pads re-anchored (closures_for_board.py; R5 moved after board 76ec8cca).
# One case at a time; field files deleted after each matrix lands (the disk rule).
#
# Sync first (from the Mac; the box's vr/ copy predates the MESH_STACKUP hook):
#   rsync -a $U/validation-results/01-switching-parasitics/round17/scripts/ box:~/temper-fem/vr/01-switching-parasitics/round17/scripts/
#   rsync -a $U/validation-results/11-candidates/c33-six-layer/adoption/fem/ box:~/temper-fem/c33/
#   rsync -a $U/native-21/stackup-6L.json box:~/temper-fem/c33/
#   scp runs-native21/s32/b2/native21-all-copper.json.gz box:~/temper-fem/c33/s32-all-copper.json.gz
#   scp runs-native21/s33/b2/native21-all-copper.json.gz box:~/temper-fem/c33/s33-all-copper.json.gz
# Then on the box:  nohup setsid bash ~/temper-fem/c33/chain_c33.sh > ~/temper-fem/c33/chain.out 2>&1 &
# Matrices: ~/temper-fem/c33/<board>-<leg>/<tag>.matrix.txt; parallel loop with fem_compare.py.
source ~/miniconda3/etc/profile.d/conda.sh; conda activate temper-fem
V=$HOME/temper-fem/vr/01-switching-parasitics/round17
C=$HOME/temper-fem/c33
clean() {
  local d=$1 tag=$2
  grep -q "^RESULT" "$d/$tag.matrix.txt" 2>/dev/null || return 1
  find "$d" -path "*/$tag-P*/mesh/*" -type f \( -name "case.result.*" -o -name "*.vtu" -o -name "*.pvtu" \) -delete
  echo "CLEANED $tag" >> "$d/campaign.log"
}
step() {   # board leg: one coarse reference case, clean, or stop the chain
  local b=$1 leg=$2 d=$C/$1-$2 tag=leg$2-h1-e1p0-$1
  mkdir -p "$d"
  if [ "$b" = s33 ]; then export MESH_STACKUP=$C/stackup-6L.json; else unset MESH_STACKUP; fi
  (cd "$d" && python -u $V/scripts/campaign.py "$d" --leg $leg --np 12 --elmer $HOME/temper-fem/elmer-install \
    --export $C/$b-all-copper.json.gz --closures $C/closures-leg${leg:0:1}-$b.json --tag-suffix=-$b \
    --cases 1:1.0 >> campaign.log 2>&1)
  clean "$d" "$tag" || { echo "FAIL $tag, chain stopped" | tee -a "$d/campaign.log"; exit 1; }
  echo "DONE $tag $(date -u +%FT%TZ)"
}
for b in s32 s33; do for L in A21 B21; do step $b $L; done; done
echo C33_FEM_DONE
