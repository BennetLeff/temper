/**
 * temper-wasm-geometry — the temper-geometry tier's only Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features geometry-wasm-test-registry`, which
 * carries temper-geometry's whole wasm32 registry (722 tests as of 2026-08-10;
 * `packages/temper-geometry/src/wasm_test_registry.rs` registers 724 and two
 * are `#[cfg(not(target_arch = "wasm32"))]`, so they are compiled out rather
 * than skipped at runtime).
 *
 * # Why one Worker and not eight
 *
 * temper-geometry declares exactly one family (`wasm-registry-geometry`) — it
 * is a flat set of independent kernels with no rule-family taxonomy to shard
 * on. So this single script is simultaneously the tier's full-corpus Worker and
 * its only shard: `check_deployed_freshness.mjs` compares its `/health` count
 * against the crate's built count, and `sweep_multi_worker.mjs` dispatches to
 * it as family `geometry`. One Cloudflare script, both roles. See
 * `tools/wasm/wasm_tier_topology.json` for the tier model and for why
 * temper-geometry is not folded into `temper-wasm-tier`.
 *
 * # Why the manifest is imported rather than inlined
 *
 * `worker_core.js` carries temper-drc-rs's four-entry manifest as a literal, a
 * hand-maintained copy of `tools/wasm/wasm_expected_failures.json`. Repeating
 * that pattern here would mean hand-maintaining fifteen entries in two places,
 * and a drifted copy fails in the least legible way available: the Worker
 * returns a bare `fail` for a divergence that `tools/wasm/r19_compare.py` knows
 * is expected, which that script scores as a DISAGREEMENT — a red nightly whose
 * real cause is a stale JS literal. Importing the JSON the rest of the tooling
 * already reads makes the two copies one.
 */
import WASM_GEOMETRY from "../../src/temper_wasm_test_runner_geometry.wasm";
import EXPECTED_FAILURES_GEOMETRY from "../../../../tools/wasm/wasm_expected_failures_geometry.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_GEOMETRY, EXPECTED_FAILURES_GEOMETRY);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
