/**
 * temper-wasm-infra — single-family Infra Worker (Phase 1 U8 multi-worker).
 */
import WASM_INFRA from "../../src/temper_wasm_test_runner_infra.wasm";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_INFRA);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
