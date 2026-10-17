#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/../../../../.." && pwd)
OUT="$REPO/output/temper-prototype-closure/round5/firmware"
mkdir -p "$OUT"
printf 'INCOMPLETE\n' > "$OUT/replay-status.txt"
TMP=$(mktemp -d /private/tmp/temper-r5-firmware.XXXXXX)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
CC=${CC:-clang}
for TEST in acquisition fast_capture; do
  "$CC" -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -I"$HERE/common" -I"$REPO/firmware/components/power/include" \
    "$HERE/common/$TEST.c" "$HERE/tests/test_$TEST.c" -o "$TMP/test_$TEST"
  "$TMP/test_$TEST" > "$OUT/$TEST-tests.txt"
done
python3 "$HERE/tests/check_contract.py" > "$OUT/pin-contract-check.txt"
if [ -n "${CMSIS_DEVICE:-}" ] && [ -n "${CMSIS_CORE:-}" ]; then
  for UNIT in platform startup; do
    "$CC" -target arm-none-eabi -mcpu=cortex-m0plus -mthumb -ffreestanding -std=gnu11 \
      -Wall -Wextra -Werror -Wno-initializer-overrides \
      -I"$CMSIS_DEVICE" -I"$CMSIS_CORE" -I"$HERE/common" \
      -I"$REPO/firmware/components/power/include" -c "$HERE/stm32/$UNIT.c" -o "$TMP/$UNIT.o"
  done
  file "$TMP/platform.o" "$TMP/startup.o" > "$OUT/arm-object-check.txt"
else
  printf 'NOT RUN: set CMSIS_DEVICE and CMSIS_CORE to official ST/ARM includes.\n' > "$OUT/arm-object-check.txt"
fi
printf 'PASS_HOST_CHECKS_ONLY\n' > "$OUT/replay-status.txt"
