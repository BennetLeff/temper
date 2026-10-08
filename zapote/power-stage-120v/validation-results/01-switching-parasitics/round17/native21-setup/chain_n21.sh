#!/bin/bash
# Native-21 extraction on the remote box (2026-10-08), after chain_legB19_v2.sh's pattern.
# Order puts the earliest useful numbers first:
#   1) coarse base matrix (h 1 mm, 1.0 mm edges), leg A then leg B: first comparison with native-19;
#   2) coarse corrections per leg: h 0.5 / 2 / 3 mm, and h 1 mm at a 20 mm crop;
#   3) fine extraction per leg: h 1 / 2 / 3 mm at 0.35 mm edges.
# One case at a time; field files (case.result.*, *.vtu, *.pvtu) deleted after each matrix lands.
#   nohup setsid bash chain_n21.sh > ~/temper-fem/r17/chain_n21.out 2>&1 &
source ~/miniconda3/etc/profile.d/conda.sh; conda activate temper-fem
V=$HOME/temper-fem/vr/01-switching-parasitics/round17
X=$HOME/temper-fem/r17/n21/native21-all-copper.json.gz
R=$HOME/temper-fem/r17
clean() {
  local d=$1 tag=$2
  grep -q "^RESULT" "$d/$tag.matrix.txt" 2>/dev/null || return 1
  find "$d" -path "*/$tag-P*/mesh/*" -type f \( -name "case.result.*" -o -name "*.vtu" -o -name "*.pvtu" \) -delete
  echo "CLEANED $tag" >> "$d/campaign.log"
}
run() {
  local d=$1 leg=$2; shift 2
  mkdir -p "$d"
  cd "$d" && python -u $V/scripts/campaign.py "$d" --leg $leg --np 12 --elmer $HOME/temper-fem/elmer-install \
    --export $X --closures $V/closures-leg${leg:0:1}-n21.json --tag-suffix=-n21 "$@" >> campaign.log 2>&1
}
step() {   # dir leg tag args...: run one case, clean, or stop the chain
  local d=$1 leg=$2 tag=$3; shift 3
  run "$d" $leg "$@"
  clean "$d" "$tag" || { echo "FAIL $tag, chain stopped" | tee -a "$d/campaign.log"; exit 1; }
  echo "DONE $tag $(date -u +%FT%TZ)"
}
for L in A21 B21; do step $R/${L,,}c $L leg$L-h1-e1p0-n21 --cases 1:1.0; done
echo BASE_DONE
for L in A21 B21; do
  for h in 0.5 2 3; do step $R/${L,,}corr $L leg$L-h${h/./p}-e1p0-n21 --cases $h:1.0; done
  step $R/${L,,}corr $L leg$L-h1-e1p0-m20-a10-n21 --cases 1:1.0 --margin 20
done
echo CORR_DONE
for L in A21 B21; do
  for h in 1 2 3; do step $R/camp${L} $L leg$L-h$h-e0p35-n21 --cases $h:0.35; done
done
echo FINE_DONE
