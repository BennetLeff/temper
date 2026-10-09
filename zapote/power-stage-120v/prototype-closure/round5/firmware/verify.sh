#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/../../../../.." && pwd)
OUT=${OUT:-"$REPO/output/temper-prototype-closure/round5/firmware/verification"}
mkdir -p "$OUT"
printf 'INCOMPLETE\n' > "$OUT/replay-status.txt"
TMP=$(mktemp -d /private/tmp/temper-r5-target-verify.XXXXXX)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
CC=${CC:-clang}
FLAGS="-std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined"
for TEST in acquisition fast_capture mirror; do
  "$CC" $FLAGS -I"$HERE/common" -I"$REPO/firmware/components/power/include" \
    "$HERE/common/$TEST.c" "$HERE/tests/test_$TEST.c" -o "$TMP/$TEST"
  "$TMP/$TEST" > "$OUT/$TEST-tests.txt"
done
for TEST in review_regressions measurement bypass; do
  "$CC" $FLAGS -I"$HERE/common" -I"$REPO/firmware/components/power/include" \
    "$HERE/common/acquisition.c" "$HERE/common/qualification.c" "$HERE/common/measurement.c" \
    "$HERE/common/sensor_frontend.c" "$HERE/common/line_telemetry.c" "$HERE/common/fast_capture.c" "$HERE/common/bypass.c" \
    "$HERE/tests/test_$TEST.c" -lm -o "$TMP/$TEST"
  "$TMP/$TEST" > "$OUT/$TEST-tests.txt"
done
if [ -n "${IDF_PATH:-}" ]; then
  "$CC" $FLAGS -I"$IDF_PATH/components/soc/esp32s3/include" -I"$REPO/firmware/components/power/include" \
    "$HERE/tests/test_mcpwm_register_contract.c" "$REPO/firmware/components/power/fullbridge_adapter.c" \
    -lm -o "$TMP/mcpwm"
  "$TMP/mcpwm" > "$OUT/mcpwm-register-tests.txt"
else
  printf 'NOT RUN: IDF_PATH required for real SDK register layout\n' > "$OUT/mcpwm-register-tests.txt"
fi
"$CC" $FLAGS -I"$REPO/firmware/components/power/include" "$HERE/tests/test_feedback_kind.c" \
  "$REPO/firmware/components/power/fullbridge_adapter.c" -lm -o "$TMP/feedback"
"$TMP/feedback" > "$OUT/feedback-kind-tests.txt"
"$CC" $FLAGS -I"$REPO/firmware/components/power/include" -I"$HERE/common" -I"$HERE/../protection-closure" \
  "$HERE/tests/test_supervisor_binding.c" "$HERE/common/supervisor_binding.c" "$HERE/common/supervisor_outputs.c" \
  "$HERE/../protection-closure/isolation.c" "$REPO/firmware/components/power/energy_supervisor.c" -lm -o "$TMP/binding"
"$TMP/binding" > "$OUT/supervisor-binding-tests.txt"
if [ -n "${IDF_PATH:-}" ]; then
  "$CC" $FLAGS -I"$IDF_PATH/components/soc/esp32s3/include" -I"$REPO/firmware/components/power/include" -I"$HERE/esp32" \
    "$HERE/tests/test_readback.c" "$REPO/firmware/components/power/fullbridge_adapter.c" -lm -o "$TMP/readback"
  "$TMP/readback" > "$OUT/readback-tests.txt"
fi
"$CC" $FLAGS -I"$REPO/firmware/components/power/include" "$REPO/firmware/test/test_power_adapter.c" \
  "$REPO/firmware/components/power/energy_supervisor.c" "$REPO/firmware/components/power/fullbridge_adapter.c" \
  "$REPO/firmware/components/power/energy_link.c" "$REPO/firmware/components/power/power_service.c" -lm -o "$TMP/power"
"$TMP/power" > "$OUT/power-adapter-tests.txt"
"$CC" $FLAGS -I"$REPO/firmware/components/power/include" -I"$HERE/common" -I"$HERE/../protection-closure" \
  "$HERE/tests/test_output_protocol.c" "$HERE/common/supervisor_binding.c" "$HERE/common/supervisor_outputs.c" \
  "$HERE/../protection-closure/isolation.c" "$REPO/firmware/components/power/energy_supervisor.c" -lm -o "$TMP/output-protocol"
"$TMP/output-protocol" > "$OUT/output-protocol-tests.csv"
"$CC" $FLAGS -I"$REPO/firmware/components/power/include" -I"$HERE/common" \
  "$HERE/tests/test_controller_intent.c" "$REPO/firmware/components/power/energy_link.c" -o "$TMP/controller-intent"
"$TMP/controller-intent" > "$OUT/controller-intent-tests.txt"
python3 "$HERE/tests/check_contract.py" > "$OUT/pin-contract-check.txt"
printf 'PASS_HOST_CHECKS_ONLY_NOT_HARDWARE_QUALIFICATION\n' > "$OUT/replay-status.txt"
