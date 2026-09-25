#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NGSPICE=${NGSPICE:-/opt/homebrew/bin/ngspice}
RUSTC=${RUSTC:-rustc}
mkdir -p "$ROOT/raw" "$ROOT/traces"
[ -x "$NGSPICE" ] || { echo "ngspice executable not found: $NGSPICE" >&2; exit 2; }

make_case() {
  name=$1; vd_fault=$2; vb_fault=$3; vd_recover=$4; vb_recover=$5
  logic_ramp=$6; aux_ramp=$7; logic_drop=$8; logic_low=$9; logic_return=${10}; logic_return_end=${11}
  aux_drop=${12}; aux_low=${13}; aux_return=${14}; aux_return_end=${15}
  bypass=${16}; stop=${17}; step=${18}
  arm_drop=${19}; arm_fall=${20}; arm2=${21}; arm2_rise=${22}; arm2_end=${23}; arm2_fall=${24}
  fault_tau=${25}; en_tau=${26}
  cir="$ROOT/raw/${name}.cir"; trace="$ROOT/traces/${name}.tsv"; raw="$ROOT/raw/${name}.raw"
  sed \
    -e "s|@VD_FAULT@|$vd_fault|g" -e "s|@VB_FAULT@|$vb_fault|g" \
    -e "s|@VD_RECOVER@|$vd_recover|g" -e "s|@VB_RECOVER@|$vb_recover|g" \
    -e "s|@LOGIC_RAMP_T@|$logic_ramp|g" -e "s|@AUX_RAMP_T@|$aux_ramp|g" \
    -e "s|@LOGIC_DROP_T@|$logic_drop|g" -e "s|@LOGIC_LOW_T@|$logic_low|g" \
    -e "s|@LOGIC_RETURN_T@|$logic_return|g" -e "s|@LOGIC_RETURN_END@|$logic_return_end|g" \
    -e "s|@AUX_DROP_T@|$aux_drop|g" -e "s|@AUX_LOW_T@|$aux_low|g" \
    -e "s|@AUX_RETURN_T@|$aux_return|g" -e "s|@AUX_RETURN_END@|$aux_return_end|g" \
    -e "s|@BYPASS@|$bypass|g" \
    -e "s|@TSTOP@|$stop|g" -e "s|@TSTEP@|$step|g" \
    -e "s|@ARM_DROP_T@|$arm_drop|g" -e "s|@ARM_FALL_T@|$arm_fall|g" \
    -e "s|@ARM2_T@|$arm2|g" -e "s|@ARM2_RISE_T@|$arm2_rise|g" \
    -e "s|@ARM2_END_T@|$arm2_end|g" -e "s|@ARM2_FALL_T@|$arm2_fall|g" \
    -e "s|@FAULT_TAU@|$fault_tau|g" -e "s|@EN_TAU@|$en_tau|g" \
    -e "s|@CONTROLLER@|$ROOT/controller.inc|g" \
    -e "s|@TRACE@|$trace|g" -e "s|@RAW@|$raw|g" \
    "$ROOT/fault_template.cir" > "$cir"
  if [ "$name" = logic_absent ]; then sed -i '' 's/^Vlogic5 .*/Vlogic5 logic5 0 0/' "$cir"; fi
  if [ "$name" = aux_absent ]; then sed -i '' 's/^Vaux15 .*/Vaux15 aux15 0 0/' "$cir"; fi
  "$NGSPICE" -b "$cir" > "$ROOT/raw/${name}.log" 2>&1
}

# Supply startup completes before ARM200us. Fault220us; recovery300.1us;
# ARM remains held until550us, with a fresh rising edge560us.
common='20u 20u 700u 701u 702u 703u 700u 701u 702u 703u 0 650u 10n 550u 551u 560u 560.1u 561u 561.1u 79.3n 18.75n'
make_case forward_mismatch 425 410 410 410 $common
make_case reverse_mismatch 410 425 410 410 $common
make_case absolute_vd 435 426 410 410 $common
make_case absolute_vb 426 435 410 410 $common
make_case logic_first 410 410 410 410 20u 40u 700u 701u 702u 703u 700u 701u 702u 703u 0 650u 10n 550u 551u 560u 560.1u 561u 561.1u 79.3n 18.75n
make_case aux_first 410 410 410 410 40u 20u 700u 701u 702u 703u 700u 701u 702u 703u 0 650u 10n 550u 551u 560u 560.1u 561u 561.1u 79.3n 18.75n
make_case logic_absent 410 410 410 410 $common
make_case aux_absent 410 410 410 410 $common
make_case slow_ramps 410 410 410 410 60u 60u 700u 701u 702u 703u 700u 701u 702u 703u 0 650u 10n 550u 551u 560u 560.1u 561u 561.1u 79.3n 18.75n
make_case logic_dropout_return 410 410 410 410 20u 20u 240u 240.1u 300u 300.1u 700u 701u 702u 703u 0 650u 10n 550u 551u 560u 560.1u 561u 561.1u 79.3n 18.75n
make_case aux_dropout_return 410 410 410 410 20u 20u 700u 701u 702u 703u 240u 240.1u 300u 300.1u 0 650u 10n 550u 551u 560u 560.1u 561u 561.1u 79.3n 18.75n
make_case aux_fast_dip 410 410 410 410 20u 20u 700u 701u 702u 703u 240u 240.001u 241u 241.001u 0 650u 10n 550u 551u 560u 560.1u 561u 561.1u 79.3n 18.75n
make_case bypass_negative 425 410 410 410 20u 20u 700u 701u 702u 703u 700u 701u 702u 703u 1 650u 10n 550u 551u 560u 560.1u 561u 561.1u 79.3n 18.75n
make_case slow_detector_negative 425 410 410 410 20u 20u 700u 701u 702u 703u 700u 701u 702u 703u 0 650u 10n 550u 551u 560u 560.1u 561u 561.1u 10u 18.75n
sed -e 's/aux_first/startup_held_arm/g' -e 's/^Varm .*/Varm arm 0 5/' -e 's/^Vpwm .*/Vpwm pwm 0 5/' "$ROOT/raw/aux_first.cir" > "$ROOT/raw/startup_held_arm.cir"
"$NGSPICE" -b "$ROOT/raw/startup_held_arm.cir" > "$ROOT/raw/startup_held_arm.log" 2>&1
"$RUSTC" --edition=2021 -O "$ROOT/extract.rs" -o "$ROOT/f2b-fault-extract"
"$ROOT/f2b-fault-extract" "$ROOT" > "$ROOT/traces/summary.csv"
echo "Wrote revision-B fault fixtures and results."
