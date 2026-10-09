#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT=${1:?usage: replay.sh owned-output-directory}
mkdir -p "$OUT"
(cd "$HERE" && shasum -a 256 -c SOURCE_SHA256) > "$OUT/preflight.log"
clang --version > "$OUT/clang-version.txt"
rustc --version > "$OUT/rustc-version.txt"
ngspice --version > "$OUT/ngspice-version.txt"
# Compiler changes do not change the analytical contract; the simulator version
# must match the recorded observation before this receipt claims reproduction.
if ! grep -q 'ngspice-45.2 ' "$OUT/ngspice-version.txt"; then
    echo 'Unsupported ngspice version; no reproduced result claimed' >&2
    exit 2
fi
clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g \
    "$HERE/isolation.c" "$HERE/test_isolation.c" -o "$OUT/isolation-tests"
"$OUT/isolation-tests" > "$OUT/isolation-tests.log"
rustc --edition=2021 -D warnings "$HERE/exposure.rs" -o "$OUT/exposure-study"
"$OUT/exposure-study" "$OUT/exposure" > "$OUT/exposure.log"
rustc --edition=2021 -D warnings "$HERE/discharge-window.rs" -o "$OUT/discharge-window"
"$OUT/discharge-window" > "$OUT/discharge-window.log"
# These intentionally wrong candidates must fail the real test harness.
sed 's/age>=PICKUP_US/age>=0/g' "$HERE/isolation.c" > "$OUT/no-pickup-dwell.c"
sed 's/if (safe \&\& reset \&\& s->reset_armed)/if (safe \&\& i->reset)/' \
    "$HERE/isolation.c" | sed 's/const bool reset=i->reset \&\& !s->previous_reset;/const bool reset=i->reset \&\& !s->previous_reset; (void)reset;/' > "$OUT/level-reset.c"
for mutation in no-pickup-dwell level-reset; do
    # The unsigned age>=0 mutation deliberately produces a tautology warning;
    # compile this negative-control body without -Werror, leaving harness intact.
    clang -std=c11 -I"$HERE" "$OUT/$mutation.c" "$HERE/test_isolation.c" -o "$OUT/$mutation"
    if (ulimit -c 0; "$OUT/$mutation") > "$OUT/$mutation.log" 2>&1; then
        echo "Mutation survived: $mutation" >&2; exit 1
    fi
    echo "Rejected expected mutation: $mutation" >> "$OUT/negative-controls.log"
done
echo 'PASS sequence + 54 conditional exposure cases + two mutation controls; NO POWER RELEASE'
