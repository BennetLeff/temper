/**
 * temper-wasm-design-bundle — the temper-design-bundle tier's only Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features design-bundle-wasm-test-registry`, which
 * carries temper-design-bundle's whole wasm32 registry (24 tests as of
 * 2026-08-11).
 *
 * 24 registered and 24 executable — this is the one tier on which those two
 * numbers coincide. temper-geometry registers 724 and executes 722,
 * temper-thermal registers 145 and executes 143, and
 * temper-constraint-compiler registers 70 and executes 69, in each case because
 * some registry entry carries its own `cfg` and is compiled out of the wasm32
 * module rather than skipped at runtime. `packages/temper-design-bundle/src/
 * wasm_test_registry.rs` has no such entry, so `/health` reports the same 24
 * the registry names. That is a fact about today's registry, not a licence to
 * assume the two are interchangeable: the number the freshness check must be
 * given is always the EXECUTABLE one (`summary.registered` from
 * run_wasm_tests.mjs, which is `temper_test_count()` of the built module).
 *
 * # Why one Worker and not eight
 *
 * temper-design-bundle declares exactly one family
 * (`wasm-registry-design-bundle`) — what survives `--no-default-features` is a
 * flat set of s-expression/netlist parsers, board identity and PCL constraint
 * typing, with no rule-family taxonomy to shard on. So this single script is
 * simultaneously the tier's full-corpus Worker and its only shard:
 * `check_deployed_freshness.mjs` compares its `/health` count against the
 * crate's built count, and `sweep_multi_worker.mjs` dispatches to it as family
 * `design-bundle`. One Cloudflare script, both roles. See
 * `tools/wasm/wasm_tier_topology.json` for the tier model and for why this
 * crate is not folded into `temper-wasm-tier`.
 *
 * # Why the manifest is imported rather than inlined
 *
 * Identical to `families/geometry/index.js` and `families/thermal/index.js`,
 * and for the identical reason: a hand-copied literal that drifts from
 * `tools/wasm/wasm_expected_failures_design_bundle.json` makes the Worker
 * return a bare `fail` for a divergence `tools/wasm/r19_compare.py` knows is
 * expected, which that script scores as a DISAGREEMENT — a red nightly whose
 * real cause is a stale JS literal.
 *
 * That manifest is EMPTY for this crate (all 24 tests pass on wasm32), and it
 * is imported anyway rather than replaced with a `[]` literal, because the file
 * is where the first divergence will be recorded and the import is what makes
 * recording it a one-file change.
 */
import WASM_DESIGN_BUNDLE from "../../src/temper_wasm_test_runner_design_bundle.wasm";
import EXPECTED_FAILURES_DESIGN_BUNDLE from "../../../../tools/wasm/wasm_expected_failures_design_bundle.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_DESIGN_BUNDLE, EXPECTED_FAILURES_DESIGN_BUNDLE);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
