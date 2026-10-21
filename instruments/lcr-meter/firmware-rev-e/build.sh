#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${PICO_SDK_PATH:?Set PICO_SDK_PATH to Pico SDK 2.2.0}"
: "${PICO_TOOLCHAIN_PATH:?Set PICO_TOOLCHAIN_PATH to Arm GNU 14.2.rel1}"
EXPECTED=a1438dff1d38bd9c65dbd693f0e5db4b9ae91779
[ "$(git -C "$PICO_SDK_PATH" rev-parse HEAD)" = "$EXPECTED" ] || { echo 'Unexpected SDK revision' >&2; exit 1; }
BUILD=${TEMPER_LCR_BUILD_DIR:-/private/tmp/temper-lcr-reve-build}
mkdir -p "$BUILD" "$ROOT/bin" "$ROOT/verification"
cmake -S "$ROOT" -B "$BUILD" -DPICO_BOARD=pico -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" -j 6
# Averaging, waveform and codec-sequence logic, compiled for and run on the build host.
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -pedantic -I"$ROOT/src" "$ROOT/test/test_host.c" \
    "$ROOT/src/syncavg.c" "$ROOT/src/wave.c" "$ROOT/src/tac5112.c" -lm -o "$BUILD/test_host"
"$BUILD/test_host" > "$ROOT/verification/host-test.txt"
rustc --edition=2021 -O "$ROOT/../firmware/tools/bin_to_uf2.rs" -o "$BUILD/bin_to_uf2"
rustc --edition=2021 -O "$ROOT/tools/verify_tdm.rs" -o "$BUILD/verify_tdm"
rustc --edition=2021 -O "$ROOT/tools/hot_loop_bound.rs" -o "$BUILD/hot_loop_bound"
"$BUILD/bin_to_uf2" "$BUILD/temper_lcr.bin" "$ROOT/bin/temper-lcr-rev-e.uf2" > "$ROOT/verification/uf2.txt"
cp "$BUILD/temper_lcr.elf" "$ROOT/bin/temper-lcr-rev-e.elf"
cp "$BUILD/tdm.pio.h" "$ROOT/verification/tdm.pio.h"
"$BUILD/verify_tdm" "$BUILD/tdm.pio.h" > "$ROOT/verification/pio.txt"
"$PICO_TOOLCHAIN_PATH/bin/arm-none-eabi-size" "$BUILD/temper_lcr.elf" > "$ROOT/verification/size.txt"
"$PICO_TOOLCHAIN_PATH/bin/arm-none-eabi-objdump" -d --no-show-raw-insn "$BUILD/temper_lcr.elf" > "$BUILD/disassembly.txt"
"$BUILD/hot_loop_bound" "$BUILD/disassembly.txt" > "$ROOT/verification/hot-loop.txt"
(cd "$ROOT" && shasum -a 256 CMakeLists.txt build.sh README.md src/* test/* tools/* bin/* > verification/SHA256SUMS)
