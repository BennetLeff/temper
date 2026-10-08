#!/bin/bash
# Round 18 option: the Mac solves leg B21's four coarse corrections while the remote box
# does leg A21's (chain_n21_v2.sh with B21_CORR_ON_MAC=1 skips them there). DESIGN ONLY:
# not run by round 18. Prerequisites (README "The Mac as a second node"):
#   - an Elmer + Hypre install on the Mac (round 17's /tmp/ps-r6-fem-elmer-install is gone;
#     rebuild Elmer a19504a against conda-forge hypre 2.32, as round 17 did) -> ELMER=<prefix>;
#   - the native-21 copper export (remote ~/temper-fem/r17/n21/native21-all-copper.json.gz);
#   - nothing else heavy on the Mac (memory note: 8 ranks max, ~20x collapse when oversubscribed);
#   - >= 15 GB free disk (field files of one case, ~12.5 GB at m20, deleted after each matrix).
# Each case: mesh, gates, 4 port solves at 8 ranks, matrix, delete field files, copy the
# matrix and log to the remote box (~/temper-fem/r17/b21corr-mac/).
set -u
ELMER=${ELMER:?Elmer install prefix on the Mac}
X=${X:?native21-all-copper.json.gz on the Mac}
W=${W:-$HOME/temper-fem-mac/b21corr}
HERE=$(cd "$(dirname "$0")" && pwd)
export R17_SCRIPTS=$HERE/../round17/scripts
REMOTE="ssh -o ControlPath=$HOME/.ssh/cm/fem bennet@100.121.239.87"
mkdir -p "$W"
for c in "0.5:1.0" "2:1.0" "3:1.0" "1:1.0 --margin 20"; do
  h=${c%%:*}; tag=legB21-h${h/./p}-e1p0$( [[ $c == *margin* ]] && echo -m20-a10 )-n21
  if ! grep -q "^RESULT" "$W/$tag.matrix.txt" 2>/dev/null; then
    # shellcheck disable=SC2086
    python3 -u "$HERE/scripts/campaign18.py" "$W" --leg B21 --np 8 --elmer "$ELMER" --export "$X" \
      --closures "$HERE/../round17/closures-legB-n21.json" --tag-suffix=-n21 --max-mem-gb 26 \
      --solver-line "Linear System Scaling = False" --cases $c >> "$W/campaign.log" 2>&1
  fi
  grep -q "^RESULT" "$W/$tag.matrix.txt" || { echo "FAIL $tag"; exit 1; }
  find "$W" -path "*/$tag-P*/mesh/*" -type f \( -name "case.result.*" -o -name "*.vtu" -o -name "*.pvtu" \) -delete
  $REMOTE "mkdir -p ~/temper-fem/r17/b21corr-mac" && \
    scp -o ControlPath="$HOME/.ssh/cm/fem" "$W/$tag.matrix.txt" "$W/campaign.log" "bennet@100.121.239.87:temper-fem/r17/b21corr-mac/"
  echo "DONE $tag $(date -u +%FT%TZ)"
done
