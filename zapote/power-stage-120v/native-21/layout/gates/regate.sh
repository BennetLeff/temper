#!/bin/sh
# Re-run every downstream gate on a built board: $1 = build dir (section.kicad_pcb, copper-dump.json).
#   sh regate.sh BUILDDIR [all|core|task04]      (default all = core then task04)
# core:   copper dump -> Rust barrier gate, JLC DFM, local-bypass gate, all-copper extract, power-copper export
# task04: the A4 DC current-flow cases on the power copper (needs core's power_copper.json.gz). Cached: skipped when the
#         power copper (board hash removed), the case list and the solver scripts are unchanged since the last run; the hit
#         is recorded in outputs/cache.json (computed-on vs reused-for board) - stage 22, chain speed-up.
set -e
U=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$U"
B=$1/section.kicad_pcb
MODE=${2:-all}
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
MP=${MP:-/Users/bennet/Miniforge3/bin/python3}
R=validation-results/04-board-current-thermal/round5-native21
if [ "$MODE" = all ] || [ "$MODE" = core ]; then
  $KP tools/copper_dump.py $B $1/evidence.json >/dev/null 2>&1
  ZAPOTE_POWER_BARRIER_BIN=${ZAPOTE_POWER_BARRIER_BIN:-/Users/bennet/Desktop/temper/target-shared/debug/zapote-power-barrier} python3 native-21/layout/barrier_gate21.py $1/evidence.json > $1/barrier-gate-rust.json &
  P_BAR=$!
  $KP tools/jlc_dfm_check.py $B > $1/jlc-dfm.json 2>/dev/null
  # local bypass: every comparator / Schmitt buffer / rail monitor has its 100 nF within the stage-19 limits (fails the gate)
  $KP native-21/layout/gates/bypass_check.py $B $1/bypass-check.json > $1/bypass-check.txt 2>&1 || { grep -v -i "wxapp\|Debug\|assert" $1/bypass-check.txt >&2; echo "BYPASS GATE FAILED" >&2; exit 1; }
  $KP validation-results/04-board-current-thermal/round4/reextract-b3/extract_geometry.py $B $1/native21-all-copper.json.gz >/dev/null 2>&1
  $KP tools/export_power_copper.py $B $R/inputs/power_copper.json.gz >/dev/null 2>&1
  wait $P_BAR
fi
if [ "$MODE" = all ] || [ "$MODE" = task04 ]; then
  cd $R
  KEY=$(python3 - <<'PY'
import gzip, hashlib, json
d = json.load(gzip.open("inputs/power_copper.json.gz"))
for k in ("board_sha256", "board", "source_sha256"):
    d.pop(k, None)
h = hashlib.sha256(json.dumps(d, sort_keys=True).encode())
for f in ("run_cases.py", "run_board.py", "summarize.py", "../round3/scripts/kit_topology_native13.py"):
    h.update(open(f, "rb").read())
print(h.hexdigest())
PY
)
  BOARD=$(shasum -a 256 "$B" | cut -d' ' -f1)
  if [ -f outputs/cache.json ] && [ -f outputs/summary.json ] && grep -q "\"key\": \"$KEY\"" outputs/cache.json; then
    python3 - "$BOARD" <<'PY'
import json, sys
p = "outputs/cache.json"; c = json.load(open(p)); c.setdefault("reused_for_boards", []).append(sys.argv[1]); json.dump(c, open(p, "w"), indent=1)
PY
    echo "task04 cache hit (power copper unchanged): $(python3 -c "import json;print(json.load(open('outputs/cache.json'))['computed_on_board'][:12])")"
  else
    rm -f outputs/*-pl*.json outputs/*.npz outputs/summary.json outputs/cache.json
    $MP ../round3/scripts/kit_topology_native13.py inputs/power_copper.json.gz outputs/kit_topology_p0125.json 0.125 >/dev/null &
    $MP ../round3/scripts/kit_topology_native13.py inputs/power_copper.json.gz outputs/kit_topology_p00625.json 0.0625 >/dev/null &
    WORKERS=6 $MP run_cases.py > outputs/run_cases.log 2>&1
    $MP run_board.py --net bus_p --source BR1.1:15 --sink Q2.2 --pitch 0.25 --plating 18 --name bus-dc-q2-p025-pl18 >/dev/null
    $MP run_board.py --net bus_p --source BR1.1:15 --sink Q2.2 --pitch 0.0625 --plating 18 --name bus-dc-q2-p00625-pl18 >/dev/null
    wait
    printf '{"key": "%s", "computed_on_board": "%s", "reused_for_boards": []}\n' "$KEY" "$BOARD" > outputs/cache.json
  fi
  $MP summarize.py | tail -1
  python3 compare_native17.py > outputs/compare_native17.txt
fi
