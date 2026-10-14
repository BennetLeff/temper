#!/bin/sh
# Native-21 final chain on a routed pass: plan board-only parts, build, all gates, Kelvin, B3, fab package.
#   sh native-21/layout/gates/chain.sh TAG PASSDIR BUILDDIR
# TAG (e.g. native21s16) must already have DIVIDER / BAND_BEFORE (and FLOOR) entries in the kelvin scripts;
# its board hash is pinned here. PASSDIR = the clean pass whose copper-dump plans the test points.
#
# Stage 22 speed-up (same gates, same outputs):
#  1. settle loop: after the build, KiCad-reported dangling tracks / vias are trimmed (trim_tails.py) and only the board
#     is rebuilt (up to 4 times) before any heavy gate runs, instead of a whole chain per cleanup;
#  2. the independent gate blocks run in parallel, each with its own log in BUILDDIR/blk-*.log and its exit status
#     checked: enclosure fit | core regate (Rust barrier, DFM, bypass, copper exports) -> task 04 -> B3 | Kelvin |
#     stage-18/19 copper gates | fab package;
#  3. task 04 and B3 are cached on content keys that exclude the board hash (regate.sh task04; B3 below); every reuse is
#     recorded in the study's outputs/cache.json.
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
mkdir -p "$B"
# ---- build, then settle: trim KiCad-reported dangling tracks / vias and rebuild the board only
for k in 1 2 3 4; do
  sh native-21/layout/incr_iter.sh native-21/layout/copper.json - "$B" > "$B.log" 2>&1
  N=$(python3 -c "import json;print(sum(v['type'] in ('track_dangling','via_dangling') for v in json.load(open('$B/drc.json'))['violations']))")
  [ "$N" = 0 ] && break
  echo "settle $k: $N dangling item(s)"; python3 $G/trim_tails.py "$B/drc.json" native-21/layout/copper.json --write | sed 's/^/  /'
done
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
# Kelvin pin and B3 geometry path for this TAG (edits two scripts; must precede the parallel blocks)
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
BP=$B/section.kicad_pcb
# ---- parallel blocks ---------------------------------------------------------------------------------------------
( $KC pcb export step --force --subst-models --define-var KIPRJMOD=$U/native-21 --output "$B/board.step" "$BP" > "$B/step.log" 2>&1
  uv run --offline --no-project --with cadquery-ocp python $E/board_boxes.py "$B/board.step" $E/native21-boxes.json >/dev/null 2>&1
  $KP $E/body_collisions.py --dump-courtyards "$BP" $E/native21-courtyards.json >/dev/null 2>&1
  python3 $E/body_collisions.py $E/native21-boxes.json $E/native21-courtyards.json $E/native21-envelopes.json > $E/native21-body-collisions.json 2>&1
  python3 $E/board_in_enclosure.py $E/native21-boxes.json $E/native21-courtyards.json $E/native21-envelopes.json > $E/native21-in-r4.json 2>&1 || echo "R4 FAIL"
  python3 -c "import json;a=json.load(open('$E/native21-body-collisions.json'));b=json.load(open('$E/native21-in-r4.json'));print('FIT',a['solids'],a['unattributed'],len(a['part_overlaps']),b['bodies'],len(b['hits']))"
) > "$B/blk-fit.log" 2>&1 &
P_FIT=$!
( $KC pcb export gerbers --output $O/gerbers/ --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts --subtract-soldermask $BP >/dev/null 2>&1
  $KC pcb export drill --output $O/gerbers/ --format excellon --excellon-units mm --excellon-separate-th --generate-map --map-format gerberx2 --generate-report --report-path $O/drill-report.txt $BP >/dev/null 2>&1
  $KC pcb export pos --output $O/positions-kicad.csv --format csv --units mm --side both $BP >/dev/null 2>&1
  $KP validation-results/08-manufacturing-package/native-21/scripts/bom_cpl_jlc.py $BP native-21/frozen/default.csv $O 2>&1 | grep -v -i "wxapp\|Debug:" | tail -1
  python3 validation-results/08-manufacturing-package/native-21/scripts/apply_lcsc.py
  python3 native-21/layout/gates/bom_cpl_check.py $O/bom-jlcpcb.csv $O/cpl-jlcpcb.csv validation-results/08-manufacturing-package/native-21/cpl-rotation-audit/cpl-jlcpcb.corrected.csv || exit 1
  $KC pcb export pdf --mode-multipage --scale 0 --output $O/assembly-drawing.pdf --layers F.Fab,F.Silkscreen,Edge.Cuts --cl Edge.Cuts --sketch-pads-on-fab-layers --black-and-white $BP >/dev/null 2>&1
  python3 validation-results/08-manufacturing-package/native-21/scripts/review_fab.py $O/gerbers validation-results/08-manufacturing-package/native-21/review.json | tail -1
  grep "Total plated\|Total unplated" $O/drill-report.txt
  rm -f $O/native-21-gerbers.zip; (cd $O/gerbers && zip -X -q ../native-21-gerbers.zip $(ls)); echo "ZIP $(shasum -a 256 $O/native-21-gerbers.zip | cut -d' ' -f1)"
) > "$B/blk-fab.log" 2>&1 &
P_FAB=$!
# core regate (barrier, DFM, bypass, copper exports) must finish before the copper-dependent blocks
sh $G/regate.sh "$B" core > "$B/blk-core.log" 2>&1 || { cat "$B/blk-core.log"; echo "REGATE CORE FAILED"; exit 1; }
cp "$B/native21-all-copper.json.gz" native-21/verification/$TAG-all-copper.json.gz
cp "$B/bypass-check.json" native-21/verification/bypass-check-$TAG.json
cp "$B/jlc-dfm.json" validation-results/08-manufacturing-package/native-21/jlc-dfm.json
( sh $G/regate.sh "$B" task04 > "$B/task04.log" 2>&1 || { tail -5 "$B/task04.log"; exit 1; }
  tail -2 "$B/task04.log"
  cd validation-results/04-board-current-thermal/round5-native21/b3
  python3 make_heat_sources.py >/dev/null
  KEY=$(python3 - <<'PY'
import glob, gzip, hashlib, json, re
geo = re.search(r'(native21[0-9a-z]+-all-copper\.json\.gz)', open("run_study.py").read()).group(1)
d = json.load(gzip.open("../../../../native-21/verification/" + geo)); d.pop("board_sha256", None)
h = hashlib.sha256(json.dumps(d, sort_keys=True).encode())
for f in sorted(glob.glob("inputs/*.json")) + ["make_heat_sources.py", "run_study.py", "ceiling_sweep.py", "thermal.py"]:
    h.update(open(f, "rb").read())
for f in sorted(glob.glob("../outputs/*-pl*.json")):
    r = json.load(open(f)); r.pop("board_sha256", None); h.update(json.dumps(r, sort_keys=True).encode())
print(h.hexdigest())
PY
)
  if [ -f outputs/cache.json ] && [ -f outputs/summary.json ] && grep -q "\"key\": \"$KEY\"" outputs/cache.json; then
    python3 -c "import json;p='outputs/cache.json';c=json.load(open(p));c.setdefault('reused_for_boards',[]).append('$H');json.dump(c,open(p,'w'),indent=1)"
    echo "B3 cache hit (copper, heat and task-04 inputs unchanged)"
  else
    python3 run_study.py >/dev/null 2>&1; python3 ceiling_sweep.py
    printf '{"key": "%s", "computed_on_board": "%s", "reused_for_boards": []}\n' "$KEY" "$H" > outputs/cache.json
  fi
  python3 -c "
import json;d=json.load(open('outputs/summary.json'))
print('B3',[(r,round(d['runs'][r]['peak']['temperature_c'],1)) for r in ('nominal_h10_p1p0','nominal_h25_p1p0','extreme_h10_p1p0','c28_h10_p1p0','c28_h25_p1p0')])"
) > "$B/blk-thermal.log" 2>&1 &
P_TH=$!
( cd validation-results/02-protection-timing/kelvin && python3 kelvin_plane.py ../../../native-21/verification/$TAG-all-copper.json.gz $TAG | tail -1 && python3 kelvin_budget.py $TAG | tail -1
) > "$B/blk-kelvin.log" 2>&1 &
P_KV=$!
( python3 validation-results/08-manufacturing-package/native-21/stage18-res-a-creepage/res_a_creepage18.py "$B/copper-dump.json" --json "$B/res-a-creepage.json" | tail -1
  S19=validation-results/08-manufacturing-package/native-21/stage19-pi-si
  $KP $S19/pi_distances19.py "$BP" --json "$B/pi-distances.json" 2>/dev/null | grep -v -i "wxapp\|Debug" | tail -1
  python3 $G/return_path19.py "$B/copper-dump.json" --json "$B/return-path.json" | tail -1
) > "$B/blk-copper.log" 2>&1 &
P_CU=$!
FAIL=""
for pair in "fit:$P_FIT" "fab:$P_FAB" "thermal:$P_TH" "kelvin:$P_KV" "copper:$P_CU"; do
  wait "${pair#*:}" || FAIL="$FAIL ${pair%%:*}"
done
# ---- summary, in the order the serial chain printed it -----------------------------------------------------------
cat "$B/blk-fit.log"
tail -1 "$B/blk-core.log"
python3 -c "import json;g=json.load(open('$B/barrier-gate-rust.json'));print('RUST',g['violations'],g['board_sha256'][:12],g['census']['items'],'RES_A outer 12.6',g['res_a_outer_violations'],{l:r['census']['items'] for l,r in g['res_a_outer'].items()});d=json.load(open('$B/jlc-dfm.json'));print('DFM',d['status'],d['vias'],d['min_track_mm'])"
cat "$B/blk-copper.log"
python3 -c "import json;d=json.load(open('$B/bypass-check.json'));print('BYPASS',d['all_pass'],{k:(v['nearest_cap']['ref'],v['nearest_cap']['supply_pad_to_pad_mm']) for k,v in d['checks'].items()})"
cat "$B/blk-kelvin.log" "$B/blk-thermal.log" "$B/blk-fab.log"
[ -z "$FAIL" ] || { echo "BLOCK FAILED:$FAIL"; exit 1; }
echo CHAIN_DONE
