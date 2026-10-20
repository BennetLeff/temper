#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${PICO_SDK_PATH:?Set PICO_SDK_PATH to Pico SDK 2.2.0}"
: "${PICO_TOOLCHAIN_PATH:?Set PICO_TOOLCHAIN_PATH to Arm GNU 14.2.rel1}"
EXPECTED=a1438dff1d38bd9c65dbd693f0e5db4b9ae91779
[ "$(git -C "$PICO_SDK_PATH" rev-parse HEAD)" = "$EXPECTED" ] || { echo 'Unexpected SDK revision' >&2; exit 1; }
BUILD=${TEMPER_LCR_BUILD_DIR:-/private/tmp/temper-lcr-revb-build}
mkdir -p "$BUILD" "$ROOT/bin" "$ROOT/verification"
cmake -S "$ROOT" -B "$BUILD" -DPICO_BOARD=pico -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" -j 6
rustc --edition=2021 -O "$ROOT/tools/bin_to_uf2.rs" -o "$BUILD/bin_to_uf2"
rustc --edition=2021 -O "$ROOT/tools/verify_pio.rs" -o "$BUILD/verify_pio"
"$BUILD/bin_to_uf2" "$BUILD/temper_lcr.bin" "$ROOT/bin/temper-lcr-rev-b.uf2" > "$ROOT/verification/uf2.txt"
cp "$BUILD/temper_lcr.elf" "$ROOT/bin/temper-lcr-rev-b.elf"
cp "$BUILD/capture.pio.h" "$ROOT/verification/capture.pio.h"
"$BUILD/verify_pio" "$BUILD/capture.pio.h" > "$ROOT/verification/pio.txt"
"$PICO_TOOLCHAIN_PATH/bin/arm-none-eabi-size" "$BUILD/temper_lcr.elf" > "$ROOT/verification/size.txt"
(cd "$ROOT" && shasum -a 256 CMakeLists.txt src/* tools/* bin/* > verification/SHA256SUMS)
