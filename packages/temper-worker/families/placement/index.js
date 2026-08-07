/**
 * temper-wasm-placement — single-family Placement Worker (Phase 1 U8 multi-worker).
 */
import WASM_PLACEMENT from "../../src/temper_wasm_test_runner_placement.wasm";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_PLACEMENT);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
