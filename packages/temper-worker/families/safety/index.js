/**
 * temper-wasm-safety — single-family Safety Worker (Phase 1 U8 multi-worker).
 */
import WASM_SAFETY from "../../src/temper_wasm_test_runner_safety.wasm";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_SAFETY);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
