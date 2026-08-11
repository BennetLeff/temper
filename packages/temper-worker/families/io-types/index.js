/**
 * temper-wasm-io-types — the temper-io-types tier's only Worker.
 *
 * Imports the module built from
 * `temper-wasm-test-runner --features io-types-wasm-test-registry`, which
 * carries temper-io-types's whole wasm32 registry (144 tests as of
 * 2026-08-11, all 144 executable and all 144 passing).
 *
 * 144 is both the registered and the executable count for this crate — see
 * `tools/wasm/wasm_expected_failures_io_types.json`'s own `_comment`: none of
 * the registered modules carries its own `cfg`, unlike temper-geometry
 * (724/722), temper-thermal (145/143), temper-constraint-compiler (70/69) or
 * temper-quality-oracle (126/125). The freshness check is given 144 anyway
 * rather than assuming registered == executable, because that assumption is
 * exactly the trap this tier has hit three times before this crate joined it.
 *
 * # Why one Worker and not eight
 *
 * temper-io-types declares exactly one family (`wasm-registry-io-types`) —
 * what survives `--no-default-features` is a flat set of KiCad/DSN
 * serialisers, footprint and S-expression parsers, provenance hashing, the
 * DAG expression parser and the placer CONTRACT kernels (Rect, netclass,
 * manufacturing, placement DRC, adjacency), with no rule-family taxonomy to
 * shard along. So this single script is simultaneously the tier's
 * full-corpus Worker and its only shard: `check_deployed_freshness.mjs`
 * compares its `/health` count against the crate's built count, and
 * `sweep_multi_worker.mjs` dispatches to it as family `io-types`. One
 * Cloudflare script, both roles. See `tools/wasm/wasm_tier_topology.json` for
 * the tier model.
 *
 * # Why the manifest is imported rather than inlined
 *
 * Identical to `families/thermal/index.js` and
 * `families/constraint-compiler/index.js`: a hand-copied literal that drifts
 * from `tools/wasm/wasm_expected_failures_io_types.json` makes the Worker
 * return a bare `fail` for a divergence `tools/wasm/r19_compare.py` knows is
 * expected, which that script scores as a DISAGREEMENT — a red nightly whose
 * real cause is a stale JS literal.
 *
 * That manifest is EMPTY for this crate (all 144 tests pass on wasm32), and
 * it is imported anyway rather than replaced with a `[]` literal, because the
 * file is where the first divergence will be recorded and the import is what
 * makes recording it a one-file change.
 *
 * # `module_sha256` (issue #945)
 *
 * `DIGEST_IO_TYPES` is `scripts/stage_wasm_families.sh`'s sha256 of the exact
 * bytes staged into `WASM_IO_TYPES`, written as a sidecar JSON next to the
 * `.wasm` file so it bundles the same way the expected-failure manifest does.
 * It answers "is this the same content", which a test count alone cannot —
 * see `worker_core.js`'s header for the full argument and
 * `tools/wasm/check_deployed_freshness.mjs` for the comparison this feeds.
 */
import WASM_IO_TYPES from "../../src/temper_wasm_test_runner_io_types.wasm";
import EXPECTED_FAILURES_IO_TYPES from "../../../../tools/wasm/wasm_expected_failures_io_types.json";
import DIGEST_IO_TYPES from "../../src/temper_wasm_test_runner_io_types.wasm.sha256.json";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_IO_TYPES, EXPECTED_FAILURES_IO_TYPES, DIGEST_IO_TYPES.sha256);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
