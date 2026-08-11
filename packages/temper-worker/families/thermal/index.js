/**
 * temper-wasm-thermal — the temper-thermal tier's only Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features thermal-wasm-test-registry`, which
 * carries temper-thermal's whole wasm32 registry (143 tests as of 2026-08-10).
 *
 * 143, not the 145 `packages/temper-thermal/src/wasm_test_registry.rs` names:
 * two entries carry their own `cfg` and are compiled out of this module rather
 * than skipped at runtime —
 * `device_power::tests::host_libm_symbols_actually_resolve`
 * (`#[cfg(not(target_arch = "wasm32"))]`) and
 * `hostmath::tests::dlsym_resolves_on_macos` (`#[cfg(target_os = "macos")]`).
 * 143 is therefore what `/health` reports and what the freshness check must be
 * given; handing it 145 is a staleness failure, and
 * tools/wasm/test_check_deployed_freshness.mjs has a case pinning exactly that.
 * temper-geometry has the same gap at 724 registered / 722 executable.
 *
 * # Why one Worker and not eight
 *
 * temper-thermal declares exactly one family (`wasm-registry-thermal`) — it is
 * a flat set of physics kernels with no rule-family taxonomy to shard on. So
 * this single script is simultaneously the tier's full-corpus Worker and its
 * only shard: `check_deployed_freshness.mjs` compares its `/health` count
 * against the crate's built count, and `sweep_multi_worker.mjs` dispatches to
 * it as family `thermal`. One Cloudflare script, both roles. See
 * `tools/wasm/wasm_tier_topology.json` for the tier model and for why
 * temper-thermal is not folded into `temper-wasm-tier`.
 *
 * # Why the manifest is imported rather than inlined
 *
 * Identical to `families/geometry/index.js`, and for the identical reason: a
 * hand-copied literal that drifts from `tools/wasm/wasm_expected_failures_
 * thermal.json` makes the Worker return a bare `fail` for a divergence
 * `tools/wasm/r19_compare.py` knows is expected, which that script scores as a
 * DISAGREEMENT — a red nightly whose real cause is a stale JS literal. All four
 * of this crate's entries are `b7-pow-divergence-absent`, i.e. tests whose
 * whole job is to prove a libm divergence is still there; misclassifying them
 * is exactly the failure that would hide a genuine change to hostmath.rs.
 */
import WASM_THERMAL from "../../src/temper_wasm_test_runner_thermal.wasm";
import EXPECTED_FAILURES_THERMAL from "../../../../tools/wasm/wasm_expected_failures_thermal.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_THERMAL, EXPECTED_FAILURES_THERMAL);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
