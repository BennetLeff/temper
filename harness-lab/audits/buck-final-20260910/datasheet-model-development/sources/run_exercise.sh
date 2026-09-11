#!/bin/sh
set -eu

# Short native ngspice exercise. This is deliberately separate from the
# adopted harness: it creates no qualification manifest and applies no limits.
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
MODEL="$ROOT/../../models/lmr51430-datasheet/model.lib"
OUT=${1:-/tmp/temper-lmr-datasheet-exercise}
NGSPICE=${NGSPICE:-/opt/homebrew/bin/ngspice}

if [ ! -f "$MODEL" ]; then
  printf '%s\n' "missing model package: $MODEL" >&2
  exit 2
fi
if [ ! -x "$NGSPICE" ]; then
  printf '%s\n' "missing ngspice executable: $NGSPICE" >&2
  exit 2
fi
if [ -e "$OUT" ]; then
  printf '%s\n' "output already exists; choose a new path: $OUT" >&2
  exit 2
fi
mkdir -p "$OUT"
OUT=$(CDPATH='' cd -- "$OUT" && pwd)
cp "$MODEL" "$OUT/model.lib"
mkdir "$OUT/sources"
cp "$ROOT/../../models/lmr51430-datasheet/parameter-provenance.json" "$OUT/parameter-provenance.json"

TEMPLATE="$ROOT/template.cir"
LOAD_TEMPLATE="$ROOT/load_step.cir"
cp "$TEMPLATE" "$OUT/sources/template.cir"
cp "$LOAD_TEMPLATE" "$OUT/sources/load_step.cir"
cp "$ROOT/run_exercise.sh" "$OUT/sources/run_exercise.sh"
shasum -a 256 "$OUT/sources/template.cir" "$OUT/sources/load_step.cir" "$OUT/sources/run_exercise.sh" > "$OUT/sources/sha256.txt"
MODEL_SHA=$(shasum -a 256 "$OUT/model.lib" | awk '{print $1}')
PARAM_SHA=$(shasum -a 256 "$OUT/parameter-provenance.json" | awk '{print $1}')
"$NGSPICE" --version > "$OUT/ngspice-version.txt" 2>&1
VERSION_SHA=$(shasum -a 256 "$OUT/ngspice-version.txt" | awk '{print $1}')
commit=$(git -C "$ROOT/../../.." rev-parse HEAD 2>/dev/null || printf UNKNOWN)

run_case() {
  name=$1
  source=$2
  params=$3
  dir="$OUT/$name"
  mkdir "$dir"
  # The copied model sits beside each case deck, matching the package-relative
  # include retained in the checked-in templates.
  sed -e 's|^\.include .*|.include ../model.lib|' \
      -e "s|^\.param .*|.param $params|" "$source" > "$dir/bench.cir"
  (cd "$dir" && "$NGSPICE" -n -b bench.cir > simulator.log 2>&1)
  test -s "$dir/waveform.raw" || { printf '%s\n' "missing waveform.raw in $dir" >&2; exit 1; }
  metrics='vout_end vout_avg vout_min vout_max il_avg pin_energy pout_energy'
  case "$name" in
    load-step-*) metrics='vout_pre vout_high vout_post iload_pre iload_high iload_post vout_min vout_max pin_energy pout_energy' ;;
  esac
  for metric in $metrics; do
    grep -Eiq "^[[:space:]]*${metric}[[:space:]]*=[[:space:]]*[-+]?(([0-9]+(\.[0-9]*)?)|(\.[0-9]+))([eE][-+]?[0-9]+)?([[:space:]]|$)" "$dir/simulator.log" || {
      printf '%s\n' "native measurement $metric missing in $dir" >&2; exit 1;
    }
  done
  grep -Eqi 'error|singular matrix|unknown parameter|measure.*failed|aborted|nan|inf' "$dir/simulator.log" && {
    printf '%s\n' "ngspice reported an error in $dir" >&2; exit 1;
  } || true
  shasum -a 256 "$dir/bench.cir" "$dir/simulator.log" "$dir/waveform.raw" \
    > "$dir/sha256.txt"
  printf '%s\t%s\n' "$name" "$dir"
}

printf '{\n  "kind": "lmr51430-datasheet-exercise/v1",\n  "development_only": true,\n  "hardware_validated": false,\n  "qualified": false,\n  "simulator_version_file": "ngspice-version.txt",\n  "simulator_version_sha256": "%s",\n  "model": "model.lib",\n  "model_sha256": "%s",\n  "parameter_provenance": "parameter-provenance.json",\n  "parameter_provenance_sha256": "%s",\n  "git_commit": "%s",\n  "cases": [\n' "$VERSION_SHA" "$MODEL_SHA" "$PARAM_SHA" "$commit" > "$OUT/manifest.json"

first=1
case_entry() {
  [ "$first" -eq 1 ] || printf ',\n' >> "$OUT/manifest.json"
  first=0
  printf '    {"name":"%s","deck_sha256":"%s","log_sha256":"%s","raw_sha256":"%s"}' \
    "$1" "$(awk 'NR==1{print $1}' "$OUT/$1/sha256.txt")" \
    "$(awk 'NR==2{print $1}' "$OUT/$1/sha256.txt")" \
    "$(awk 'NR==3{print $1}' "$OUT/$1/sha256.txt")" >> "$OUT/manifest.json"
}

# A repeatable bounded check for ordinary development. The default still
# emits the complete requested matrix; QUICK=1 avoids re-running every corner
# when only the model/package wiring needs to be checked.
if [ "${LMR_QUICK:-0}" = 1 ]; then
  run_case nominal-steady "$TEMPLATE" "VINSET=15 CIN=10u COUT=44u LVAL=5.6u RLOAD=6.6" >/dev/null
  case_entry nominal-steady
  run_case load-step-0p05-to-0p5 "$LOAD_TEMPLATE" "VINSET=15 CIN=10u COUT=44u LVAL=5.6u ILOW=.05 IHIGH=.5" >/dev/null
  case_entry load-step-0p05-to-0p5
  run_case sensitivity-L-4.48u "$TEMPLATE" "VINSET=15 CIN=4.54u COUT=22.01u LVAL=4.48u RLOAD=6.6" >/dev/null
  case_entry sensitivity-L-4.48u
  printf '\n  ]\n}\n' >> "$OUT/manifest.json"
  printf '%s\n' "completed bounded native ngspice exercise: $OUT"
  exit 0
fi

for vin in 13.5 15 16.5; do
  run_case "startup-${vin}V-0A" "$TEMPLATE" "VINSET=${vin} CIN=10u COUT=44u LVAL=5.6u RLOAD=1e12" >/dev/null
  case_entry "startup-${vin}V-0A"
  run_case "startup-${vin}V-0p5A" "$TEMPLATE" "VINSET=${vin} CIN=10u COUT=44u LVAL=5.6u RLOAD=6.6" >/dev/null
  case_entry "startup-${vin}V-0p5A"
done

run_case load-step-0p05-to-0p5 "$LOAD_TEMPLATE" "VINSET=15 CIN=10u COUT=44u LVAL=5.6u ILOW=.05 IHIGH=.5" >/dev/null
case_entry load-step-0p05-to-0p5
run_case load-step-0p05-to-1 "$LOAD_TEMPLATE" "VINSET=15 CIN=10u COUT=44u LVAL=5.6u ILOW=.05 IHIGH=1" >/dev/null
case_entry load-step-0p05-to-1

for l in 4.48u 6.72u; do
  run_case "sensitivity-L-${l}" "$TEMPLATE" "VINSET=15 CIN=4.54u COUT=22.01u LVAL=${l} RLOAD=6.6" >/dev/null
  case_entry "sensitivity-L-${l}"
done
printf '\n  ]\n}\n' >> "$OUT/manifest.json"

printf '%s\n' "completed native ngspice exercise: $OUT"
