#!/bin/bash
# Round 18 follow-on to chain_n21_v2.sh: fine h = 1 mm at 0.45 mm edges for every leg whose
# 0.35 mm fine case the v2 chain's 56 GB memory guard refused (user decision 2026-10-08:
# A21 fine at 0.45 mm; README §5 option 2, ~51 GB estimate, ~1 % shift in the mesh offset).
# A leg whose 0.35 mm fine case v2 did solve keeps it.
#
# Launch (remote) at any time; it waits for chain_n21_v2.sh to exit:
#   cd ~/temper-fem/r17 && nohup setsid bash \
#     ~/temper-fem/vr/01-switching-parasitics/round18-speedup/fine_n21_e0p45.sh \
#     > fine_n21_e0p45.out 2>&1 < /dev/null &
set -u
source ~/miniconda3/etc/profile.d/conda.sh; conda activate temper-fem
VR=$HOME/temper-fem/vr/01-switching-parasitics
V=$VR/round17
C=$VR/round18-speedup/scripts/campaign18.py
export R17_SCRIPTS=$V/scripts
X=$HOME/temper-fem/r17/n21/native21-all-copper.json.gz
R=$HOME/temper-fem/r17
EXTRA="Linear System Scaling = False"
MAXMEM=${MAXMEM:-56}
while pgrep -f "chain_n21_v2.sh" > /dev/null || pgrep -f "campaign18.py" > /dev/null; do
  sleep 300                                    # the v2 chain finishes (or refuses) its fine cases first
done
echo "START $(date -u +%FT%TZ)"
clean() {
  local d=$1 tag=$2
  grep -q "^RESULT" "$d/$tag.matrix.txt" 2>/dev/null || return 1
  find "$d" -path "*/$tag-P*/mesh/*" -type f \( -name "case.result.*" -o -name "*.vtu" -o -name "*.pvtu" \) -delete
  echo "CLEANED $tag" >> "$d/campaign.log"
}
for L in B21 A21; do
  d=$R/camp$L
  if grep -q "^RESULT" "$d/leg$L-h1-e0p35-n21.matrix.txt" 2>/dev/null; then
    echo "KEEP leg$L-h1-e0p35-n21 (solved at 0.35 mm by v2)"; continue
  fi
  tag=leg$L-h1-e0p45-n21
  if grep -q "^RESULT" "$d/$tag.matrix.txt" 2>/dev/null; then echo "REUSED $tag"; continue; fi
  mkdir -p "$d"
  (cd "$d" && python -u "$C" "$d" --leg $L --np 12 --elmer $HOME/temper-fem/elmer-install \
    --export $X --closures $V/closures-leg${L:0:1}-n21.json --tag-suffix=-n21 \
    --max-mem-gb "$MAXMEM" --solver-line "$EXTRA" --cases 1:0.45 >> campaign.log 2>&1)
  if clean "$d" "$tag"; then echo "DONE $tag $(date -u +%FT%TZ)"
  else echo "FAIL $tag $(date -u +%FT%TZ): $(grep -E "^FAIL" "$d/campaign.log" | tail -1)"; fi
done
echo FINE_E0P45_DONE
