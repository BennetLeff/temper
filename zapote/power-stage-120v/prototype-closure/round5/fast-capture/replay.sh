#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/../../../../.." && pwd)
OUT="$REPO/output/temper-prototype-closure/round5/fast-capture"
IVERILOG=${IVERILOG:-iverilog}
VVP=${VVP:-vvp}
mkdir -p "$OUT"
"$IVERILOG" -g2012 -Wall -I"$HERE/tests" -s tb_capture -o "$OUT/capture.vvp" "$HERE"/rtl/*.v "$HERE/tests/tb_capture.sv"
(cd "$OUT" && "$VVP" capture.vvp) > "$OUT/rtl-test.log"
clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
 -I"$HERE/../firmware/common" -I"$REPO/firmware/components/power/include" \
 "$HERE/tests/receiver_oracle.c" "$HERE/../firmware/common/fast_capture.c" \
 "$REPO/firmware/components/power/fullbridge_adapter.c" -o "$OUT/receiver-oracle"
"$OUT/receiver-oracle" "$OUT/frames.hex" > "$OUT/receiver-test.log"
cat "$OUT/rtl-test.log" "$OUT/receiver-test.log"
if [ -n "${ICE40_CELLS_SIM:-}" ]; then
 "$IVERILOG" -g2012 -s tb_gate_map -o "$OUT/gate-map.vvp" "$HERE/rtl/gate_map.v" "$HERE/tests/tb_gate_map.sv" "$ICE40_CELLS_SIM"
 "$VVP" "$OUT/gate-map.vvp" > "$OUT/gate-map-test.log"
 cat "$OUT/gate-map-test.log"
fi
