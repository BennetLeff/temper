/**
 * temper-wasm-constraints — the temper-constraints tier's only Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features constraints-wasm-test-registry`,
 * which carries temper-constraints's whole wasm32 registry (29 executable
 * tests as of 2026-08-11, all passing — see
 * `packages/temper-placer/temper-constraints/src/wasm_test_registry.rs`'s
 * own header).
 *
 * 29, not the 30 that file names: `ipc::tests::host_libm_symbols_actually_
 * resolve` carries its own `#[cfg(not(target_arch = "wasm32"))]` — it
 * asserts that `dlsym()` resolves the host libm's `pow`, and
 * wasm32-unknown-unknown has no dynamic loader, so the entry is compiled
 * out rather than skipped at runtime. The same shape as
 * temper-constraint-compiler's 70/69 gap, temper-geometry's 724/722 and
 * temper-thermal's 145/143. Measured 2026-08-11 with `node tools/wasm/
 * run_wasm_tests.mjs` against the actual build: 29 registered, 29 executed,
 * 29 passed, 0 failed — and diffed (not just counted) against `cargo test
 * --no-default-features --manifest-path
 * packages/temper-placer/temper-constraints/Cargo.toml`'s 30 passing names
 * (the host_libm test included, since native x86_64 is not `wasm32`): the
 * wasm32 29 are an exact subset. 29 is therefore what `/health` reports and
 * what the freshness check must be given; handing it 30 is a staleness
 * failure, and `tools/wasm/test_check_deployed_freshness.mjs` has a case
 * pinning exactly that.
 *
 * # Why one Worker and not eight
 *
 * temper-constraints declares exactly one family
 * (`wasm-registry-constraints`) — the three surviving modules (`loss`,
 * `encoder`, `ipc`) are a flat set of pure loss/geometry/ampacity kernels
 * with no rule-family taxonomy to shard along. So this single script is
 * simultaneously the tier's full-corpus Worker and its only shard:
 * `check_deployed_freshness.mjs` compares its `/health` count against the
 * crate's built count, and `sweep_multi_worker.mjs` dispatches to it as
 * family `constraints`. One Cloudflare script, both roles. See
 * `tools/wasm/wasm_tier_topology.json` for the tier model.
 *
 * # Why the manifest is imported rather than inlined
 *
 * Identical to `families/pcl-ir/index.js` and
 * `families/constraint-compiler/index.js`: a hand-copied literal that
 * drifts from `tools/wasm/wasm_expected_failures_constraints.json` makes
 * the Worker return a bare `fail` for a divergence `tools/wasm/
 * r19_compare.py` knows is expected, which that script scores as a
 * DISAGREEMENT — a red nightly whose real cause is a stale JS literal.
 *
 * That manifest is EMPTY for this crate (all 29 executable tests pass on
 * wasm32), and it is imported anyway rather than replaced with a `[]`
 * literal, because the file is where the first divergence will be recorded
 * and the import is what makes recording it a one-file change.
 *
 * # `module_sha256` (issue #945)
 *
 * `DIGEST_CONSTRAINTS` is `scripts/stage_wasm_families.sh`'s sha256 of the
 * exact bytes staged into `WASM_CONSTRAINTS`, written as a sidecar JSON
 * next to the `.wasm` file so it bundles the same way the expected-failure
 * manifest does. It answers "is this the same content", which a test count
 * alone cannot — see `worker_core.js`'s header for the full argument and
 * `tools/wasm/check_deployed_freshness.mjs` for the comparison this feeds.
 */
import WASM_CONSTRAINTS from "../../src/temper_wasm_test_runner_constraints.wasm";
import EXPECTED_FAILURES_CONSTRAINTS from "../../../../tools/wasm/wasm_expected_failures_constraints.json";
import DIGEST_CONSTRAINTS from "../../src/temper_wasm_test_runner_constraints.wasm.sha256.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(
  WASM_CONSTRAINTS,
  EXPECTED_FAILURES_CONSTRAINTS,
  DIGEST_CONSTRAINTS.sha256,
);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
