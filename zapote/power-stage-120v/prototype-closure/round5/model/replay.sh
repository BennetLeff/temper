#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../../../.." && pwd)
model="$root/zapote/power-stage-120v/prototype-closure/round5/model"
common="$root/zapote/power-stage-120v/prototype-closure/round5/firmware/common"
isolation="$root/zapote/power-stage-120v/prototype-closure/round5/protection-closure"
out=${1:?Pass a NEW absolute output directory under output/temper-prototype-closure/round5/model}
case "$out" in "$root/output/temper-prototype-closure/round5/model/"*) ;; *) echo 'Output must remain in round5/model' >&2;exit 2;; esac
mkdir "$out"
printf 'INCOMPLETE\n' > "$out/STATUS"
vendor=${TEMPER_VENDOR_MODEL:-/Users/bennet/Desktop/temper/worktrees/ps-oracle/zapote/power-stage-120v/validation-plan/sim-kit/models/vendor/IFX_CFD7_650V.lib}
lib=/opt/homebrew/Cellar/libngspice/45.2
cd "$root"
inputs=("$model"/*.c "$model"/*.h "$model"/*.rs "$model"/*.cir "$model/replay.sh" "$common/acquisition.c" "$common/acquisition.h" "$common/supervisor_binding.c" "$common/supervisor_binding.h" "$common/supervisor_outputs.c" "$common/supervisor_outputs.h" "$isolation/isolation.c" "$isolation/isolation.h" "$isolation/interface.json" firmware/components/power/fullbridge_adapter.c firmware/components/power/include/fullbridge_adapter.h firmware/components/power/energy_supervisor.c firmware/components/power/include/energy_supervisor.h zapote/power-stage-120v/prototype-closure/round4/fields/evidence/A-e4-h1-matrix.json zapote/power-stage-120v/prototype-closure/round4/fields/evidence/B-e4-f4-h1-matrix.json zapote/power-stage-120v/prototype-closure/round5/protection/interface.json output/temper-prototype-closure/round5/protection/closed-loop-topology.json "$vendor" "$lib/lib/libngspice.0.dylib" "$lib/include/ngspice/sharedspice.h")
shasum -a 256 "${inputs[@]}" > "$out/inputs.sha256"
shasum -a 256 "$root/zapote/power-stage-120v/prototype-closure/round5/boards/pre-pins.tsv" >> "$out/inputs.sha256"
clang --version > "$out/tool-versions.txt"
rustc --version >> "$out/tool-versions.txt"
/opt/homebrew/bin/ngspice --version >> "$out/tool-versions.txt"
shasum -a 256 "$common/measurement.c" "$common/measurement.h" "$common/bypass.c" "$common/bypass.h" >> "$out/inputs.sha256"
clang -O2 -Wall -Wextra -I"$lib/include" -Ifirmware/components/power/include -I"$common" -I"$isolation" "$model/cosim.c" "$common/measurement.c" "$common/bypass.c" firmware/components/power/fullbridge_adapter.c firmware/components/power/energy_supervisor.c "$common/acquisition.c" "$common/supervisor_binding.c" "$common/supervisor_outputs.c" "$isolation/isolation.c" -L"$lib/lib" -lngspice -o "$out/cosim"
clang -O2 -I"$lib/include" "$model/runtime_check.c" -L"$lib/lib" -lngspice -o "$out/runtime-check"
"$out/runtime-check" > "$out/runtime-check.log"
clang -O2 -Wall -Wextra "$model/test_measurement.c" "$model/sampled_measurement.c" -o "$out/measurement-test"
"$out/measurement-test" > "$out/measurement-tests.log"
clang -O2 -Wall -Wextra -Werror -I"$common" "$model/test_shared_measurement.c" "$common/measurement.c" "$common/bypass.c" -o "$out/shared-measurement-test"
"$out/shared-measurement-test" > "$out/shared-measurement-tests.log"
clang -O2 -Wall -Wextra -Werror "$model/test_contact_model.c" -o "$out/contact-model-test"
"$out/contact-model-test" > "$out/contact-model-tests.log"
for source in cases device_runner energy_ode geometry_gate audit; do rustc --edition 2021 -O "$model/$source.rs" -o "$out/$source"; done
rustc --edition 2021 --test "$model/energy_ode.rs" -o "$out/energy-test"
"$out/energy-test" > "$out/energy-tests.log"
rustc --edition 2021 --test "$model/audit.rs" -o "$out/audit-test"
"$out/audit-test" > "$out/audit-tests.log"
"$out/cases" "$model/averaged.cir" "$out/verified-cases" "$out/cosim"
"$out/device_runner" "$root" "$out/device-reference-psa" "$vendor"
"$out/energy_ode" "$out/energy-ode.csv"
set +e
"$out/geometry_gate" output/temper-prototype-closure/round5/protection/closed-loop-topology.json > "$out/geometry-gate.json"
geometry_status=$?
set -e
[[ $geometry_status == 3 ]] || { echo 'Expected incomplete physical geometry rejection' >&2;exit 1; }
"$out/audit" "$out" > "$out/audit.log"
shasum -a 256 -c "$out/inputs.sha256" > "$out/input-recheck.log"
printf 'DIAGNOSTIC_REPLAY_COMPLETE_NO_POWER_RELEASE\n' > "$out/STATUS"
