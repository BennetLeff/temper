/**
 * temper-wasm-rust-router — the temper-rust-router tier's only Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features rust-router-wasm-test-registry`,
 * which carries temper-rust-router's whole wasm32 registry (20 tests as of
 * 2026-08-11, all executable, all passing — see
 * `packages/temper-rust-router/src/wasm_test_registry.rs`'s own header).
 *
 * 20 is both the registered and the executable count for this crate, the
 * same shape as temper-design-bundle's 24/24 and temper-io-types's
 * 144/144: no entry in this crate's registry carries its own
 * `#[cfg(not(target_arch = "wasm32"))]`. `cargo test --no-default-features
 * --manifest-path packages/temper-rust-router/Cargo.toml` runs 23 lib
 * tests (0 failed): the wasm32 registry's 20 plus 3 `proptests::*` tests
 * (`f32s_from_le_bytes`'s round-trip properties) that use the `proptest`
 * dev-dependency, which is not linked into the ordinary (non-test) build
 * this registry compiles into — the same `proptest-dev-dependency` class
 * every other crate on the tier already excludes on the same grounds.
 * Measured 2026-08-11 with `node tools/wasm/run_wasm_tests.mjs` against the
 * actual build: 20 registered, 20 executed, 20 passed, 0 failed — and
 * diffed (not just counted) against the native 23: the wasm32 20 are an
 * exact subset.
 *
 * # Why one Worker and not eight
 *
 * temper-rust-router declares exactly one family
 * (`wasm-registry-rust-router`) — the three surviving modules
 * (`layer_assignment`, `terminal_planning`, `net_ordering`) are a flat set
 * of pure topology kernels with no rule-family taxonomy to shard along. So
 * this single script is simultaneously the tier's full-corpus Worker and
 * its only shard: `check_deployed_freshness.mjs` compares its `/health`
 * count against the crate's built count, and `sweep_multi_worker.mjs`
 * dispatches to it as family `rust-router`. One Cloudflare script, both
 * roles. See `tools/wasm/wasm_tier_topology.json` for the tier model.
 *
 * # Why the manifest is imported rather than inlined
 *
 * Identical to `families/pcl-ir/index.js` and
 * `families/constraint-compiler/index.js`: a hand-copied literal that
 * drifts from `tools/wasm/wasm_expected_failures_rust_router.json` makes
 * the Worker return a bare `fail` for a divergence `tools/wasm/
 * r19_compare.py` knows is expected, which that script scores as a
 * DISAGREEMENT — a red nightly whose real cause is a stale JS literal.
 *
 * That manifest is EMPTY for this crate (all 20 executable tests pass on
 * wasm32), and it is imported anyway rather than replaced with a `[]`
 * literal, because the file is where the first divergence will be recorded
 * and the import is what makes recording it a one-file change.
 *
 * # `module_sha256` (issue #945)
 *
 * `DIGEST_RUST_ROUTER` is `scripts/stage_wasm_families.sh`'s sha256 of the
 * exact bytes staged into `WASM_RUST_ROUTER`, written as a sidecar JSON
 * next to the `.wasm` file so it bundles the same way the expected-failure
 * manifest does. It answers "is this the same content", which a test count
 * alone cannot — see `worker_core.js`'s header for the full argument and
 * `tools/wasm/check_deployed_freshness.mjs` for the comparison this feeds.
 */
import WASM_RUST_ROUTER from "../../src/temper_wasm_test_runner_rust_router.wasm";
import EXPECTED_FAILURES_RUST_ROUTER from "../../../../tools/wasm/wasm_expected_failures_rust_router.json";
import DIGEST_RUST_ROUTER from "../../src/temper_wasm_test_runner_rust_router.wasm.sha256.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(
  WASM_RUST_ROUTER,
  EXPECTED_FAILURES_RUST_ROUTER,
  DIGEST_RUST_ROUTER.sha256,
);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
