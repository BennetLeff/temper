#!/bin/sh
# Native-21 final chain on a routed pass: plan board-only parts, build, all gates, Kelvin, B3, fab package.
#   sh native-21/layout/gates/chain.sh TAG PASSDIR BUILDDIR
# TAG (e.g. native21s16) must already have DIVIDER / BAND_BEFORE (and FLOOR) entries in the kelvin scripts;
# its board hash is pinned here. PASSDIR = the clean pass whose copper-dump plans the test points.
set -e
TAG=$1; PASS=$2; B=$3
U=$(cd "$(dirname "$0")/../../.." && pwd)
G=$U/native-21/layout/gates
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
KC=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
E=validation-plan/enclosure-fit; O=validation-results/08-manufacturing-package/native-21/fab
cd "$U"
python3 native-21/layout/plan_board_only21.py "$PASS/copper-dump.json" | grep -E "TPs|^holes|fiducials" | cut -c1-200
python3 $G/zone_priority_gate.py native-21/layout/copper.json   # stage 17b: no fill-order-dependent pours
mkdir -p "$B"; sh native-21/layout/incr_iter.sh native-21/layout/copper.json - "$B" > "$B.log" 2>&1
grep -E "^unconnected|thermal reliefs|labels|plane splits" "$B.log"; head -1 "$B/barrier.txt"
echo "errors $(python3 $G/count_errors.py $B/drc.json)"; tail -3 "$B.log" | grep violations
H=$(shasum -a 256 "$B/section.kicad_pcb" | cut -d' ' -f1); echo "BOARD $H"
$KP native-21/layout/dump_pads.py "$B/section.kicad_pcb" "$B/pads-board.json" >/dev/null 2>&1
python3 native-21/verification/d5_audit.py "$B/copper-dump.json" "$B/pads-board.json" >/dev/null 2>&1
python3 -c "import json;d=json.load(open('native-21/verification/d5-audit.json'));print('D5',d['verdict_pcb'],d['copper']['HOT-SELV']['min_mm'],d['copper']['HOT-PE']['min_mm'])"
python3 native-21/layout/probe_map21.py
$KC sch erc --format json --output "$B/erc.json" "$B/section.kicad_sch" >/dev/null 2>&1 || true
python3 -c "
import json,collections;d=json.load(open('$B/erc.json'));c=collections.Counter()
[c.update([(v['severity'],v['type'])]) for sh in d.get('sheets',[]) for v in sh.get('violations',[])];print('ERC',dict(c))"
$KC pcb export step --force --subst-models --define-var KIPRJMOD=$U/native-21 --output "$B/board.step" "$B/section.kicad_pcb" > "$B/step.log" 2>&1
uv run --offline --no-project --with cadquery-ocp python $E/board_boxes.py "$B/board.step" $E/native21-boxes.json >/dev/null 2>&1
$KP $E/body_collisions.py --dump-courtyards "$B/section.kicad_pcb" $E/native21-courtyards.json >/dev/null 2>&1
python3 $E/body_collisions.py $E/native21-boxes.json $E/native21-courtyards.json $E/native21-envelopes.json > $E/native21-body-collisions.json 2>&1
python3 $E/board_in_enclosure.py $E/native21-boxes.json $E/native21-courtyards.json $E/native21-envelopes.json > $E/native21-in-r4.json 2>&1 || echo "R4 FAIL"
python3 -c "import json;a=json.load(open('$E/native21-body-collisions.json'));b=json.load(open('$E/native21-in-r4.json'));print('FIT',a['solids'],a['unattributed'],len(a['part_overlaps']),b['bodies'],len(b['hits']))"
sh $G/regate.sh "$B" | tail -1
python3 -c "import json;g=json.load(open('$B/barrier-gate-rust.json'));print('RUST',g['violations'],g['board_sha256'][:12],g['census']['items']);d=json.load(open('$B/jlc-dfm.json'));print('DFM',d['status'],d['vias'],d['min_track_mm'])"
cp "$B/native21-all-copper.json.gz" native-21/verification/$TAG-all-copper.json.gz
python3 - "$H" "$TAG" <<'PY'
import re, sys
h, tag = sys.argv[1], sys.argv[2]
p = 'validation-results/02-protection-timing/kelvin/kelvin_plane.py'; s = open(p).read()
pin = re.search(r'"%s": "[0-9a-f]{64}"' % re.escape(tag), s)
if pin:
    s = s.replace(pin.group(0), f'"{tag}": "{h}"')
else:
    last = list(re.finditer(r'"native21[0-9a-z]+": "[0-9a-f]{64}"\}', s))[-1].group(0)
    s = s.replace(last, last[:-1] + f',\n              "{tag}": "{h}"}}')
open(p, 'w').write(s)
p = 'validation-results/04-board-current-thermal/round5-native21/b3/run_study.py'; s = open(p).read()
s = re.sub(r'native21[0-9a-z]+-all-copper\.json\.gz', f'{tag}-all-copper.json.gz', s, count=1)
open(p, 'w').write(s)
PY
(cd validation-results/02-protection-timing/kelvin && python3 kelvin_plane.py ../../../native-21/verification/$TAG-all-copper.json.gz $TAG | tail -1 && python3 kelvin_budget.py $TAG | tail -1)
(cd validation-results/04-board-current-thermal/round5-native21/b3 && python3 make_heat_sources.py >/dev/null && python3 run_study.py >/dev/null 2>&1; python3 ceiling_sweep.py; python3 -c "
import json;d=json.load(open('outputs/summary.json'))
print('B3',[(r,round(d['runs'][r]['peak']['temperature_c'],1)) for r in ('nominal_h10_p1p0','nominal_h25_p1p0','extreme_h10_p1p0','c28_h10_p1p0','c28_h25_p1p0')])")
BP=$B/section.kicad_pcb
$KC pcb export gerbers --output $O/gerbers/ --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts --subtract-soldermask $BP >/dev/null 2>&1
$KC pcb export drill --output $O/gerbers/ --format excellon --excellon-units mm --excellon-separate-th --generate-map --map-format gerberx2 --generate-report --report-path $O/drill-report.txt $BP >/dev/null 2>&1
$KC pcb export pos --output $O/positions-kicad.csv --format csv --units mm --side both $BP >/dev/null 2>&1
$KP validation-results/08-manufacturing-package/native-21/scripts/bom_cpl_jlc.py $BP native-21/frozen/default.csv $O 2>&1 | grep -v -i "wxapp\|Debug:" | tail -1
python3 validation-results/08-manufacturing-package/native-21/scripts/apply_lcsc.py
$KC pcb export pdf --mode-multipage --scale 0 --output $O/assembly-drawing.pdf --layers F.Fab,F.Silkscreen,Edge.Cuts --cl Edge.Cuts --sketch-pads-on-fab-layers --black-and-white $BP >/dev/null 2>&1
python3 validation-results/08-manufacturing-package/native-21/scripts/review_fab.py $O/gerbers validation-results/08-manufacturing-package/native-21/review.json | tail -1
grep "Total plated\|Total unplated" $O/drill-report.txt
rm -f $O/native-21-gerbers.zip; (cd $O/gerbers && zip -X -q ../native-21-gerbers.zip $(ls)); echo "ZIP $(shasum -a 256 $O/native-21-gerbers.zip | cut -d' ' -f1)"
cp "$B/jlc-dfm.json" validation-results/08-manufacturing-package/native-21/jlc-dfm.json
echo CHAIN_DONE
