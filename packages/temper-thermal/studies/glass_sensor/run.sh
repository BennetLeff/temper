#!/usr/bin/env bash
set -euo pipefail
STUDY_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="${TEMPER_REPO:-$(cd "$STUDY_DIR/../../../.." && pwd)}"
OUTPUT_DIR="${1:-$STUDY_DIR/results}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/temper-glass-build.XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT
export MPLCONFIGDIR="$BUILD_DIR/mpl"
mkdir -p "$OUTPUT_DIR"
"$PYTHON_BIN" "$STUDY_DIR/audit.py" "$STUDY_DIR" "$REPO_DIR" "$OUTPUT_DIR" before
rustfmt --check "$STUDY_DIR/model.rs" "$STUDY_DIR/main.rs" "$STUDY_DIR/controller.rs"
rustc --edition=2021 -D warnings --test "$STUDY_DIR/model.rs" -o "$BUILD_DIR/tests"
"$BUILD_DIR/tests" > "$OUTPUT_DIR/tests.txt"
rustc --edition=2021 -D warnings -O "$STUDY_DIR/main.rs" -o "$BUILD_DIR/study"
"$BUILD_DIR/study" "$OUTPUT_DIR" > "$OUTPUT_DIR/run-log.txt"
CONTROL_DIR="$REPO_DIR/firmware/components/control"
TEST_DIR="$REPO_DIR/firmware/test"
cc -std=c99 -O2 -I "$CONTROL_DIR" -c "$STUDY_DIR/controller_bridge.c" -o "$BUILD_DIR/bridge.o"
cc -std=c99 -O2 -c "$CONTROL_DIR/pid_control.c" -o "$BUILD_DIR/pid.o"
cc -std=c99 -O2 -c "$CONTROL_DIR/cascade_pid.c" -o "$BUILD_DIR/cascade.o"
ar rcs "$BUILD_DIR/libstudy_control.a" "$BUILD_DIR/bridge.o" "$BUILD_DIR/pid.o" "$BUILD_DIR/cascade.o"
rustc --edition=2021 -D warnings -O "$STUDY_DIR/controller.rs" -L "$BUILD_DIR" -l static=study_control -o "$BUILD_DIR/controller"
"$BUILD_DIR/controller" "$OUTPUT_DIR"
for suite in cascade_pid probe_detection; do
    cc -std=c99 -O2 -I "$TEST_DIR" -I "$TEST_DIR/unity" -I "$CONTROL_DIR" \
        "$TEST_DIR/test_main_${suite}.c" "$TEST_DIR/test_${suite}.c" \
        "$CONTROL_DIR/pid_control.c" "$CONTROL_DIR/cascade_pid.c" "$TEST_DIR/unity/unity.c" \
        -lm -o "$BUILD_DIR/$suite"
    "$BUILD_DIR/$suite" > "$OUTPUT_DIR/$suite-tests.txt"
done
"$PYTHON_BIN" "$STUDY_DIR/render.py" "$OUTPUT_DIR" > "$OUTPUT_DIR/plot-log.txt"
for name in mechanical traces controller_traces; do
    gzip -n -f "$OUTPUT_DIR/$name.csv"
done
"$PYTHON_BIN" "$STUDY_DIR/audit.py" "$STUDY_DIR" "$REPO_DIR" "$OUTPUT_DIR" after
printf 'Completed study: %s\n' "$OUTPUT_DIR"
