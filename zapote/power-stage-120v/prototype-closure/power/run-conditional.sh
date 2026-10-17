#!/usr/bin/env bash
# Reuse the frozen runner and vendor model without writing into that checkout.
set -euo pipefail
src=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$src/../../../.." && pwd)
oracle=${1:?Usage: run-conditional.sh /absolute/path/to/ps-oracle [output-directory]}
out=${2:-"$repo/output/temper-prototype-closure/power"}
bash "$src/preflight.sh" "$oracle"
mkdir -p "$out"
out=$(cd "$out" && pwd)
power="$oracle/zapote/power-stage-120v"
runner="$power/validation-plan/sim-kit/common/run_ngspice.py"
matrix=()
while read -r directive parameter; do
  matrix+=("$parameter")
done < "$src/matrix-params.inc"

# Historical baseline proves the instrument; 348 ns is not the selected DT.
PYTHONDONTWRITEBYTECODE=1 python3 "$runner" "$src/leg_matrix_baseline.cir" \
  "${matrix[@]}" VBUS=170 IL=37 DIR=0 DT=348n TRMAX=0.2n LESL=1.06n \
  --keep "$out/baseline" > "$out/baseline-result.json"
jq -e '.aborted == false and (.failed|length) == 0 and
  .meas.vds_ls_die_pk == 203.6704 and .meas.vgs_ls_off_max == 2.234341' \
  "$out/baseline-result.json" > "$out/baseline-check.txt"

printf 'path,threshold_A,bus_V,esl_nH,command_delay_us,slope_A_per_us,first_1p9_s,imposed_A_at_first_1p9,VDS_LS_pk_V,VDS_HS_pk_V,VGS_HS_off_max_V,VGS_LS_late_max_V,VGS_LS_min_V\n' > "$out/conditional.csv"
for item in ct_low:50.558 ct_high:60.014 shunt_low:38.438184 shunt_high:85.551033; do
  label=${item%%:*}
  threshold=${item#*:}
  for bus in 170 198 280; do
    for esl in 1.06 10; do
      for delay in 0 1 5; do
        tag="${label}_v${bus}_esl${esl}_td${delay}"
        PYTHONDONTWRITEBYTECODE=1 python3 "$runner" "$src/conditional_turnoff.cir" \
          "${matrix[@]}" "VBUS=$bus" "ITRIP=$threshold" "LESL=${esl}n" \
          "TD=${delay}u" SLOPE=10e6 DT=443n TRMAX=0.2n \
          --keep "$out/$tag" > "$out/$tag.json"
        jq -e -f "$src/accept-conditional.jq" \
          "$out/$tag.json" > /dev/null
        jq -r --arg p "$label" --argjson i "$threshold" --argjson b "$bus" \
          --argjson e "$esl" --argjson d "$delay" \
          '[$p,$i,$b,$e,$d,10,.meas.gate_first_1p9,.meas.imposed_current_at_first_1p9,
          .meas.vds_ls_die_pk,.meas.vds_hs_die_pk,.meas.vgs_hs_off_max,
          .meas.vgs_ls_late_max,.meas.vgs_ls_min] | @csv' "$out/$tag.json" >> "$out/conditional.csv"
        printf '%s complete\n' "$tag"
      done
    done
  done
done
# Refine the three observed extrema without changing the physical model.
for tag in shunt_low_v280_esl10_td0 shunt_high_v198_esl1.06_td1 shunt_high_v170_esl1.06_td5; do
  params=()
  while read -r parameter; do params+=("$parameter"); done < <(
    jq -r '.params | .TRMAX="0.1n" | to_entries[] | "\(.key)=\(.value)"' "$out/$tag.json")
  PYTHONDONTWRITEBYTECODE=1 python3 "$runner" "$src/conditional_turnoff.cir" \
    "${params[@]}" --keep "$out/${tag}_refined" > "$out/${tag}_refined.json"
  jq -e -f "$src/accept-conditional.jq" \
    "$out/${tag}_refined.json" > /dev/null
done
# Temperature probes change only the vendor FET's imposed temperature. The
# idealized driver and passive parts do not acquire qualified hot behavior.
for temp in 100 150; do
  awk -v t="$temp" '/^\.tran / {print ".temp " t} {print}' \
    "$src/conditional_turnoff.cir" > "$out/conditional-${temp}C.cir"
  for tag in shunt_low_v280_esl10_td0 shunt_high_v198_esl1.06_td1 shunt_high_v170_esl1.06_td5; do
    params=()
    while read -r parameter; do params+=("$parameter"); done < <(
      jq -r '.params | .TRMAX="0.1n" | to_entries[] | "\(.key)=\(.value)"' "$out/$tag.json")
    PYTHONDONTWRITEBYTECODE=1 python3 "$runner" "$out/conditional-${temp}C.cir" \
      "${params[@]}" --keep "$out/${tag}_${temp}C" > "$out/${tag}_${temp}C.json"
    jq -e -f "$src/accept-conditional.jq" \
      "$out/${tag}_${temp}C.json" > /dev/null
  done
done
# Includes are copied only to ignored run output by the established runner.
shasum -a 256 "$src/leg_matrix_baseline.cir" "$src/conditional_turnoff.cir" \
  "$src/legA-h0-best.matrix.txt" "$src/matrix-params.inc" "$runner" \
  "$power/validation-plan/sim-kit/models/vendor/IFX_CFD7_650V.lib" \
  "$power/validation-plan/sim-kit/common/options.inc" > "$out/source-hashes.txt"
ngspice --version > "$out/ngspice-version.txt"
