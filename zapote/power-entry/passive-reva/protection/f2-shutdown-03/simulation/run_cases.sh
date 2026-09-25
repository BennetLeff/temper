#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NGSPICE=${NGSPICE:-/opt/homebrew/bin/ngspice}
RUSTC=${RUSTC:-rustc}
mkdir -p "$ROOT/raw" "$ROOT/traces"

if [ ! -x "$NGSPICE" ]; then
  echo "ngspice executable not found: $NGSPICE" >&2
  exit 2
fi

make_case() {
  name=$1; l=$2; current=$3; open=$4; arm=$5; arm2=$6; permit_drop=$7; rail_drop=$8; gate_tau=$9; stop=${10}; vb=${11:-410}; vd=${12:-410}; duty=${13:-5.5u}; pwm_delay=${14:-3u}; close=${15:-219u}; permit_return=${16:-219.5u}; rail_return=${17:-219.5u}; en_tau=${18:-39n}; step=${19:-2n}; arm_hold=${20:-1.5u}
  arm2_time=$arm2
  [ "$arm2" = 0 ] && arm2_time=1u
  divinit=$(awk -v bus="$vd" 'BEGIN { printf "%.9f", bus*5820/(987000+200+5620) }')
  cir="$ROOT/raw/${name}.cir"
  trace="$ROOT/traces/${name}.tsv"
  raw="$ROOT/raw/${name}.raw"
  sed \
    -e "s|@LBOOST@|$l|g" \
    -e "s|@IINIT@|$current|g" \
    -e "s|@PW_ON@|$duty|g" \
    -e "s|@PWM_DELAY@|$pwm_delay|g" \
    -e "s|@VB_INIT@|$vb|g" \
    -e "s|@VD_INIT@|$vd|g" \
    -e "s|@DIV_INIT@|$divinit|g" \
    -e "s|@T_OPEN@|$open|g" \
    -e "s|@T_CLOSE@|$close|g" \
    -e "s|@T_ARM@|$arm|g" \
    -e "s|@ARM_HOLD@|$arm_hold|g" \
    -e "s|@T_ARM2@|$arm2_time|g" \
    -e "s|@ARM2@|$( [ "$arm2" = 0 ] && echo 0 || echo 1 )|g" \
    -e "s|@PERMIT_DROP@|$permit_drop|g" \
    -e "s|@PERMIT_RETURN@|$permit_return|g" \
    -e "s|@RAIL_DROP@|$rail_drop|g" \
    -e "s|@RAIL_RETURN@|$rail_return|g" \
    -e "s|@GATE_TAU@|$gate_tau|g" \
    -e "s|@EN_TAU@|$en_tau|g" \
    -e "s|@TSTOP@|$stop|g" \
    -e "s|@TSTEP@|$step|g" \
    -e "s|@TRACE@|$trace|g" \
    -e "s|@RAW@|$raw|g" \
    "$ROOT/f2_shutdown_template.cir" > "$cir"
  "$NGSPICE" -b "$cir" > "$ROOT/raw/${name}.log" 2>&1
}

# Nominal, F2-open current cases, and deliberate state/driver stress cases.
# t_open=120 us; run long enough to include inductor commutation and no-return.
make_case normal_arm 180u 40 300u 1u 0 400u 400u 120n 220u 410 410 5.5u 3u 500u 410u 410u 39n 2n 1.5u
make_case f2_open_40_adverse 100u 40 120u 1u 0 400u 400u 120n 220u 410 410 5.5u 3u 500u 410u 410u 39n 2n 1.5u
make_case f2_open_45_adverse 180u 45 120u 1u 0 400u 400u 120n 220u 410 410 5.5u 3u 500u 410u 410u 39n 2n 1.5u
make_case f2_open_50_adverse 216u 50 120u 1u 0 400u 400u 120n 220u 410 410 5.5u 3u 500u 410u 410u 39n 2n 1.5u
make_case f2_phase_1u 216u 50 120u 1u 0 400u 400u 120n 220u 410 410 5.5u 1u 500u 410u 410u 39n 2n 1.5u
make_case f2_phase_1u_refined 216u 50 120u 1u 0 400u 400u 120n 220u 410 410 5.5u 1u 500u 410u 410u 39n 1n 1.5u
make_case doubled_gate_charge 216u 50 120u 1u 0 400u 400u 240n 220u 410 410 5.5u 1u 500u 410u 410u 39n 2n 1.5u
make_case f2_phase_2u 216u 50 120u 1u 0 400u 400u 120n 220u 410 410 5.5u 2u 500u 410u 410u 39n 2n 1.5u
make_case f2_phase_4u 216u 50 120u 1u 0 400u 400u 120n 220u 410 410 5.5u 4u 500u 410u 410u 39n 2n 1.5u
make_case f2_phase_5u 216u 50 120u 1u 0 400u 400u 120n 220u 410 410 5.5u 5u 500u 410u 410u 39n 2n 1.5u
make_case f2_open_50_refined 216u 50 120u 1u 0 400u 400u 120n 220u 410 410 5.5u 3u 500u 410u 410u 39n 1n 1.5u
make_case reverse_mismatch 180u 40 120u 1u 0 400u 400u 120n 220u 425 410 5.5u 3u 500u 410u 410u 39n 2n 1.5u
make_case absolute_vd_ov 180u 40 120u 1u 0 400u 400u 120n 220u 425 430 5.5u 3u 500u 410u 410u 39n 2n 1.5u
make_case absolute_vb_ov 180u 40 120u 1u 0 400u 400u 120n 220u 430 425 5.5u 3u 500u 410u 410u 39n 2n 1.5u
make_case fault_clear_held_arm 180u 40 120u 1u 0 400u 400u 120n 240u 410 410 5.5u 3u 160u 410u 410u 39n 2n 200u
make_case fresh_rearm 180u 40 120u 1u 260u 400u 400u 120n 300u 410 410 5.5u 3u 160u 410u 410u 39n 2n 1.5u
make_case permit_loss_return 180u 40 300u 1u 0 80u 400u 120n 240u 410 410 5.5u 3u 500u 100u 410u 39n 2n 1.5u
make_case rails_invalid_return 180u 40 300u 1u 0 400u 80u 120n 240u 410 410 5.5u 3u 500u 410u 100u 39n 2n 1.5u
make_case slowed_gate_negative 180u 40 120u 1u 0 400u 400u 480n 260u 410 410 5.5u 3u 500u 410u 410u 5u 2n 1.5u

"$RUSTC" --edition=2021 -O "$ROOT/extract.rs" -o "$ROOT/raw/f2_extract"
"$ROOT/raw/f2_extract" "$ROOT" > "$ROOT/traces/summary.csv"
echo "Wrote traces and summary under $ROOT"
