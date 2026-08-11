/**
 * temper-wasm-orchestration — the temper-orchestration tier's only Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features orchestration-wasm-test-registry`,
 * which carries temper-orchestration's whole wasm32 registry (83 executable
 * tests as of 2026-08-11, all passing — see
 * `packages/temper-orchestration/src/wasm_test_registry.rs`'s own header).
 *
 * 83, not the 91 that file names: TWO exclusion classes stack for this
 * crate, more than any other single-family tier.
 *   * `host_math::tests::host_libm_symbols_actually_resolve` carries its own
 *     `#[cfg(not(target_arch = "wasm32"))]` — the same dlsym/no-dynamic-
 *     loader fact temper-constraint-compiler (70/69), temper-geometry,
 *     temper-thermal and temper-quality-oracle already catalogue (1 test).
 *   * Seven individual `#[test]` entries, scattered across three otherwise-
 *     eligible modules (`phased_component_assignment_validator_stage` x2,
 *     `feasibility` x3, `pipeline_state` x2), carry their own
 *     `#[cfg(feature = "python")]` and are absent from BOTH the native
 *     `--no-default-features` build and this wasm32 build identically —
 *     the same `python-gated` class every whole-module exclusion on this
 *     tier already uses, just applied at test-function granularity (7
 *     tests).
 * 91 - 1 - 7 = 83. Neither class produces an entry in
 * `tools/wasm/wasm_expected_failures_orchestration.json` (empty): a
 * `#[cfg]`-excluded test never runs anywhere in the relevant build, so it
 * can neither pass nor fail and an entry would be an orphan exclusion.
 * Measured 2026-08-11 with `node tools/wasm/run_wasm_tests.mjs` against the
 * actual build: 83 registered, 83 executed, 83 passed, 0 failed — and
 * diffed (not just counted) against `cargo test --no-default-features
 * --manifest-path packages/temper-orchestration/Cargo.toml --lib`'s 84
 * passing names: the wasm32 83 are an exact subset, the 84th being
 * `host_libm_symbols_actually_resolve`. See
 * `tools/wasm/wasm_tier_topology.json`'s own header for why
 * `native_test_args` for this crate alone carries a fourth element, `--lib`
 * (its `tests/*.rs` integration files all reference pyo3 directly and fail
 * to compile under `--no-default-features` — the `integration-test-target`
 * exclusion class, at crate scope).
 *
 * # Why one Worker and not eight
 *
 * temper-orchestration declares exactly one family
 * (`wasm-registry-orchestration`) — what survives `--no-default-features`
 * is a flat set of pure kernels (timing, feasibility, copper-length, the
 * `Stage`/`PipelineRunner` scaffolding) with no rule-family taxonomy to
 * shard along. So this single script is simultaneously the tier's
 * full-corpus Worker and its only shard: `check_deployed_freshness.mjs`
 * compares its `/health` count against the crate's built count, and
 * `sweep_multi_worker.mjs` dispatches to it as family `orchestration`. One
 * Cloudflare script, both roles. See `tools/wasm/wasm_tier_topology.json`
 * for the tier model.
 *
 * # Why the manifest is imported rather than inlined
 *
 * Identical to `families/pcl-ir/index.js` and
 * `families/constraint-compiler/index.js`: a hand-copied literal that
 * drifts from `tools/wasm/wasm_expected_failures_orchestration.json` makes
 * the Worker return a bare `fail` for a divergence `tools/wasm/
 * r19_compare.py` knows is expected, which that script scores as a
 * DISAGREEMENT — a red nightly whose real cause is a stale JS literal.
 *
 * That manifest is EMPTY for this crate (all 83 executable tests pass on
 * wasm32), and it is imported anyway rather than replaced with a `[]`
 * literal, because the file is where the first divergence will be recorded
 * and the import is what makes recording it a one-file change.
 *
 * # `module_sha256` (issue #945)
 *
 * `DIGEST_ORCHESTRATION` is `scripts/stage_wasm_families.sh`'s sha256 of
 * the exact bytes staged into `WASM_ORCHESTRATION`, written as a sidecar
 * JSON next to the `.wasm` file so it bundles the same way the
 * expected-failure manifest does. It answers "is this the same content",
 * which a test count alone cannot — see `worker_core.js`'s header for the
 * full argument and `tools/wasm/check_deployed_freshness.mjs` for the
 * comparison this feeds.
 */
import WASM_ORCHESTRATION from "../../src/temper_wasm_test_runner_orchestration.wasm";
import EXPECTED_FAILURES_ORCHESTRATION from "../../../../tools/wasm/wasm_expected_failures_orchestration.json";
import DIGEST_ORCHESTRATION from "../../src/temper_wasm_test_runner_orchestration.wasm.sha256.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(
  WASM_ORCHESTRATION,
  EXPECTED_FAILURES_ORCHESTRATION,
  DIGEST_ORCHESTRATION.sha256,
);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
