#!/bin/bash
# Build every WASM module the tier deploys and stage them in
# packages/temper-worker/src/ for deployment.  Run from repo root.
#
# The build matrix is NOT written out here.  It is read from
# tools/wasm/wasm_tier_topology.json -- the same file the deploy workflow, the
# sweep client and the freshness checker read -- so a module cannot be built
# without being deployed, swept and checked, or vice versa.  See that file's
# `_comment` for why the list used to live in four places and why that was a
# latent staleness bug rather than a tidiness complaint.
#
# Today that yields nine modules: temper-drc-rs's full corpus plus its seven
# family shards, and temper-geometry's single-family corpus.  Duplicates are
# collapsed by the topology loader: temper-geometry's full corpus and its only
# shard are the same module and are compiled once.
set -euo pipefail

WASM_DIR="target-shared/wasm32-unknown-unknown/release"
STAGE_DIR="packages/temper-worker/src"
CRATE="packages/temper-wasm-test-runner/Cargo.toml"

# `node` rather than `jq`: the deploy workflow already provisions Node (wrangler
# needs it), every other consumer of the topology is a .mjs, and jq is not
# guaranteed on a bare runner.  Failing here with a clear message beats an empty
# loop that stages nothing and reports success.
if ! command -v node >/dev/null 2>&1; then
    echo "error: node is required to read tools/wasm/wasm_tier_topology.json (the build matrix)." >&2
    exit 1
fi

MATRIX="$(node -e '
import("./tools/wasm/tier_topology.mjs").then(({ loadTopology, buildTargets }) => {
  for (const b of buildTargets(loadTopology())) {
    console.log([b.crate, b.cargo_features, b.staged_module].join("\t"));
  }
}).catch((e) => { console.error(e.message); process.exit(1); });
')"

if [ -z "$MATRIX" ]; then
    echo "error: tools/wasm/wasm_tier_topology.json yielded an empty build matrix; refusing to report success having staged nothing." >&2
    exit 1
fi

while IFS=$'\t' read -r crate features staged; do
    [ -n "$features" ] || continue
    echo "=== Building ${crate} (--features ${features}) -> ${staged} ==="
    cargo build --release --target wasm32-unknown-unknown \
        --no-default-features --features "$features" \
        --manifest-path "$CRATE"
    cp "$WASM_DIR/temper_wasm_test_runner.wasm" "$STAGE_DIR/$staged"
done <<< "$MATRIX"

echo "=== Staged modules ==="
ls -lh "$STAGE_DIR"/temper_wasm_test_runner*.wasm
