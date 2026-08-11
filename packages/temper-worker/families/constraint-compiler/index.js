/**
 * temper-wasm-constraint-compiler — the temper-constraint-compiler tier's only
 * Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features constraint-compiler-wasm-test-registry`,
 * which carries temper-constraint-compiler's whole wasm32 registry (69 tests as
 * of 2026-08-11, all passing).
 *
 * 69, not the 70 `packages/temper-constraint-compiler/src/wasm_test_registry.rs`
 * names: `constraints::tests::host_libm_symbols_actually_resolve` carries its
 * own `#[cfg(not(target_arch = "wasm32"))]` in constraints/mod.rs — it asserts
 * that `dlsym()` resolves the host libm's `pow`, and wasm32-unknown-unknown has
 * no dynamic loader — so `gen_wasm_test_registry.py` copies that cfg onto the
 * registry entry and the test is compiled out rather than skipped at runtime.
 * 69 is therefore what `/health` reports and what the freshness check must be
 * given; handing it 70 is a staleness failure, and
 * tools/wasm/test_check_deployed_freshness.mjs has a case pinning exactly that.
 * temper-geometry has the same gap at 724 registered / 722 executable and
 * temper-thermal at 145 / 143.
 *
 * # Why one Worker and not eight
 *
 * temper-constraint-compiler declares exactly one family
 * (`wasm-registry-constraint-compiler`) — the lowering tiers are a flat
 * pipeline with no taxonomy to shard along. So this single script is
 * simultaneously the tier's full-corpus Worker and its only shard:
 * `check_deployed_freshness.mjs` compares its `/health` count against the
 * crate's built count, and `sweep_multi_worker.mjs` dispatches to it as family
 * `constraint-compiler`. One Cloudflare script, both roles. See
 * `tools/wasm/wasm_tier_topology.json` for the tier model.
 *
 * # Why the manifest is imported rather than inlined
 *
 * Identical to `families/geometry/index.js` and `families/thermal/index.js`: a
 * hand-copied literal that drifts from
 * `tools/wasm/wasm_expected_failures_constraint_compiler.json` makes the Worker
 * return a bare `fail` for a divergence `tools/wasm/r19_compare.py` knows is
 * expected, which that script scores as a DISAGREEMENT — a red nightly whose
 * real cause is a stale JS literal.
 *
 * That manifest is EMPTY for this crate (all 69 executable tests pass on
 * wasm32), and it is imported anyway rather than replaced with a `[]` literal,
 * because the file is where the first divergence will be recorded and the
 * import is what makes recording it a one-file change.
 *
 * # `module_sha256` (issue #945)
 *
 * `DIGEST_CONSTRAINT_COMPILER` is `scripts/stage_wasm_families.sh`'s sha256 of
 * the exact bytes staged into `WASM_CONSTRAINT_COMPILER`, written as a
 * sidecar JSON next to the `.wasm` file so it bundles the same way the
 * expected-failure manifest does. It answers "is this the same content",
 * which a test count alone cannot — see `worker_core.js`'s header for the
 * full argument and `tools/wasm/check_deployed_freshness.mjs` for the
 * comparison this feeds.
 */
import WASM_CONSTRAINT_COMPILER from "../../src/temper_wasm_test_runner_constraint_compiler.wasm";
import EXPECTED_FAILURES_CONSTRAINT_COMPILER from "../../../../tools/wasm/wasm_expected_failures_constraint_compiler.json";
import DIGEST_CONSTRAINT_COMPILER from "../../src/temper_wasm_test_runner_constraint_compiler.wasm.sha256.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(
  WASM_CONSTRAINT_COMPILER,
  EXPECTED_FAILURES_CONSTRAINT_COMPILER,
  DIGEST_CONSTRAINT_COMPILER.sha256,
);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
