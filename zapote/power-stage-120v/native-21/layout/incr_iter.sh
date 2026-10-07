#!/bin/sh
# Incremental native-21 pass: base copper + patches21 + open pairs of DRC_IN -> routed board + DRC.
#   sh native-21/layout/incr_iter.sh BASE.json DRC_IN.json [OUTDIR]
# With DRC_IN "-", only applies BASE (to obtain its DRC).
set -e
UNIT=$(cd "$(dirname "$0")/../.." && pwd)
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
BASE=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
OUT=${3:-$UNIT/native-21/routed}
cd "$UNIT"
python3 native-21/layout/place.py
$KPY prototype-closure/pcb/build_native21.py >/dev/null 2>&1
python3 native-21/layout/write_rules21.py
$KPY native-21/layout/dump_pads.py native-21/section.kicad_pcb native-21/layout/pads.json >/dev/null 2>&1
if [ "$2" = "-" ]; then cp "$BASE" native-21/layout/copper.json
else python3 native-21/layout/incr21.py "$BASE" "$2" native-21/layout/copper.json; fi
$KPY prototype-closure/pcb/apply_copper21.py --out "$OUT" 2>/dev/null | grep -v -i wxapp
$CLI pcb drc --refill-zones --save-board --format json -o "$OUT/drc.json" "$OUT/section.kicad_pcb" >/dev/null 2>&1 || true
$KPY native-21/layout/plot_copper.py --dump "$OUT/section.kicad_pcb" "$OUT/copper-dump.json" >/dev/null 2>&1
python3 native-21/layout/plot_copper.py "$OUT/copper-dump.json" "$OUT/copper.png"
(cd native-21/layout && python3 barrier21.py "$OUT/copper-dump.json" > "$OUT/barrier.txt" 2>&1 || true)
head -1 "$OUT/barrier.txt"
python3 - "$OUT/drc.json" <<'PY'
import json, sys, collections, re
d = json.load(open(sys.argv[1]))
c = collections.Counter((v["type"], v["severity"]) for v in d["violations"])
print("violations", sorted(c.items(), key=lambda kv: -kv[1]))
un = d.get("unconnected_items", [])
print("unconnected", len(un))
# a pour split into pieces shows up as zone-to-zone ratsnest: name it, it is a plane cut, not a stray pin
splits = collections.Counter(re.search(r"\[([^\]]*)\] on (\S+)", v["items"][0]["description"]).groups()
                             for v in un if all(i["description"].startswith("Zone") for i in v["items"]))
print("plane splits", dict(splits) or 0)
PY
