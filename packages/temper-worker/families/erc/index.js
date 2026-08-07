/**
 * temper-wasm-erc — single-family ERC Worker (Phase 1 U8 multi-worker).
 */
import WASM_ERC from "../../src/temper_wasm_test_runner_erc.wasm";
import { createWorker } from "../../src/worker_core.js";

const worker = createWorker(WASM_ERC);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
