#!/bin/sh
# Build the firmware's C1 control sources (unchanged) plus the ctypes shim as a
# host shared library for the co-simulation. Plain cc, not ESP-IDF.
#   usage: build_lib.sh <out_dir>     -> <out_dir>/libpantemp.so
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
fw="$here/../../../firmware/components/control"
out=${1:-"$here/build"}
mkdir -p "$out"
${CC:-cc} -std=c99 -O2 -fPIC -shared -Wall -Wextra -Wpedantic -Werror \
    -I"$fw" "$here/cosim_shim.c" \
    "$fw/pan_temp_estimator.c" "$fw/plant_gain.c" "$fw/pan_rate_pid.c" \
    "$fw/contact_check.c" "$fw/pan_sensor_guard.c" "$fw/pan_temp_loop.c" \
    -lm -o "$out/libpantemp.so"
echo "$out/libpantemp.so"
