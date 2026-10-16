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
#
# Scoped mode (gates/scoped/README.md): `scoped_chain.py run` sets SCOPED_PLAN=BUILDDIR/scoped-plan.json, which marks every
# step RUN or REUSE against a benchmark build; `want STEP` is true for a step to run. Without SCOPED_PLAN (the full chain,
# mandatory at merge to the integration branch) every step runs, as before. The last step writes BUILDDIR/scoped-manifest.json
# (content keys of this build), which makes any full-chain build a benchmark for later scoped runs.
set -e
# a failing step must stop the chain even when its output is piped through grep / tail (a wrong PASSDIR once
# ran a whole chain on the previous test-point plan because `planner | grep` hid the traceback)
set -o pipefail
TAG=$1; PASS=$2; B=$3
[ -f "$PASS/copper-dump.json" ] || { echo "chain: no $PASS/copper-dump.json (PASSDIR is a pass's iN dir)" >&2; exit 1; }
U=$(cd "$(dirname "$0")/../../.." && pwd)
G=$U/native-21/layout/gates
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
KC=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
E=validation-plan/enclosure-fit; O=validation-results/08-manufacturing-package/native-21/fab
cd "$U"
want() {
  [ -z "${SCOPED_PLAN:-}" ] && return 0
  python3 -I -c "import json,sys;sys.exit(json.load(open(sys.argv[1]))['steps'][sys.argv[2]]['do'] not in ('RUN','RUN?'))" "$SCOPED_PLAN" "$1"
}
if want build; then
python3 native-21/layout/plan_board_only21.py "$PASS/copper-dump.json" | grep -E "TPs|^holes|fiducials" | cut -c1-200
python3 $G/zone_priority_gate.py native-21/layout/copper.json   # stage 17b: no fill-order-dependent pours
mkdir -p "$B"
# ---- build, then settle: trim KiCad-reported dangling tracks / vias and rebuild the board only
# Every trim is followed by a rebuild, so the gated board is always the build of the committed copper.json (stage 27: a
# stub chain on leg_b-permit_gate needed four trims, and the old 4-pass loop gated the board built before the last one).
k=0
while :; do
  k=$((k + 1))
  sh native-21/layout/incr_iter.sh native-21/layout/copper.json - "$B" > "$B.log" 2>&1
  N=$(python3 -c "import json;print(sum(v['type'] in ('track_dangling','via_dangling') for v in json.load(open('$B/drc.json'))['violations']))")
  [ "$N" = 0 ] && break
  [ "$k" -ge 8 ] && { echo "settle: still $N dangling item(s) after $k builds" >&2; exit 1; }
  echo "settle $k: $N dangling item(s)"; python3 $G/trim_tails.py "$B/drc.json" native-21/layout/copper.json --write | sed 's/^/  /'
done
grep -E "^unconnected|thermal reliefs|labels|plane splits" "$B.log"; head -1 "$B/barrier.txt"
echo "errors $(python3 $G/count_errors.py $B/drc.json)"; tail -3 "$B.log" | grep violations
else
  # scoped, no board input changed: BUILDDIR is the scoped run's copy of the benchmark build (same board_sha256)
  echo "scoped: board build reused from the benchmark"; head -1 "$B/barrier.txt"
  echo "errors $(python3 $G/count_errors.py $B/drc.json)"
fi
# copper-temperature basis (OPEN-ITEMS S17): every consumer of copper resistance / loss in the scorecard input chain
# carries a declared basis (cu_temp_registry.json) or passes an explicit temperature. Static, about 1 s, no board data.
# (no pipe: in sh a pipeline takes the exit status of its last command, so `| tail` would hide a failure)
python3 -I $G/cu_temp_basis.py --fail-waived --report "$B/cu-temp-basis.json" > "$B/cu-temp-basis.log" 2>&1 || {
  tail -20 "$B/cu-temp-basis.log" >&2; echo "cu_temp_basis: FAILED" >&2; exit 1; }
tail -4 "$B/cu-temp-basis.log"
H=$(shasum -a 256 "$B/section.kicad_pcb" | cut -d' ' -f1); echo "BOARD $H"
if want d5; then
$KP native-21/layout/dump_pads.py "$B/section.kicad_pcb" "$B/pads-board.json" >/dev/null 2>&1
python3 native-21/verification/d5_audit.py "$B/copper-dump.json" "$B/pads-board.json" >/dev/null 2>&1
fi
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
# copper layers for the Gerbers, top to bottom, from native-21/stackup.json (stage 33)
CUL=$(python3 -c "import sys; sys.path.insert(0, 'native-21/layout'); import layers21; print(','.join(layers21.CU))")
case "$CUL" in F.Cu,*,B.Cu) ;; *) echo "layers21 failed: $CUL" >&2; exit 1;; esac
# ---- parallel blocks ---------------------------------------------------------------------------------------------
( $KC pcb export step --force --subst-models --define-var KIPRJMOD=$U/native-21 --output "$B/board.step" "$BP" > "$B/step.log" 2>&1
  uv run --offline --no-project --with cadquery-ocp python $E/board_boxes.py "$B/board.step" $E/native21-boxes.json >/dev/null 2>&1
  $KP $E/body_collisions.py --dump-courtyards "$BP" $E/native21-courtyards.json >/dev/null 2>&1
  python3 $E/body_collisions.py $E/native21-boxes.json $E/native21-courtyards.json $E/native21-envelopes.json > $E/native21-body-collisions.json 2>&1
  python3 $E/board_in_enclosure.py $E/native21-boxes.json $E/native21-courtyards.json $E/native21-envelopes.json > $E/native21-in-r4.json 2>&1 || echo "R4 FAIL"
  # OPEN-ITEMS S2 airflow route: nothing over 4 mm under the jet box (temper-8d airflow-r1 D6.2)
  python3 native-21/layout/gates/jet_strip_height.py $E/native21-boxes.json $E/native21-courtyards.json $E/native21-jet-strip.json || echo "JET STRIP FAIL"
  python3 -c "import json;a=json.load(open('$E/native21-body-collisions.json'));b=json.load(open('$E/native21-in-r4.json'));print('FIT',a['solids'],a['unattributed'],len(a['part_overlaps']),b['bodies'],len(b['hits']))"
) > "$B/blk-fit.log" 2>&1 &
P_FIT=$!
( $KC pcb export gerbers --output $O/gerbers/ --layers $CUL,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts --subtract-soldermask $BP >/dev/null 2>&1
  $KC pcb export drill --output $O/gerbers/ --format excellon --excellon-units mm --excellon-separate-th --generate-map --map-format gerberx2 --generate-report --report-path $O/drill-report.txt $BP >/dev/null 2>&1
  $KC pcb export pos --output $O/positions-kicad.csv --format csv --units mm --side both $BP >/dev/null 2>&1
  $KP validation-results/08-manufacturing-package/native-21/scripts/bom_cpl_jlc.py $BP native-21/frozen/default.csv $O 2>&1 | grep -v -i "wxapp\|Debug:" | tail -1
  python3 validation-results/08-manufacturing-package/native-21/scripts/apply_lcsc.py
  # CPL rotation audit on this board (stage 22 committed a stale audit that never saw U22 / U23 / U40)
  ( cd validation-results/08-manufacturing-package/native-21/cpl-rotation-audit && python3 -I extract_kicad.py $BP >/dev/null && python3 -I audit.py | tail -1 ) || exit 1
  python3 -c "import csv;import json;A='validation-results/08-manufacturing-package/native-21/cpl-rotation-audit/';lc={d.strip():r['LCSC Part #'].strip() for r in csv.DictReader(open('$O/bom-jlcpcb.csv')) for d in r['Designator'].split(',')};a={r['designator'] for r in csv.DictReader(open(A+'audit.csv'))}|{x['designator'] for x in json.load(open(A+'audit.json'))['excluded'] if not lc.get(x['designator'])};c={r['Designator'] for r in csv.DictReader(open('$O/cpl-jlcpcb.csv'))};m=sorted(c-a);print('CPL audit covers',len(c&a),'of',len(c));assert not m,('CPL lines not audited (or excluded although they now have an LCSC code)',m)" || exit 1
  python3 native-21/layout/gates/bom_cpl_check.py $O/bom-jlcpcb.csv $O/cpl-jlcpcb.csv validation-results/08-manufacturing-package/native-21/cpl-rotation-audit/cpl-jlcpcb.corrected.csv || exit 1
  $KC pcb export pdf --mode-multipage --scale 0 --output $O/assembly-drawing.pdf --layers F.Fab,F.Silkscreen,Edge.Cuts --cl Edge.Cuts --sketch-pads-on-fab-layers --black-and-white $BP >/dev/null 2>&1
  python3 validation-results/08-manufacturing-package/native-21/scripts/review_fab.py $O/gerbers validation-results/08-manufacturing-package/native-21/review.json | tail -1
  grep "Total plated\|Total unplated" $O/drill-report.txt
  rm -f $O/native-21-gerbers.zip; (cd $O/gerbers && zip -X -q ../native-21-gerbers.zip $(ls)); echo "ZIP $(shasum -a 256 $O/native-21-gerbers.zip | cut -d' ' -f1)"
) > "$B/blk-fab.log" 2>&1 &
P_FAB=$!
# core regate (barrier, DFM, bypass, copper exports) must finish before the copper-dependent blocks
SKIP_BAR=""; want core_barrier || SKIP_BAR=1
REGATE_SKIP_BARRIER=$SKIP_BAR sh $G/regate.sh "$B" core > "$B/blk-core.log" 2>&1 || { cat "$B/blk-core.log"; echo "REGATE CORE FAILED"; exit 1; }
cp "$B/native21-all-copper.json.gz" native-21/verification/$TAG-all-copper.json.gz
cp "$B/bypass-check.json" native-21/verification/bypass-check-$TAG.json
cp "$B/jlc-dfm.json" validation-results/08-manufacturing-package/native-21/jlc-dfm.json
CK=$($KP $G/copper_key.py "$B/section.kicad_pcb" 2>/dev/null | tail -1)
case "$CK" in [0-9a-f]*) ;; *) echo "copper_key failed" >&2; exit 1;; esac
# scoped: decide the keyed thermal steps and the manual card inputs on this build's keys (writes SCOPED_PLAN)
if [ -n "${SCOPED_PLAN:-}" ]; then python3 -I $G/scoped/scoped_chain.py decide "$B" "$SCOPED_PLAN" || { echo "SCOPED DECIDE FAILED"; exit 1; }; fi
( # B3's heat inputs first: they are part of the shared model key (model_key.py) that task 04's cache key also takes
  ( cd validation-results/04-board-current-thermal/round5-native21/b3 && python3 make_heat_sources.py >/dev/null )
  if want task04; then
  sh $G/regate.sh "$B" task04 > "$B/task04.log" 2>&1 || { tail -5 "$B/task04.log"; exit 1; }
  tail -2 "$B/task04.log"
  else echo "scoped: task 04 reused from the benchmark (key in $SCOPED_PLAN)" | tee "$B/task04.log"; fi
  # key: the board's copper inputs (copper_key.py; the refilled copper is not bit-reproducible), the shared model key
  # (model_key.py: every task-04 and B3 script, the heat sources, the stackup file(s), SHEET_BARREL; stage 33, so a
  # model change misses both caches together) and the task-04 results B3 reads
  b3key() { python3 - "$CK" "$(python3 $G/model_key.py | tail -1)" <<'PY'
import glob, hashlib, json, sys
h = hashlib.sha256(("b3|" + sys.argv[1] + "|" + sys.argv[2]).encode())
for f in sorted(glob.glob("../outputs/*-pl*.json")):
    r = json.load(open(f)); r.pop("board_sha256", None); h.update(json.dumps(r, sort_keys=True).encode())
print(h.hexdigest())
PY
  }
  cd validation-results/04-board-current-thermal/round5-native21/b3
  if want b3_study; then
  KEY=$(b3key)
  b3hit() { [ -f outputs/cache.json ] && [ -f outputs/summary.json ] && grep -q "\"key\": \"$KEY\"" outputs/cache.json; }
  if ! b3hit && grep -q "task04 cache hit" "$B/task04.log"; then
    # B3 must recompute but task 04 reused results computed on another build of this copper; B3's same-board check
    # (thermal.py) would then fail. With the shared model key this means B3's cache was lost or overwritten
    # elsewhere, so recompute task 04 on this build too instead of failing late.
    echo "B3 miss after a task-04 hit: recomputing task 04 on this build"
    ( cd "$U" && TASK04_FORCE=1 sh $G/regate.sh "$B" task04 > "$B/task04-forced.log" 2>&1 ) || { tail -5 "$B/task04-forced.log"; exit 1; }
    tail -1 "$B/task04-forced.log"; KEY=$(b3key)
  fi
  if b3hit; then
    python3 -c "import json;p='outputs/cache.json';c=json.load(open(p));c.setdefault('reused_for_boards',[]).append('$H');json.dump(c,open(p,'w'),indent=1)"
    echo "B3 cache hit (copper, model and task-04 inputs unchanged)"
  else
    python3 run_study.py >/dev/null 2>&1; python3 ceiling_sweep.py
    printf '{"key": "%s", "computed_on_board": "%s", "reused_for_boards": []}\n' "$KEY" "$H" > outputs/cache.json
  fi
  else echo "scoped: B3 study and ceiling sweep reused from the benchmark (key in $SCOPED_PLAN)"; fi
  python3 -c "
import json;d=json.load(open('outputs/summary.json'))
print('B3',[(r,round(d['runs'][r]['peak']['temperature_c'],1)) for r in ('nominal_h10_p1p0','nominal_h25_p1p0','extreme_h10_p1p0','c28_h10_p1p0','c28_h25_p1p0')])"
  # B3 ratings (DECISIONS 46): body-model margins to the laminate MOT and part limits, ~9 min (b3_ratings_gate.BASIS:
  # release case c18_h10 at bay 61 C, ratchet cases c22_h10 / c28_h10 at bay 55 C, all at I_line 13.5 A; six solves,
  # at most 4 workers). Its FAIL is a release verdict the scorecard reads, not a chain failure; a margins.json not solved
  # on this board is.
  # run_basis.py exits with the gate's status (1 on a FAIL verdict); under set -e that ended the block on every board
  # that fails the release gate (all of them today), so its status is not used: the board check below catches a crash
  if want b3_ratings; then
  ( cd ../b3-ratings && python3 run_basis.py --workers 4 > "$B/b3-ratings.log" 2>&1 ) || true; tail -1 "$B/b3-ratings.log"
  python3 -c "import json,sys;m=json.load(open('../b3-ratings/margins.json'));sys.exit(set(m['board_sha256'].values())!={'$H'})" \
    || { echo "B3_RATINGS: margins.json not solved on board $H"; tail -5 "$B/b3-ratings.log"; exit 1; }
  else echo "scoped: B3 ratings reused from the benchmark (key in $SCOPED_PLAN)"; fi
) > "$B/blk-thermal.log" 2>&1 &
P_TH=$!
( cd validation-results/02-protection-timing/kelvin && python3 kelvin_plane.py ../../../native-21/verification/$TAG-all-copper.json.gz $TAG | tail -1 && python3 kelvin_budget.py $TAG | tail -1
) > "$B/blk-kelvin.log" 2>&1 &
P_KV=$!
( python3 validation-results/08-manufacturing-package/native-21/stage18-res-a-creepage/res_a_creepage18.py "$B/copper-dump.json" --json "$B/res-a-creepage.json" | tail -1
  S19=validation-results/08-manufacturing-package/native-21/stage19-pi-si
  $KP $S19/pi_distances19.py "$BP" --json "$B/pi-distances.json" 2>/dev/null | grep -v -i "wxapp\|Debug" | tail -1
  python3 $G/return_path19.py "$B/copper-dump.json" --json "$B/return-path.json" | tail -1
  # SELV-spine lock (13-coupling WS4 <-> WS5; gates/README.md): SPINE_OWNER=selv only for the SELV-side lane
  python3 -I $G/spine_lock.py native-21/verification/$TAG-all-copper.json.gz ${SPINE_OWNER:+--owner "$SPINE_OWNER"} > "$B/spine-lock.json" \
    && echo "SPINE_LOCK PASS (owner ${SPINE_OWNER:-none})" || { echo "SPINE_LOCK FAIL: $(cut -c1-300 "$B/spine-lock.json")"; exit 1; }
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
# content keys of this build (board, copper, per-net, thermal steps), so a later scoped run can prove what it reuses
python3 -I $G/scoped/scoped_chain.py manifest "$B" "$TAG" || echo "scoped manifest not written (non-fatal)"
echo CHAIN_DONE
