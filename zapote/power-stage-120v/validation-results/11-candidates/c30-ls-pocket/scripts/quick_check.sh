#!/bin/sh
# Layout aid: one stage-40 build pass and the fast checks (DRC, barrier, return path, bypass, track geometry vs s38).
#   sh quick_check.sh OUTDIR        (runs from the unit root; base / empty DRC under runs-native21/s40)
set -u
U=$(cd "$(dirname "$0")/../../../.." && pwd); cd "$U"
R=/Users/bennet/Desktop/temper/worktrees/runs-native21
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
OUT=$1
INCR21_FROZEN=1 INCR21_PRUNE=1 sh native-21/layout/incr_iter.sh $R/s40/base-s38.json $R/s40/empty-drc.json "$OUT" > "$OUT.log" 2>&1
grep -E "^(barrier|violations|unconnected|plane)" "$OUT.log"
python3 native-21/layout/gates/return_path19.py "$OUT/copper-dump.json" --json "$OUT/rp.json" | tail -1
python3 -c "
import json; r=json.load(open('$OUT/rp.json')); n=0
for k,v in r['signals'].items():
    for c in v.get('reference_changes',[])+v.get('stitches',[]):
        if c.get('mm') is None or c['mm']>3.0: n+=1; print('  open', k, c['at'])
print('return_path_open_changes', n)"
$KPY native-21/layout/gates/bypass_check.py "$OUT/section.kicad_pcb" "$OUT/bypass.json" 2>&1 | grep -E "FAIL|U44|U45" | grep -v -i wxapp
$KPY validation-results/04-board-current-thermal/round4/reextract-b3/extract_geometry.py "$OUT/section.kicad_pcb" "$OUT/native21-all-copper.json.gz" >/dev/null 2>&1
python3 -I native-21/layout/gates/track_geometry.py "$OUT/native21-all-copper.json.gz"
python3 native-21/layout/gates/zone_priority_gate.py native-21/layout/copper.json
