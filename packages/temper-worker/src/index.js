/**
 * Cloudflare Worker entry point for the temper WASM verification tier.
 *
 * The `.wasm` module is a `[wasm_modules]` binding: Cloudflare compiles it once
 * at upload time and exposes it as a `WebAssembly.Module` via this default
 * import. Per-request instantiation happens in the shared core
 * (`src/worker_core.js`), so the R17 logic is identical between this deployed
 * Worker and the local Node smoke-test harness.
 *
 * # Contract (R17)
 *
 * One test function per Worker invocation — fresh `WebAssembly.instantiate`
 * per request so a panicking test that traps cannot poison the next request.
 *
 * POST /run-test
 *   Body: { "index": <number> }  or  { "name": "<string>" }
 *   Response: { "verdict": "pass"|"fail"|"expected-fail"|"unexpected-pass"
 *               |"bad-index"|"not-found",
 *               "index": <number>, "name": "<string>",
 *               "message": "<string>" | null,
 *               "abi_version": <number>, "ms": <number> }
 *
 * GET /manifest
 *   Returns the expected-failure manifest as JSON, keyed by test name.
 *
 * GET /health
 *   Returns { "status": "ok", "abi_version": <number>, "test_count": <number> }.
 *
 * # Trap protocol
 *
 * A failing test panics → abort → `unreachable` → WebAssembly trap. The core
 * catches the trap and reads the panic buffer via `temper_panic_message_ptr/len`
 * before the WebAssembly store is torn down.
 *
 * # ABI version check
 *
 * The `ABI_VERSION` var (see wrangler.toml) is compared against the module's
 * exported `temper_wasm_abi_version()` on every request. A mismatch means the
 * Worker was deployed against an incompatible .wasm — it returns a failing
 * verdict until the deploy is corrected.
 *
 * # Import contract
 *
 * The .wasm module has zero imports (verified at build time). The core passes
 * an empty import object to `WebAssembly.instantiate`.
 */

import WASM from "./temper_wasm_test_runner.wasm";
import { createWorker } from "./worker_core.js";

const worker = createWorker(WASM);

export default {
  async fetch(request, env, ctx) {
    return worker.fetch(request, env, ctx);
  },
};
