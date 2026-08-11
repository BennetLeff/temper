/**
 * temper-wasm-quality-oracle — the temper-quality-oracle tier's only Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features quality-oracle-wasm-test-registry`,
 * which carries temper-quality-oracle's whole wasm32 registry (126 tests as
 * of 2026-08-11, 125 of them executable).
 *
 * 125, not the 126 `packages/temper-quality-oracle/src/wasm_test_registry.rs`
 * names: `placement_metrics::tests::py_pow_resolves_to_host_libm_not_sqrt`
 * carries its own `#[cfg(not(target_arch = "wasm32"))]` in placement_metrics.rs
 * — it is the anti-vacuity guard proving CPython's `dlsym`-resolved `pow`
 * still diverges from `x * x`, and wasm32-unknown-unknown has no dynamic
 * loader — so `gen_wasm_test_registry.py` copies that cfg onto the registry
 * entry and the test is compiled out rather than skipped at runtime. 125 is
 * therefore what `/health` reports and what the freshness check must be
 * given; handing it 126 is a staleness failure, and
 * tools/wasm/test_check_deployed_freshness.mjs has a case pinning exactly
 * that. temper-geometry has the same gap at 724 registered / 722 executable,
 * temper-thermal at 145 / 143 and temper-constraint-compiler at 70 / 69.
 *
 * # Why one Worker and not eight
 *
 * temper-quality-oracle declares exactly one family
 * (`wasm-registry-quality-oracle`) — the six-layer quality pipeline (net
 * classification, constraint derivation, config assembly, threshold
 * evaluation, the pass/fail oracle, and the placement / aesthetic / routing /
 * validation scorers) is a flat set of pure scoring kernels with no
 * rule-family taxonomy to shard along. So this single script is
 * simultaneously the tier's full-corpus Worker and its only shard:
 * `check_deployed_freshness.mjs` compares its `/health` count against the
 * crate's built count, and `sweep_multi_worker.mjs` dispatches to it as
 * family `quality-oracle`. One Cloudflare script, both roles. See
 * `tools/wasm/wasm_tier_topology.json` for the tier model.
 *
 * # Why the manifest is imported rather than inlined
 *
 * Identical to `families/thermal/index.js` and
 * `families/constraint-compiler/index.js`: a hand-copied literal that drifts
 * from `tools/wasm/wasm_expected_failures_quality_oracle.json` makes the
 * Worker return a bare `fail` for a divergence `tools/wasm/r19_compare.py`
 * knows is expected, which that script scores as a DISAGREEMENT — a red
 * nightly whose real cause is a stale JS literal.
 *
 * That manifest is EMPTY for this crate (all 125 executable tests pass on
 * wasm32 — see its own `_comment` for why none of the established divergence
 * classes has anything to attach to), and it is imported anyway rather than
 * replaced with a `[]` literal, because the file is where the first
 * divergence will be recorded and the import is what makes recording it a
 * one-file change.
 *
 * # `module_sha256` (issue #945)
 *
 * `DIGEST_QUALITY_ORACLE` is `scripts/stage_wasm_families.sh`'s sha256 of the
 * exact bytes staged into `WASM_QUALITY_ORACLE`, written as a sidecar JSON
 * next to the `.wasm` file so it bundles the same way the expected-failure
 * manifest does. It answers "is this the same content", which a test count
 * alone cannot — see `worker_core.js`'s header for the full argument and
 * `tools/wasm/check_deployed_freshness.mjs` for the comparison this feeds.
 */
import WASM_QUALITY_ORACLE from "../../src/temper_wasm_test_runner_quality_oracle.wasm";
import EXPECTED_FAILURES_QUALITY_ORACLE from "../../../../tools/wasm/wasm_expected_failures_quality_oracle.json";
import DIGEST_QUALITY_ORACLE from "../../src/temper_wasm_test_runner_quality_oracle.wasm.sha256.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(
  WASM_QUALITY_ORACLE,
  EXPECTED_FAILURES_QUALITY_ORACLE,
  DIGEST_QUALITY_ORACLE.sha256,
);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
