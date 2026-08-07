/**
 * temper-wasm-routing — single-family Routing Worker (Phase 1 U8 multi-worker).
 */
import WASM_ROUTING from "../../src/temper_wasm_test_runner_routing.wasm";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_ROUTING);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
