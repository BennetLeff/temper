#!/usr/bin/env bash
# Reproduce the controller block-validator evidence (DECISIONS C30).
#
#   zapote/controller/evidence/block-validators/run.sh [BIN_DIR]
#
# BIN_DIR holds the built zapote-interlock, zapote-thermal and zapote-rtd
# (default: <repo>/.target-validators/release, from
#   cd zapote && CARGO_TARGET_DIR=$PWD/../.target-validators cargo build --release -p zapote-harness).
# Needs KiCad 10.0.4's bundled Python for pcbnew (KICAD_PY) and python3.
# Validators exit 1 on FAIL *or* INDETERMINATE; exit codes are recorded, not
# treated as script errors.  Large intermediates (filtered boards, native
# exports, unit inputs) go to $WORK and are not committed; their sha256 are in
# intermediates.sha256.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
Z="$REPO/zapote"
BIN="${1:-$REPO/.target-validators/release}"
KICAD_PY="${KICAD_PY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
WORK="${WORK:-$(mktemp -d)}"
OUT="${OUT:-$HERE}"
BOARD="$Z/controller/pcb/controller.kicad_pcb"
RES="$OUT/results"; MAPS="$OUT/mappings"
mkdir -p "$RES" "$MAPS" "$WORK/repo/harness-lab" "$WORK/repo/zapote/rtd"
rm -f "${RES:?}"/* "${MAPS:?}"/* "${OUT:?}/intermediates.sha256"

# The exporters import <repo>/harness-lab/assembly_geometry.py, which was removed
# from the tree (d70fd1857); the committed vendor copy is that file at d70fd1857^.
cp "$HERE/vendor/harness-lab/assembly_geometry.py" "$WORK/repo/harness-lab/"
# rtd/native_measure.py locates it relative to its own path: byte-identical copy.
cp "$Z/rtd/native_measure.py" "$WORK/repo/zapote/rtd/native_measure.py"

( cd "$BIN" && shasum -a 256 zapote-interlock zapote-thermal zapote-rtd ) > "$OUT/binaries.sha256"
shasum -a 256 "$Z/current-sense/tools/extract_current_sense_native.py" "$Z/rtd/native_measure.py" \
  "$Z/rtd/unit/bind_native.py" "$HERE/filter_block.py" "$HERE/bind_controller_rtd.py" \
  "$HERE/profile-controller.json" "$HERE/controller_pins.h" "$HERE/vendor/harness-lab/assembly_geometry.py" \
  "$BOARD" > "$OUT/inputs.sha256"

record() { # name, then command...: stdout -> results/name.json, exit -> results/name.exit
  local name="$1"; shift
  "$@" > "$RES/$name.json" 2> "$RES/$name.stderr"; echo $? > "$RES/$name.exit"
  [ -s "$RES/$name.stderr" ] || rm -f "${RES:?}/$name.stderr"
}
export_native() { # board out.json
  "$KICAD_PY" "$Z/current-sense/tools/extract_current_sense_native.py" --repo "$HERE/vendor" \
    --board "$1" --output "$2" 2>&1 | grep -v 'assert\|swig' >/dev/null
}
rtd_native() { "$KICAD_PY" "$WORK/repo/zapote/rtd/native_measure.py" "$1" "$2" 2>&1 | grep -v 'assert\|swig' >/dev/null; }
rtd_bind() { # native board profile out [extra bind args...]
  local native="$1" board="$2" profile="$3" out="$4"; shift 4
  python3 "$HERE/bind_controller_rtd.py" --profile "$profile" --native "$native" --board-file "$board" \
    --source-manifest "$Z/rtd/unit/candidate/source-manifest.json" --extractor "$Z/rtd/native_measure.py" \
    --model "$Z/rtd/model-correctness/qualified-input/model.json" --firmware "$REPO/firmware/config.h" \
    --qualified-input "$Z/rtd/model-correctness/qualified-input/input.json" --binary "$BIN/zapote-rtd" \
    --output "$out" "$@"
}
run_il() { record "$1" "$BIN/zapote-interlock" "$Z/interlock/candidate/source-manifest.json" "$2" "$Z/interlock/interface-contract.json"; }
run_th() { record "$1" "$BIN/zapote-thermal" "$Z/thermal-sense/candidate/source-manifest.json" "$2" "$Z/thermal-sense/sensor-contract.json"; }
run_rtd() { record "$1" "$BIN/zapote-rtd" --unit-input "$2"; }
filter() { # block manifest-dir tag [extra filter args...]
  local block="$1" cand="$2" tag="$3"; shift 3
  python3 "$HERE/filter_block.py" --board "$BOARD" --block "$block" --source-manifest "$cand/source-manifest.json" \
    --out-board "$WORK/$tag.kicad_pcb" --mapping-report "$MAPS/$tag.json" "$@" >/dev/null
}

echo "== controls: each validator on its committed standalone unit input"
run_il control-standalone-interlock "$Z/interlock/evidence/native-final.json"
run_th control-standalone-thermal   "$Z/thermal-sense/evidence/native-final.json"
run_rtd control-standalone-rtd      "$Z/rtd/model-correctness/qualified-input/input.json"

echo "== controls: same exporters/binder re-run on the unit's own board (pipeline control)"
export_native "$Z/interlock/candidate/section.kicad_pcb" "$WORK/unit-interlock-native.json"
run_il control-pipeline-interlock "$WORK/unit-interlock-native.json"
export_native "$Z/thermal-sense/candidate/section.kicad_pcb" "$WORK/unit-thermal-native.json"
run_th control-pipeline-thermal "$WORK/unit-thermal-native.json"
rtd_native "$Z/rtd/unit/candidate/section.kicad_pcb" "$WORK/unit-rtd-native.json"
rtd_bind "$WORK/unit-rtd-native.json" "$Z/rtd/unit/candidate/section.kicad_pcb" "$Z/rtd/unit/profile.json" \
  "$WORK/unit-rtd-input.json" --firmware-pins "$REPO/firmware/components/hal/include/temper_pins.h"
run_rtd control-pipeline-rtd "$WORK/unit-rtd-input.json"

echo "== controller runs"
filter interlock "$Z/interlock/candidate" interlock
export_native "$WORK/interlock.kicad_pcb" "$WORK/interlock-native.json"
run_il controller-interlock "$WORK/interlock-native.json"
filter thermal "$Z/thermal-sense/candidate" thermal
export_native "$WORK/thermal.kicad_pcb" "$WORK/thermal-native.json"
run_th controller-thermal "$WORK/thermal-native.json"
filter rtd_pan "$Z/rtd/unit/candidate" rtd_pan
rtd_native "$WORK/rtd_pan.kicad_pcb" "$WORK/rtd_pan-native.json"
rtd_bind "$WORK/rtd_pan-native.json" "$WORK/rtd_pan.kicad_pcb" "$HERE/profile-controller.json" "$WORK/rtd_pan-input.json" \
  --firmware-pins "$HERE/controller_pins.h" --absent-instance unit_io
run_rtd controller-rtd "$WORK/rtd_pan-input.json"

echo "== negative controls on the filtered controller exports"
filter interlock "$Z/interlock/candidate" neg-interlock-drop-bypass --drop-footprint aggregate_bypass
export_native "$WORK/neg-interlock-drop-bypass.kicad_pcb" "$WORK/neg-il1.json"
run_il negative-interlock-drop-aggregate_bypass "$WORK/neg-il1.json"
filter interlock "$Z/interlock/candidate" neg-interlock-swap-net --swap-pad-net fault_inv_bypass:1:gnd
export_native "$WORK/neg-interlock-swap-net.kicad_pcb" "$WORK/neg-il2.json"
run_il negative-interlock-swap-fault_inv_bypass-pad1-to-gnd "$WORK/neg-il2.json"
filter thermal "$Z/thermal-sense/candidate" neg-thermal-drop-bypass --drop-footprint hs_bypass
export_native "$WORK/neg-thermal-drop-bypass.kicad_pcb" "$WORK/neg-th1.json"
run_th negative-thermal-drop-hs_bypass "$WORK/neg-th1.json"
filter thermal "$Z/thermal-sense/candidate" neg-thermal-swap-net --swap-pad-net hs_bypass:1:COIL_REF
export_native "$WORK/neg-thermal-swap-net.kicad_pcb" "$WORK/neg-th2.json"
run_th negative-thermal-swap-hs_bypass-pad1-to-COIL_REF "$WORK/neg-th2.json"
# RTD: drop the ADC DVDD bypass.  With the capacitor declared absent to the binder the
# Rust validator must catch it; without the declaration the binder itself aborts on the
# census difference (both recorded).
filter rtd_pan "$Z/rtd/unit/candidate" neg-rtd-drop-bypass --drop-footprint rtd_pan.c_dvdd
rtd_native "$WORK/neg-rtd-drop-bypass.kicad_pcb" "$WORK/neg-rtd1-native.json"
rtd_bind "$WORK/neg-rtd1-native.json" "$WORK/neg-rtd-drop-bypass.kicad_pcb" "$HERE/profile-controller.json" "$WORK/neg-rtd1-input.json" \
  --firmware-pins "$HERE/controller_pins.h" --absent-instance unit_io --absent-instance rtd_pan.c_dvdd
run_rtd negative-rtd-drop-c_dvdd-declared-absent "$WORK/neg-rtd1-input.json"
rtd_bind "$WORK/neg-rtd1-native.json" "$WORK/neg-rtd-drop-bypass.kicad_pcb" "$HERE/profile-controller.json" "$WORK/neg-rtd1b-input.json" \
  --firmware-pins "$HERE/controller_pins.h" --absent-instance unit_io > "$RES/negative-rtd-drop-c_dvdd-binder-abort.txt" 2>&1
echo "binder exit: $?" >> "$RES/negative-rtd-drop-c_dvdd-binder-abort.txt"
filter rtd_pan "$Z/rtd/unit/candidate" neg-rtd-swap-net --swap-pad-net rtd_pan.c_dvdd:1:gnd
rtd_native "$WORK/neg-rtd-swap-net.kicad_pcb" "$WORK/neg-rtd2-native.json"
rtd_bind "$WORK/neg-rtd2-native.json" "$WORK/neg-rtd-swap-net.kicad_pcb" "$HERE/profile-controller.json" "$WORK/neg-rtd2-input.json" \
  --firmware-pins "$HERE/controller_pins.h" --absent-instance unit_io > "$RES/negative-rtd-swap-c_dvdd-pad1-to-gnd-binder-abort.txt" 2>&1
echo "binder exit: $?" >> "$RES/negative-rtd-swap-c_dvdd-pad1-to-gnd-binder-abort.txt"

( cd "$WORK" && shasum -a 256 *.kicad_pcb *native*.json *input*.json 2>/dev/null ) > "$OUT/intermediates.sha256"
python3 "$HERE/summarize.py" "$OUT"
echo "work dir (intermediates, not committed): $WORK"
