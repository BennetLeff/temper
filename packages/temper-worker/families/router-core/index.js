/**
 * temper-wasm-router-core — the temper-rust-router-core tier's only Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features router-core-wasm-test-registry`, which
 * carries temper-rust-router-core's whole wasm32 registry: 111 registered, 111
 * executable, 111 passing as of 2026-08-11.
 *
 * # 111 registered and 111 executable, which is not the tier's usual shape
 *
 * temper-geometry registers 724 and executes 722, temper-thermal 145/143 and
 * temper-constraint-compiler 70/69, in each case because some registry entry
 * carries its own `cfg` and is compiled out of the wasm32 module rather than
 * skipped at runtime. This crate's registry has no such entry, so `/health`
 * reports the same 111 the registry names. That is a fact about today's
 * registry, not a licence to assume the two are interchangeable: the number the
 * freshness check must be given is always the EXECUTABLE one
 * (`summary.registered` from run_wasm_tests.mjs, which is `temper_test_count()`
 * of the built module).
 *
 * # Why the manifest is imported rather than inlined, and why it is empty
 *
 * `tools/wasm/wasm_expected_failures_router_core.json` currently lists NO
 * divergences, and that is a measurement rather than an omission. Until #946
 * it listed 23, all one class (`no-clock`) and one root cause in PRODUCTION
 * code: `combinator::rewrite::rewrite()` evaluated `Instant::now()`
 * unconditionally, and `wasm32-unknown-unknown` has no clock. #947 made that
 * timestamp lazy; all 23 turned into passes and were deleted from the manifest
 * in the same PR. This Worker is being introduced on the far side of that fix,
 * so it carries a fully green corpus.
 *
 * The manifest is still IMPORTED rather than replaced with a `[]` literal, for
 * the reason `families/geometry/index.js` and `families/thermal/index.js` give:
 * a hand-copied literal that drifts from the JSON makes the Worker return a
 * bare `fail` for a divergence `tools/wasm/r19_compare.py` knows is expected,
 * which that script scores as a DISAGREEMENT — a red nightly whose real cause
 * is a stale JS literal. This crate is the sharpest illustration available:
 * had this Worker been written a day earlier it would have carried 23 literals,
 * and #947 would have turned every one of them into a spurious disagreement
 * from a file nobody thought to edit. Importing the JSON the rest of the
 * tooling already reads makes any future reconciliation a one-file change.
 *
 * The emptiness is also enforced in both directions rather than assumed:
 * `run_wasm_tests.mjs` exits non-zero on an UNEXPECTED PASS as well as on a
 * plain fail, so a listed test that starts passing and an unlisted test that
 * starts failing are both loud. An empty manifest is therefore a claim that
 * every registered test really runs on wasm32.
 *
 * # Why one Worker and not eight
 *
 * temper-rust-router-core declares exactly one family
 * (`wasm-registry-router-core`) — the solver-free core is a flat set of graph
 * and rewrite kernels with no rule-family taxonomy to shard on. So this single
 * script is simultaneously the tier's full-corpus Worker and its only shard:
 * `check_deployed_freshness.mjs` compares its `/health` count against the
 * crate's built count, and `sweep_multi_worker.mjs` dispatches to it as family
 * `router-core`. One Cloudflare script, both roles. See
 * `tools/wasm/wasm_tier_topology.json` for the tier model.
 */
import WASM_ROUTER_CORE from "../../src/temper_wasm_test_runner_router_core.wasm";
import EXPECTED_FAILURES_ROUTER_CORE from "../../../../tools/wasm/wasm_expected_failures_router_core.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_ROUTER_CORE, EXPECTED_FAILURES_ROUTER_CORE);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
