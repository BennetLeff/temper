/**
 * temper-wasm-pcl-ir — the temper-pcl-ir tier's only Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features pcl-ir-wasm-test-registry`, which
 * carries temper-pcl-ir's whole wasm32 registry (2 tests, both executable,
 * both passing — see `packages/temper-pcl-ir/src/wasm_test_registry.rs`'s own
 * header: "No exclusion classes apply here").
 *
 * 2 is both the registered and the executable count for this crate, the same
 * shape as temper-design-bundle's 24/24 and temper-io-types's 144/144 —
 * unlike temper-geometry (724/722 at #940, 2234/2232 after the #961 property
 * campaign), temper-thermal (145/143), temper-constraint-compiler (70/69) or
 * temper-quality-oracle (126/125), no module here carries its own
 * `#[cfg(not(target_arch = "wasm32"))]`. The freshness check is given 2
 * anyway rather than assuming registered == executable, because that
 * assumption is exactly the trap this tier has hit four times before this
 * crate joined it.
 *
 * # Why one Worker and not eight
 *
 * temper-pcl-ir declares exactly one family (`wasm-registry-pcl-ir`) — this
 * crate is a flat typed data model (the shared PCL IR) with no rule-family
 * taxonomy to shard along. So this single script is simultaneously the
 * tier's full-corpus Worker and its only shard: `check_deployed_freshness.mjs`
 * compares its `/health` count against the crate's built count, and
 * `sweep_multi_worker.mjs` dispatches to it as family `pcl-ir`. One
 * Cloudflare script, both roles. See `tools/wasm/wasm_tier_topology.json` for
 * the tier model.
 *
 * # Why the manifest is imported rather than inlined
 *
 * Identical to `families/constraint-compiler/index.js` and
 * `families/io-types/index.js`: a hand-copied literal that drifts from
 * `tools/wasm/wasm_expected_failures_pcl_ir.json` makes the Worker return a
 * bare `fail` for a divergence `tools/wasm/r19_compare.py` knows is expected,
 * which that script scores as a DISAGREEMENT — a red nightly whose real cause
 * is a stale JS literal.
 *
 * That manifest is EMPTY for this crate (both executable tests pass on
 * wasm32), and it is imported anyway rather than replaced with a `[]`
 * literal, because the file is where the first divergence will be recorded
 * and the import is what makes recording it a one-file change.
 *
 * # `module_sha256` (issue #945)
 *
 * `DIGEST_PCL_IR` is `scripts/stage_wasm_families.sh`'s sha256 of the exact
 * bytes staged into `WASM_PCL_IR`, written as a sidecar JSON next to the
 * `.wasm` file so it bundles the same way the expected-failure manifest does.
 * It answers "is this the same content", which a test count alone cannot —
 * see `worker_core.js`'s header for the full argument and
 * `tools/wasm/check_deployed_freshness.mjs` for the comparison this feeds.
 */
import WASM_PCL_IR from "../../src/temper_wasm_test_runner_pcl_ir.wasm";
import EXPECTED_FAILURES_PCL_IR from "../../../../tools/wasm/wasm_expected_failures_pcl_ir.json";
import DIGEST_PCL_IR from "../../src/temper_wasm_test_runner_pcl_ir.wasm.sha256.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_PCL_IR, EXPECTED_FAILURES_PCL_IR, DIGEST_PCL_IR.sha256);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
