#!/bin/bash
# Build all per-family WASM modules and stage them in packages/temper-worker/src/
# for deployment.  Run from repo root.
set -euo pipefail

WASM_DIR="target-shared/wasm32-unknown-unknown/release"
STAGE_DIR="packages/temper-worker/src"
CRATE="packages/temper-wasm-test-runner/Cargo.toml"

echo "=== Building full (default) ==="
cargo build --release --target wasm32-unknown-unknown --manifest-path "$CRATE"
cp "$WASM_DIR/temper_wasm_test_runner.wasm" "$STAGE_DIR/"

for family in drc emc erc safety placement routing infra; do
    echo "=== Building wasm-registry-$family ==="
    cargo build --release --target wasm32-unknown-unknown \
        --no-default-features --features "wasm-registry-$family" \
        --manifest-path "$CRATE"
    cp "$WASM_DIR/temper_wasm_test_runner.wasm" \
       "$STAGE_DIR/temper_wasm_test_runner_${family}.wasm"
done

echo "=== Staged modules ==="
ls -lh "$STAGE_DIR"/temper_wasm_test_runner*.wasm
