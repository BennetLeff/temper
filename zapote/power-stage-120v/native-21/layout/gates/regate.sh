#!/bin/sh
# Re-run every downstream gate on a built board: $1 = build dir (section.kicad_pcb, copper-dump.json).
#   sh regate.sh BUILDDIR [all|core|task04]      (default all = core then task04)
# core:   copper dump -> Rust barrier gate, JLC DFM, local-bypass gate, all-copper extract, power-copper export
# task04: the A4 DC current-flow cases on the power copper (needs core's power_copper.json.gz). Cached: skipped when the
#         board's copper inputs (copper_key.py: tracks, vias, pads, zone outlines and rules, not the refill, which KiCad
#         does not reproduce bit for bit), the case list and the solver scripts are unchanged since the last run; the hit
#         is recorded in outputs/cache.json (computed-on vs reused-for board) - stage 22, chain speed-up. Stage 33: the key
#         is copper_key.py + model_key.py (every task-04 and B3 model input, shared with chain.sh's B3 key).
set -e
# a step piped through tail must still fail the gate (summarize.py exits 1 on any A4 failure; the pipe hid it)
set -o pipefail
BD=$(cd "$1" && pwd)
U=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$U"
B=$BD/section.kicad_pcb
MODE=${2:-all}
. "$U/native-21/layout/gates/laps.sh"; laps_init "regate/$MODE" "$BD/steps.jsonl"
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
MP=${MP:-/Users/bennet/Miniforge3/bin/python3}
R=validation-results/04-board-current-thermal/round5-native21
if [ "$MODE" = all ] || [ "$MODE" = core ]; then
  $KP tools/copper_dump.py $B $1/evidence.json >/dev/null 2>&1
  lap copper_dump
  # the release barrier binary of this checkout's sources (barrier_bin.sh: ~9x faster than debug, identical report)
  BAR_BIN=${ZAPOTE_POWER_BARRIER_BIN:-$(sh "$U/native-21/layout/gates/barrier_bin.sh")}
  lap barrier_bin
  ZAPOTE_POWER_BARRIER_BIN=$BAR_BIN python3 native-21/layout/barrier_gate21.py $1/evidence.json > $1/barrier-gate-rust.json &
  P_BAR=$!
  $KP tools/jlc_dfm_check.py $B > $1/jlc-dfm.json 2>/dev/null
  lap jlc_dfm
  # local bypass: every comparator / Schmitt buffer / rail monitor has its 100 nF within the stage-19 limits (fails the gate)
  $KP native-21/layout/gates/bypass_check.py $B $1/bypass-check.json > $1/bypass-check.txt 2>&1 || { grep -v -i "wxapp\|Debug\|assert" $1/bypass-check.txt >&2; echo "BYPASS GATE FAILED" >&2; exit 1; }
  lap bypass_check
  $KP validation-results/04-board-current-thermal/round4/reextract-b3/extract_geometry.py $B $1/native21-all-copper.json.gz >/dev/null 2>&1
  lap extract_geometry
  # exported beside the build; task04 copies it into the study only when it recomputes, so inputs/ always matches outputs/
  $KP tools/export_power_copper.py $B "$BD/power_copper.json.gz" >/dev/null 2>&1
  lap export_power_copper
  wait $P_BAR
  lap barrier_gate_wait
fi
if [ "$MODE" = all ] || [ "$MODE" = task04 ]; then
  CK=$($KP native-21/layout/gates/copper_key.py "$B" 2>/dev/null | tail -1)
  case "$CK" in [0-9a-f]*) ;; *) echo "copper_key failed" >&2; exit 1;; esac
  # stage 33 (DECISIONS 38, chain cache trap): the model half of the key is model_key.py, shared with chain.sh's B3
  # cache - every task-04 and B3 script, B3's heat inputs, the resolved stackup file(s) and SHEET_BARREL - so a change
  # to any model input misses both caches (it used to hash only the four task-04 scripts: a B3 script or stackup
  # change gave a task-04 hit and a B3 recompute, which then failed B3's same-board check)
  MK=$(python3 native-21/layout/gates/model_key.py | tail -1)
  case "$MK" in [0-9a-f]*) ;; *) echo "model_key failed" >&2; exit 1;; esac
  lap copper_and_model_key
  cd $R
  KEY=$(python3 -c "import hashlib,sys;print(hashlib.sha256(('task04|'+sys.argv[1]+'|'+sys.argv[2]).encode()).hexdigest())" "$CK" "$MK")
  BOARD=$(shasum -a 256 "$B" | cut -d' ' -f1)
  # the nodal heat files (*.npz) are gitignored: a hit also needs the local ones to be those the results were computed with
  NPZ=$(python3 -c "import glob,hashlib;h=hashlib.sha256();[h.update(open(f,'rb').read()) for f in sorted(glob.glob('outputs/*.npz'))];print(h.hexdigest())")
  lap npz_hash
  # TASK04_FORCE=1 recomputes regardless (chain.sh uses it if B3 misses after a task-04 hit; see there)
  if [ -z "${TASK04_FORCE:-}" ] && [ -f outputs/cache.json ] && [ -f outputs/summary.json ] && grep -q "\"key\": \"$KEY\"" outputs/cache.json \
     && grep -q "\"npz_sha256\": \"$NPZ\"" outputs/cache.json; then
    python3 - "$BOARD" <<'PY'
import json, sys
p = "outputs/cache.json"; c = json.load(open(p)); c.setdefault("reused_for_boards", []).append(sys.argv[1]); json.dump(c, open(p, "w"), indent=1)
PY
    # the reused results stay paired with the export they were computed on (same copper inputs, another refill)
    python3 - <<'PY'
import gzip, json
c = json.load(open("outputs/cache.json")); e = json.load(gzip.open("inputs/power_copper.json.gz"))
assert e["board_sha256"] == c["computed_on_board"], ("inputs/power_copper.json.gz is not the computed-on export", e["board_sha256"][:12], c["computed_on_board"][:12])
print("task04 cache hit (copper inputs unchanged): computed on", c["computed_on_board"][:12])
PY
    lap task04_cache_hit
  else
    rm -f outputs/*-pl*.json outputs/*.npz outputs/summary.json outputs/cache.json
    cp "$BD/power_copper.json.gz" inputs/power_copper.json.gz
    $MP ../round3/scripts/kit_topology_native13.py inputs/power_copper.json.gz outputs/kit_topology_p0125.json 0.125 >/dev/null &
    $MP ../round3/scripts/kit_topology_native13.py inputs/power_copper.json.gz outputs/kit_topology_p00625.json 0.0625 >/dev/null &
    # TASK04_WORKERS caps the case runner's processes (default 6, as before); a shared machine sets it lower
    WORKERS=${TASK04_WORKERS:-6} $MP run_cases.py > outputs/run_cases.log 2>&1
    lap run_cases
    $MP run_board.py --net bus_p --source BR1.1:15 --sink Q2.2 --pitch 0.25 --plating 18 --name bus-dc-q2-p025-pl18 >/dev/null
    lap run_board_p025
    $MP run_board.py --net bus_p --source BR1.1:15 --sink Q2.2 --pitch 0.0625 --plating 18 --name bus-dc-q2-p00625-pl18 >/dev/null
    lap run_board_p00625
    wait
    NPZ=$(python3 -c "import glob,hashlib;h=hashlib.sha256();[h.update(open(f,'rb').read()) for f in sorted(glob.glob('outputs/*.npz'))];print(h.hexdigest())")
    printf '{"key": "%s", "copper_key": "%s", "model_key": "%s", "npz_sha256": "%s", "computed_on_board": "%s", "reused_for_boards": []}\n' "$KEY" "$CK" "$MK" "$NPZ" "$BOARD" > outputs/cache.json
    lap kit_topology_wait_and_cache_write
  fi
  $MP summarize.py | tail -1
  lap summarize
  python3 compare_native17.py > outputs/compare_native17.txt
  lap compare_native17
fi
