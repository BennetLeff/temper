/**
 * temper-wasm-emc — single-family EMC Worker (Phase 1 U8 multi-worker).
 */
import WASM_EMC from "../../src/temper_wasm_test_runner_emc.wasm";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_EMC);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
