#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(git -C "$here" rev-parse --show-toplevel)
out="$repo/zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D29"
mkdir -p "$out"
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g \
 -I"$here/pwm_stub" -I"$repo/firmware/components/power/include" \
 "$here/test_pwm_target.c" "$repo/firmware/components/power/fullbridge_adapter.c" -lm -o "$out/test_pwm_target"
"$out/test_pwm_target"
