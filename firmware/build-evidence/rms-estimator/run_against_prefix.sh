#!/usr/bin/env bash
# Shows that test_rms_estimator.c fails on the pre-fix estimator and passes on the fixed one.
# Usage: run_against_prefix.sh [PRE_FIX_COMMIT]   (default 93276ac80, the integration commit the fix is cut from)
# Builds the test twice with plain cc: once against firmware/components/power as of PRE_FIX_COMMIT,
# once against the working tree. Expect: first run aborts on the +-0.5 % assertion, second passes.
set -uo pipefail
PRE="${1:-93276ac80}"
FW="$(cd "$(dirname "$0")/../.." && pwd)"
REPO="$(git -C "$FW" rev-parse --show-toplevel)"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK:?}"' EXIT
mkdir -p "$WORK/pre"
git -C "$REPO" archive "$PRE" firmware/components/power firmware/components/hal/include | tar -x -C "$WORK/pre"
SRC="$WORK/pre/firmware/components/power"
build_run() { # label, power dir, hal include dir, output
  cc -std=gnu99 -Wall -Wextra -Werror -UNDEBUG -DHOST_BUILD -I"$2/include" -I"$3" \
     -o "$WORK/bin_$1" "$FW/test/test_rms_estimator.c" "$2/n21_signal.c" "$2/input_limits.c" "$2/blower_aux.c" -lm || return 99
  "$WORK/bin_$1" 2>&1; echo "exit code: $?"
}
echo "=== pre-fix ($PRE) ==="
build_run pre "$SRC" "$WORK/pre/firmware/components/hal/include"
echo "=== fixed (working tree) ==="
build_run fixed "$FW/components/power" "$FW/components/hal/include"
