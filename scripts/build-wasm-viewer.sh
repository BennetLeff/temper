#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VIEWER_DIR="$SCRIPT_DIR/../packages/temper-viewer"
OUTPUT_DIR="$SCRIPT_DIR/../packages/temper-placer/src/temper_placer/visualization/static/wasm"

echo "=== Building temper-viewer (WASM) ==="

cd "$VIEWER_DIR"

# Build for WASM target
wasm-pack build --target web --out-dir pkg "$@"

# Optimize WASM binary if wasm-opt is available
if command -v wasm-opt &> /dev/null; then
    echo "=== Optimizing with wasm-opt ==="
    wasm-opt -Os pkg/temper_viewer_bg.wasm -o pkg/temper_viewer_bg.wasm
else
    echo "NOTE: wasm-opt not found. Install binaryen for smaller WASM output."
fi

# Copy to static directory
mkdir -p "$OUTPUT_DIR"
cp pkg/temper_viewer.js "$OUTPUT_DIR/"
cp pkg/temper_viewer_bg.wasm "$OUTPUT_DIR/"

# Size check
WASM_SIZE=$(stat -f%z "$OUTPUT_DIR/temper_viewer_bg.wasm" 2>/dev/null || stat -c%s "$OUTPUT_DIR/temper_viewer_bg.wasm" 2>/dev/null)
echo "=== Build complete ==="
echo "WASM binary: $OUTPUT_DIR/temper_viewer_bg.wasm (${WASM_SIZE} bytes)"
echo "JS glue:     $OUTPUT_DIR/temper_viewer.js"
