#!/bin/sh
# Export the in-repo inputs a coupling-audit stage run reads, as they were at a commit, into DEST (read-only on the repo).
#   sh validation-results/13-coupling/scripts/export_stage.sh REF DEST [REPO] [BOARD]
#   e.g. sh .../export_stage.sh f7e98c0ec /tmp/s32 "" .../runs-native21/s32/b2/section.kicad_pcb
#        -> run_all.sh --stage native21s32 --root /tmp/s32/zapote/power-stage-120v
# REF is the stage's root_ref (stages.py). REPO defaults to the checkout this script sits in. native-21/section.kicad_pcb
# is not tracked (rules21 reads its net list); BOARD, the stage chain's own board file, is copied there when the commit
# lacks it (b3_maps.py checks its sha256 is the stage's board_sha256).
set -e
REF=$1; DEST=$2; BOARD=$4
REPO=${3:-$(git -C "$(dirname "$0")" rev-parse --show-toplevel)}
P=zapote/power-stage-120v
mkdir -p "$DEST"
PATHS=""
for p in audit.rs tools native-21/frozen native-21/layout native-21/placement.json native-21/stackup.json native-21/section.kicad_pcb native-21/section.kicad_dru native-21/verification \
         validation-plan/enclosure-fit validation-results/10-benchmark validation-results/11-candidates/groups.json \
         validation-results/02-protection-timing/kelvin validation-results/02-protection-timing/coil-pickup/s21b \
         validation-results/02-protection-timing/shoot-through-f1 validation-results/06-controller-interface/cmti \
         validation-results/04-board-current-thermal/round5-native21/b3 \
         validation-results/04-board-current-thermal/round5-native21/b3-convergence \
         validation-results/04-board-current-thermal/round5-native21/b3-ratings; do
  if git -C "$REPO" cat-file -e "$REF:$P/$p" 2>/dev/null; then PATHS="$PATHS $P/$p"; fi
done
git -C "$REPO" archive "$REF" -- $PATHS | tar -x -C "$DEST"
if [ ! -f "$DEST/$P/native-21/section.kicad_pcb" ] && [ -n "$BOARD" ]; then cp "$BOARD" "$DEST/$P/native-21/section.kicad_pcb"; fi
echo "$REF -> $DEST/$P"
