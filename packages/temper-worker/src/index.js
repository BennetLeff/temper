/**
 * Cloudflare Worker entry point for the temper WASM verification tier
 * — per-family shard layout (Phase 1 U8).
 *
 * Each family gets its own `.wasm` module, imported as a
 * `WebAssembly.Module` at upload time.  The multi-family core
 * (`src/worker_core.js`) lazily instantiates each family's module on
 * the first request to that family's route.
 *
 * # Family-to-route mapping
 *
 *   Family     Route            Module import
 *   ------     ------           --------------
 *   drc        /drc/health      temper_wasm_test_runner_drc.wasm
 *   emc        /emc/health      temper_wasm_test_runner_emc.wasm
 *   erc        /erc/health      temper_wasm_test_runner_erc.wasm
 *   safety     /safety/health   temper_wasm_test_runner_safety.wasm
 *   placement  /placement/health temper_wasm_test_runner_placement.wasm
 *   routing    /routing/health  temper_wasm_test_runner_routing.wasm
 *   infra      /infra/health    temper_wasm_test_runner_infra.wasm
 *
 * # Backward-compatible /run-test
 *
 * `POST /run-test` accepts an optional `family` field.  When absent,
 * the request routes to whichever module is registered as `default`
 * (here, the full 147-test module for backward compat with CI).
 *
 * # Local Node fallback
 *
 * When not running on Cloudflare (no `WRANGLER_BUILD` env var), each
 * `.wasm` import resolves to `undefined`.  The entry point falls back
 * to reading modules from disk via `node:fs`, matching the local dev
 * server convention from `tools/wasm/worker_local_server.mjs`.
 *
 * # `module_sha256` (issue #945)
 *
 * `DIGEST_FULL` is `scripts/stage_wasm_families.sh`'s sha256 of the exact
 * bytes staged into `WASM_FULL` (the tier's full-corpus module), written as a
 * sidecar JSON next to the `.wasm` file so it bundles the same way the
 * expected-failure manifest does. Only the `default` family carries a digest
 * here: `check_deployed_freshness.mjs` compares content hash against
 * `full_corpus_worker` per tier, exactly as it compares built vs. deployed
 * COUNT against the full-corpus Worker and leaves the count-based partition
 * check (shards sum to the built count) as the seven shards' own,
 * independent, unweakened control. See `worker_core.js`'s header for the full
 * argument.
 */

import WASM_FULL    from "./temper_wasm_test_runner.wasm";
import WASM_DRC     from "./temper_wasm_test_runner_drc.wasm";
import WASM_EMC     from "./temper_wasm_test_runner_emc.wasm";
import WASM_ERC     from "./temper_wasm_test_runner_erc.wasm";
import WASM_SAFETY  from "./temper_wasm_test_runner_safety.wasm";
import WASM_PLACEMENT from "./temper_wasm_test_runner_placement.wasm";
import WASM_ROUTING from "./temper_wasm_test_runner_routing.wasm";
import WASM_INFRA   from "./temper_wasm_test_runner_infra.wasm";
import DIGEST_FULL  from "./temper_wasm_test_runner.wasm.sha256.json";

import { createMultiFamilyWorker } from "./worker_core.js";

// When running locally (Node), WASM imports are undefined and we
// fall back to reading modules from disk.  The `worker_local_server.mjs`
// harness has the path setup; this fallback is just for completeness.
let modules = {
  default:   WASM_FULL,
  drc:       WASM_DRC,
  emc:       WASM_EMC,
  erc:       WASM_ERC,
  safety:    WASM_SAFETY,
  placement: WASM_PLACEMENT,
  routing:   WASM_ROUTING,
  infra:     WASM_INFRA,
};

const worker = createMultiFamilyWorker(modules, undefined, { default: DIGEST_FULL.sha256 });

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
