#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${PICO_SDK_PATH:?Set PICO_SDK_PATH to Pico SDK 2.2.0}"
: "${PICO_TOOLCHAIN_PATH:?Set PICO_TOOLCHAIN_PATH to Arm GNU 14.2.rel1}"
EXPECTED=a1438dff1d38bd9c65dbd693f0e5db4b9ae91779
[ "$(git -C "$PICO_SDK_PATH" rev-parse HEAD)" = "$EXPECTED" ] || { echo 'Unexpected SDK revision' >&2; exit 1; }
BUILD=${TEMPER_LCR_BUILD_DIR:-/private/tmp/temper-lcr-reve-build}
mkdir -p "$BUILD" "$ROOT/bin" "$ROOT/verification"
rustc --edition=2021 -O "$ROOT/../firmware/tools/bin_to_uf2.rs" -o "$BUILD/bin_to_uf2"
rustc --edition=2021 -O "$ROOT/tools/verify_tdm.rs" -o "$BUILD/verify_tdm"
rustc --edition=2021 -O "$ROOT/tools/hot_loop_bound.rs" -o "$BUILD/hot_loop_bound"
: > "$ROOT/verification/host-test.txt"
: > "$ROOT/verification/hot-loop.txt"
: > "$ROOT/verification/size.txt"
: > "$ROOT/verification/uf2.txt"
# Two builds (README "Sample rate"): the default 187.5 kHz image and the 375 kHz variant.
# NAME FS_375K CYCLES_PER_FRAME (SYSTEM_CLOCK_HZ / FS_HZ, the hot-loop budget)
for build in "temper-lcr-rev-e 0 640" "temper-lcr-rev-e-375k 1 288"; do
    set -- $build
    NAME=$1 FS_375K=$2 BUDGET=$3
    DIR="$BUILD/$NAME"
    cmake -S "$ROOT" -B "$DIR" -DPICO_BOARD=pico -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release \
        -DLCR_FS_375K="$FS_375K"
    cmake --build "$DIR" -j 6
    # Averaging, waveform, codec-sequence and relay logic, compiled for and run on the build host.
    ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -pedantic -DLCR_FS_375K="$FS_375K" -I"$ROOT/src" \
        "$ROOT/test/test_host.c" "$ROOT/src/syncavg.c" "$ROOT/src/wave.c" "$ROOT/src/tac5112.c" \
        "$ROOT/src/relay.c" -lm -o "$DIR/test_host"
    "$DIR/test_host" >> "$ROOT/verification/host-test.txt"
    "$BUILD/bin_to_uf2" "$DIR/temper_lcr.bin" "$ROOT/bin/$NAME.uf2" | sed "s/^/$NAME: /" >> "$ROOT/verification/uf2.txt"
    cp "$DIR/temper_lcr.elf" "$ROOT/bin/$NAME.elf"
    "$PICO_TOOLCHAIN_PATH/bin/arm-none-eabi-size" "$DIR/temper_lcr.elf" | sed "s|$DIR/temper_lcr.elf|bin/$NAME.elf|" >> "$ROOT/verification/size.txt"
    "$PICO_TOOLCHAIN_PATH/bin/arm-none-eabi-objdump" -d --no-show-raw-insn "$DIR/temper_lcr.elf" > "$DIR/disassembly.txt"
    "$BUILD/hot_loop_bound" "$DIR/disassembly.txt" "$BUDGET" | sed "s/^/$NAME: /" >> "$ROOT/verification/hot-loop.txt"
done
# Both PIO programs are assembled in every build; check them from the default build.
cp "$BUILD/temper-lcr-rev-e/tdm.pio.h" "$ROOT/verification/tdm.pio.h"
cp "$BUILD/temper-lcr-rev-e/tdm375.pio.h" "$ROOT/verification/tdm375.pio.h"
"$BUILD/verify_tdm" "$ROOT/verification/tdm.pio.h" "$ROOT/verification/tdm375.pio.h" > "$ROOT/verification/pio.txt"
(cd "$ROOT" && shasum -a 256 CMakeLists.txt build.sh README.md src/* test/* tools/* bin/* > verification/SHA256SUMS)
