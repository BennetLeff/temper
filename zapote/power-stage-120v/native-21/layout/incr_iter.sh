#!/bin/sh
# Incremental native-21 pass: base copper + patches21 + open pairs of DRC_IN -> routed board + DRC.
#   [FILLS=prev/copper-dump.json] sh native-21/layout/incr_iter.sh BASE.json DRC_IN.json[,...] [OUTDIR]
# With DRC_IN "-", only applies BASE (to obtain its DRC).
set -e
UNIT=$(cd "$(dirname "$0")/../.." && pwd)
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
BASE=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
OUT=${3:-$UNIT/native-21/routed}
cd "$UNIT"
. native-21/layout/gates/laps.sh; laps_init incr_iter "$OUT/steps.jsonl"
python3 native-21/layout/place.py
lap place
$KPY prototype-closure/pcb/build_native21.py >/dev/null 2>&1
lap build_native21
python3 native-21/layout/write_rules21.py
lap write_rules21
python3 prototype-closure/pcb/pin_functions21.py >/dev/null
lap pin_functions21
python3 prototype-closure/pcb/build_schematic21.py
lap build_schematic21
$KPY native-21/layout/dump_pads.py native-21/section.kicad_pcb native-21/layout/pads.json >/dev/null 2>&1
lap dump_pads
if [ "$2" = "-" ]; then [ "$BASE" -ef native-21/layout/copper.json ] || cp "$BASE" native-21/layout/copper.json
else python3 native-21/layout/incr21.py "$BASE" "$2" native-21/layout/copper.json "${FILLS:-}"; fi
lap incr21
$KPY prototype-closure/pcb/apply_copper21.py --out "$OUT" 2>/dev/null | grep -v -i wxapp
lap apply_copper21
# board-only parts: bring-up test points, fiducials, mounting holes (board_only21.json)
[ -f native-21/layout/board_only21.json ] && $KPY native-21/layout/board_only21.py "$OUT/section.kicad_pcb" 2>/dev/null | { grep -v -i wxapp || true; }
lap board_only21
# thermal-relief spokes on low-current THT pads (review M3)
# fail loudly: this step once died on a KiCad API change behind 2>/dev/null and the build went on
R=$($KPY native-21/layout/pad_reliefs21.py "$OUT/section.kicad_pcb" 2>&1 | grep -v -i wxapp || true)
echo "$R"
echo "$R" | grep -q "^thermal reliefs on [1-9]" || { echo "pad_reliefs21 failed" >&2; exit 1; }
lap pad_reliefs21
# designators at the fabricator legend minimum, collision-free (positions kept in reference-labels.json)
[ -f native-21/reference-labels.json ] || echo '{"schema": "temper.power-stage-120v.labels.v1", "references": {}}' > native-21/reference-labels.json
$KPY tools/place_reference_labels.py "$OUT/section.kicad_pcb" native-21/reference-labels.json --output native-21/reference-labels.json --fab-unresolved 2>/dev/null \
    | python3 -c 'import sys,json; t=sys.stdin.read(); d=json.loads(t[t.index("{"):]); print("labels:", d["references"] - len(d["unresolved"]), "on silk,", len(d["unresolved"]), "on F.Fab (no clear legend spot)")' 
lap place_reference_labels
[ -f native-21/layout/board_only21.json ] && $KPY native-21/layout/board_only21.py --fix-labels 2>/dev/null
NFP=$(grep -c '(footprint "' "$OUT/section.kicad_pcb")
$KPY tools/apply_reference_labels.py "$OUT/section.kicad_pcb" native-21/reference-labels.json "$OUT/section.kicad_pcb" "$OUT/labels-receipt.json" --components "$NFP" --bounds 0 0 290 190 2>/dev/null | { grep -v -i wxapp || true; }
[ -f native-21/layout/board_only21.json ] && $KPY native-21/layout/board_only21.py --unmirror "$OUT/section.kicad_pcb" 2>/dev/null
lap apply_reference_labels
# schematic beside the board for parity (native-21/section.kicad_sch, build_schematic21.py)
cp native-21/section.kicad_sch native-21/native21.kicad_sym native-21/sym-lib-table "$OUT/"
$CLI pcb drc --refill-zones --save-board --schematic-parity --format json -o "$OUT/drc.json" "$OUT/section.kicad_pcb" >/dev/null 2>&1 || true
lap kicad_drc
$KPY native-21/layout/plot_copper.py --dump "$OUT/section.kicad_pcb" "$OUT/copper-dump.json" >/dev/null 2>&1
lap copper_dump
python3 native-21/layout/plot_copper.py "$OUT/copper-dump.json" "$OUT/copper.png"
lap copper_png
(cd native-21/layout && python3 barrier21.py "$OUT/copper-dump.json" > "$OUT/barrier.txt" 2>&1 || true)
head -1 "$OUT/barrier.txt"
lap barrier21
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
lap drc_summary
