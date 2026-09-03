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
# Today that yields fifteen modules: temper-drc-rs's full corpus plus its seven
# family shards, and one single-family corpus each for temper-geometry,
# temper-thermal, temper-design-bundle, temper-rust-router-core,
# temper-constraint-compiler, temper-quality-oracle and temper-io-types.
# Duplicates are collapsed by the topology loader: a single-family tier's full
# corpus and its only shard are the same module and are compiled once -- so
# those seven contribute seven builds, not fourteen.  None of the tiers added
# since this script was written needed an edit to it.
#
# Alongside each staged `<module>.wasm`, this script also writes
# `<module>.wasm.sha256.json` -- `{"sha256": "<hex>"}`, the sha256 of the exact
# bytes just staged. That sidecar is imported by the Worker entry points
# (families/*/index.js, src/index.js) next to the .wasm module itself and the
# expected-failure manifest, and returned from `/health` as `module_sha256`.
# It exists because a TEST COUNT is a weak proxy for "is this the same
# content": PR #941 fixed a clock bug that moved 7 temper-geometry tests from
# trapping to passing on wasm32 while the registered count stayed 722 both
# before and after, and check_deployed_freshness.mjs (which only ever compared
# counts) reported the stale pre-#941 module "fresh" for four commits -- see
# issue #945. The digest is computed here, not inside the Worker, because a
# deployed Worker only ever gets a COMPILED `WebAssembly.Module` (Cloudflare's
# bundler consumes the raw bytes at upload time) and there is no supported way
# to recover the original bytes from a compiled Module to hash them at
# request time; hashing at stage time, over the same bytes `cp` just staged,
# is the one point in the pipeline that still has the raw file.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(pwd)"
TOPOLOGY=""
TOPOLOGY_LOADER="${SCRIPT_DIR}/../tools/wasm/tier_topology.mjs"
STAGE_DIR=""
TARGET_DIR=""
PREVIEW_CANDIDATE=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --preview-candidate)
            PREVIEW_CANDIDATE=1
            shift
            ;;
        --repo-root|--topology|--output-dir|--target-dir)
            [ "$#" -ge 2 ] || { echo "error: $1 requires a value" >&2; exit 2; }
            case "$1" in
                --repo-root) REPO_ROOT="$2" ;;
                --topology) TOPOLOGY="$2" ;;
                --output-dir) STAGE_DIR="$2" ;;
                --target-dir) TARGET_DIR="$2" ;;
            esac
            shift 2
            ;;
        *)
            echo "error: unknown argument $1" >&2
            exit 2
            ;;
    esac
done

REPO_ROOT="$(cd -- "$REPO_ROOT" && pwd)"
TOPOLOGY="${TOPOLOGY:-${REPO_ROOT}/tools/wasm/wasm_tier_topology.json}"
STAGE_DIR="${STAGE_DIR:-${REPO_ROOT}/packages/temper-worker/src}"
TARGET_DIR="${TARGET_DIR:-${REPO_ROOT}/target-shared}"
mkdir -p "$STAGE_DIR" "$TARGET_DIR"
STAGE_DIR="$(cd -- "$STAGE_DIR" && pwd)"
TARGET_DIR="$(cd -- "$TARGET_DIR" && pwd)"
WASM_DIR="${TARGET_DIR}/wasm32-unknown-unknown/release"
CRATE="${REPO_ROOT}/packages/temper-wasm-test-runner/Cargo.toml"

if [ "$PREVIEW_CANDIDATE" -eq 1 ]; then
    # The PR preview is a fresh, exact allowlist. Refuse to mix this build with
    # an earlier attempt or a second module; the trusted attester repeats the
    # same check after the build.
    if find "$STAGE_DIR" -mindepth 1 -print -quit | grep -q .; then
        echo "error: preview output directory must be empty" >&2
        exit 1
    fi
fi

# `node` rather than `jq`: the deploy workflow already provisions Node (wrangler
# needs it), every other consumer of the topology is a .mjs, and jq is not
# guaranteed on a bare runner.  Failing here with a clear message beats an empty
# loop that stages nothing and reports success.
if ! command -v node >/dev/null 2>&1; then
    echo "error: node is required to read tools/wasm/wasm_tier_topology.json (the build matrix)." >&2
    exit 1
fi

MATRIX="$(TOPOLOGY_LOADER="$TOPOLOGY_LOADER" TOPOLOGY="$TOPOLOGY" PREVIEW_CANDIDATE="$PREVIEW_CANDIDATE" node -e '
import("node:url").then(({ pathToFileURL }) => import(pathToFileURL(process.env.TOPOLOGY_LOADER).href)).then(({ loadTopology, buildTargets, previewCandidateContract }) => {
  const topology = loadTopology(process.env.TOPOLOGY);
  const targets = process.env.PREVIEW_CANDIDATE === "1"
    ? [previewCandidateContract(topology)]
    : buildTargets(topology);
  for (const b of targets) {
    const crate = b.crate;
    const cargoFeatures = b.cargo_features;
    const stagedModule = b.module_file ?? b.staged_module;
    console.log([crate, cargoFeatures, stagedModule].join("\t"));
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
    (
        cd "$REPO_ROOT"
        # GitHub's file-command paths are removed for the credential-free PR
        # build so an untrusted build script cannot inject state into the
        # later fixed-command steps. The preview publisher is a different job;
        # this one never receives its credentials.
        env -u GITHUB_ENV -u GITHUB_OUTPUT -u GITHUB_PATH -u GITHUB_STEP_SUMMARY \
            -u GITHUB_TOKEN -u GH_TOKEN \
            -u ACTIONS_RUNTIME_TOKEN -u ACTIONS_CACHE_URL -u ACTIONS_RESULTS_URL \
            -u ACTIONS_ID_TOKEN_REQUEST_TOKEN -u ACTIONS_ID_TOKEN_REQUEST_URL \
            CARGO_TARGET_DIR="$TARGET_DIR" \
            cargo build --release --target wasm32-unknown-unknown \
                --no-default-features --features "$features" \
                --manifest-path "$CRATE"
    )
    cp "$WASM_DIR/temper_wasm_test_runner.wasm" "$STAGE_DIR/$staged"
    # sha256 of the exact bytes just staged -- see the header comment above
    # ("Alongside each staged...") for why this happens here rather than in
    # the Worker.
    DIGEST="$(sha256sum "$STAGE_DIR/$staged" | cut -d' ' -f1)"
    printf '{"sha256":"%s"}\n' "$DIGEST" > "$STAGE_DIR/$staged.sha256.json"
    echo "    sha256 ${DIGEST}"
done <<< "$MATRIX"

echo "=== Staged modules ==="
if [ "$PREVIEW_CANDIDATE" -eq 1 ]; then
    find "$STAGE_DIR" -maxdepth 1 -type f -name '*.wasm' -print
else
    ls -lh "$STAGE_DIR"/temper_wasm_test_runner*.wasm
fi
echo "=== Staged digests ==="
if [ "$PREVIEW_CANDIDATE" -eq 1 ]; then
    find "$STAGE_DIR" -maxdepth 1 -type f -name '*.wasm.sha256.json' -print
else
    ls -lh "$STAGE_DIR"/temper_wasm_test_runner*.wasm.sha256.json
fi
