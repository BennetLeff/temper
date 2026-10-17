#!/bin/zsh
# phase 3 (after phase 2): option (a) as R_ext with the as-built branch, the device-study CM8 proxy control,
# CM8 finalists (both proxies) on the full and loss grids
S=$(cd "$(dirname "$0")" && pwd)
until grep -q PHASE2DONE $S/../sims/log_phase2.txt; do sleep 20; done
run() { [ -f $S/../sims/$2/$1/results.json ] && return; python3 -I $S/gn.py $1 --cfg $2 --workers 4 || echo "FAIL $1 $2"; }
for r in 8p2 10 12 15; do run s4screen cm8rgc_rext$r; done
for r in 10 12 15 18 22; do run s4screen rext$r; done
for c in c8_split27_1 cm8_split27_1 c8_asbuilt cm8_asbuilt; do run full $c; done
for c in c8_asbuilt c8_split27_1 cm8_asbuilt cm8_split27_1; do run loss $c; done
echo PHASE3DONE
