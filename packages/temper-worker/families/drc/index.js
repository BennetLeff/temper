/**
 * temper-wasm-drc — single-family DRC Worker (Phase 1 U8 multi-worker).
 *
 * Imports only the DRC shard (1 test, 77 KB) and exposes the standard
 * single-module Worker API via `createWorker` from `worker_core.js`.
 */
import WASM_DRC from "../../src/temper_wasm_test_runner_drc.wasm";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_DRC);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
