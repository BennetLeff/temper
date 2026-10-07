#!/bin/sh
# Rebuild native-21: placement -> board -> rules -> authored copper -> fill + DRC -> plots.
#   sh native-21/layout/copper_iter.sh [OUTDIR]
set -e
UNIT=$(cd "$(dirname "$0")/../.." && pwd)
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
OUT=${1:-$UNIT/native-21/routed}
cd "$UNIT"
python3 native-21/layout/place.py
$KPY prototype-closure/pcb/build_native21.py >/dev/null 2>&1
python3 native-21/layout/write_rules21.py
python3 native-21/layout/route21.py
$KPY prototype-closure/pcb/apply_copper21.py --out "$OUT" 2>/dev/null | grep -v -i wxapp
$CLI pcb drc --refill-zones --save-board --format json -o "$OUT/drc.json" "$OUT/section.kicad_pcb" >/dev/null 2>&1 || true
$KPY native-21/layout/plot_copper.py --dump "$OUT/section.kicad_pcb" "$OUT/copper-dump.json" >/dev/null 2>&1
python3 native-21/layout/plot_copper.py "$OUT/copper-dump.json" "$OUT/copper.png"
python3 - "$OUT/drc.json" <<'PY'
import json, sys, collections
d = json.load(open(sys.argv[1]))
c = collections.Counter((v["type"], v["severity"]) for v in d["violations"])
print("violations", sorted(c.items(), key=lambda kv: -kv[1]))
print("unconnected", len(d.get("unconnected_items", [])))
PY
