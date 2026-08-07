#!/bin/bash
# R1 WASM substrate smoke test — rungs 2-3.
#
# Builds the wasm32 artifact, runs all 95 tests under wasmtime,
# and compares verdicts with native. Exits non-zero on any
# unexpected mismatch.
#
# Requires: rustup (wasm32-unknown-unknown target), wasmtime, wasm-tools.
#
# Usage:
#   tools/wasm/run_r1_smoke.sh              # full rung 2 + 3
#   tools/wasm/run_r1_smoke.sh --build-only # rung 2 only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Verify prerequisites
command -v wasmtime >/dev/null 2>&1 || { echo "ERROR: wasmtime not found. Install: brew install wasmtime"; exit 2; }
command -v wasm-tools >/dev/null 2>&1 || { echo "ERROR: wasm-tools not found. Install: brew install wasm-tools"; exit 2; }

# Check wasm32 target
if ! rustup target list --installed | grep -q wasm32-unknown-unknown; then
    echo "Installing wasm32-unknown-unknown target..."
    rustup target add wasm32-unknown-unknown
fi

cd "$REPO_ROOT"
exec python3 tools/wasm/run_r1_smoke.py "$@"
