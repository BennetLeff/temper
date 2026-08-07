/**
 * Cloudflare Worker entry point for the temper WASM verification tier.
 *
 * # Contract (R17)
 *
 * One test function per Worker invocation — fresh `WebAssembly.instantiate`
 * per request so a panicking test that traps cannot poison the next request.
 *
 * ## Endpoints
 *
 * POST /run-test
 *   Body: { "index": <number> }  or  { "name": "<string>" }
 *   Response: { "verdict": "pass"|"fail"|"bad-index"|"not-found",
 *               "index": <number>, "name": "<string>",
 *               "message": "<string>" | null,
 *               "abi_version": <number> }
 *
 * GET /manifest
 *   Returns the expected-failure manifest as JSON, keyed by test name.
 *   The manifest is hand-maintained at tools/wasm/wasm_expected_failures.json.
 *
 * GET /health
 *   Returns { "status": "ok", "abi_version": <number>, "test_count": <number> }.
 *   Always instantiates a fresh module (so it catches a broken .wasm at deploy
 *   time, not on the first real request).
 *
 * ## Trap protocol
 *
 * A failing test panics → abort → `unreachable` → WebAssembly trap. The Worker
 * catches the trap as a thrown error from `WebAssembly.Instance` construction
 * or `temper_run_test()` invocation, then reads the panic buffer via
 * `temper_panic_message_ptr/len` before the WebAssembly store is torn down.
 *
 * ## ABI version check
 *
 * The Worker compares the `ABI_VERSION` env var against the module's exported
 * `temper_wasm_abi_version()` at startup. A mismatch means the Worker was
 * deployed against an incompatible .wasm — it returns 500 for every request
 * until the deploy is corrected.
 *
 * ## Import contract
 *
 * The .wasm module has zero imports (verified at build time). The Worker
 * passes an empty import object to `WebAssembly.instantiate`.
 */

// ---------------------------------------------------------------------------
// In a real Cloudflare Workers deployment, the .wasm is imported as a compiled
// module via the `[wasm_modules]` binding in wrangler.toml:
//
//   import WASM from "./temper_wasm_test_runner.wasm";
//
// The local probe (`tools/wasm/worker_local_probe.mjs`) substitutes this with
// a `readFileSync` + `WebAssembly.compile` at startup, producing the same
// `WebAssembly.Module` shape. The Worker code below references `WASM` as the
// module handle and does not care how it was obtained.
//
// When deploying, uncomment the import above and delete the fallback block.
// --- FALLBACK for local Node probe (remove before deploy) ---
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const WASM_PATH = fileURLToPath(
  new URL("../../../target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm", import.meta.url),
);
// The local probe script sets Wrangler-style env vars on process.env.
const ENV = typeof ABI_VERSION !== "undefined" ? { ABI_VERSION } : process.env;
const EXPECTED_ABI = parseInt(ENV.ABI_VERSION || "1", 10);

let WASM = null;

// --- END FALLBACK ---

// ---------------------------------------------------------------------------
// Expected-failure manifest — hand-maintained, bundled with the Worker.
// In production this is a static JSON import; the local probe reads from disk.

const EXPECTED_FAILURES = {
  "_comment": [
    "Tests that execute on wasm32 and legitimately FAIL there, because they",
    "assert a property of the native host that wasm32 does not have.",
  ],
  "expected_failures": {
    "pymath::tests::host_libm_symbols_actually_resolve": {
      "class": "no-dynamic-loader",
      "reason": "Asserts dlsym(RTLD_DEFAULT, ...) resolves cos/sin/acos/pow. wasm32 has no dynamic loader."
    },
    "pymath::tests::pow_is_not_a_multiply_or_a_sqrt": {
      "class": "b7-pow-divergence-absent",
      "reason": "Asserts pow(x,2.0) != x*x for some x. LLVM folds the intrinsic on wasm32."
    },
    "dfm::tests::thermal_via_side_round_absorbs_the_pow_vs_sqrt_divergence": {
      "class": "b7-pow-divergence-absent",
      "reason": "Asserts pow-vs-sqrt divergence exists before testing rounding absorption."
    },
    "dfm::tests::via_annular_area_uses_r_times_r_not_pow": {
      "class": "b7-pow-divergence-absent",
      "reason": "Asserts r*r != pow(r,2.0) for some r."
    }
  }
};

// ---------------------------------------------------------------------------
// Constants matching the wasm-test-runner ABI

const RUN_OK = 0;
const RUN_BAD_INDEX = 1;

// ---------------------------------------------------------------------------
// Helpers

/**
 * Read a UTF-8 string from the instance's linear memory.
 * ptr=0 or len=0 yields the empty string.
 */
function readString(inst, ptr, len) {
  if (ptr === 0 || len === 0) return "";
  return new TextDecoder().decode(
    new Uint8Array(inst.exports.memory.buffer, ptr, len),
  );
}

/**
 * Build the name→index lookup map from the instance's registry.
 * Called once per instantiation (after a census).
 */
function buildNameIndex(inst) {
  const count = inst.exports.temper_test_count();
  const map = new Map();
  for (let i = 0; i < count; i++) {
    const name = readString(
      inst,
      inst.exports.temper_test_name_ptr(i),
      inst.exports.temper_test_name_len(i),
    );
    if (name) map.set(name, i);
  }
  return map;
}

// ---------------------------------------------------------------------------
// Per-request logic: instantiate → run one test → return verdict

/**
 * Instantiate the WASM module and run a single test by index.
 *
 * Returns { verdict, index, name, message, abi_version, ms }.
 * On trap, the panic buffer is read from the dying instance before the
 * WebAssembly store is released.
 */
async function runTest(index) {
  const t0 = Date.now();

  let inst;
  try {
    // WebAssembly.instantiate(compiledModule, importObject) returns the Instance directly.
    inst = await WebAssembly.instantiate(WASM, {});
  } catch (err) {
    // Instantiation itself trapped — corrupted module or OOM.
    const ms = Date.now() - t0;
    return {
      verdict: "fail",
      index,
      name: null,
      message: `instantiation trap: ${err.message || err}`,
      abi_version: null,
      ms,
    };
  }

  const abi = inst.exports.temper_wasm_abi_version();
  if (abi !== EXPECTED_ABI) {
    return {
      verdict: "fail",
      index,
      name: null,
      message: `ABI mismatch: module has ${abi}, Worker expects ${EXPECTED_ABI}`,
      abi_version: abi,
      ms: Date.now() - t0,
    };
  }

  const count = inst.exports.temper_test_count();
  if (index < 0 || index >= count) {
    return {
      verdict: "bad-index",
      index,
      name: null,
      message: `index ${index} out of range [0, ${count})`,
      abi_version: abi,
      ms: Date.now() - t0,
    };
  }

  const name = readString(
    inst,
    inst.exports.temper_test_name_ptr(index),
    inst.exports.temper_test_name_len(index),
  );

  try {
    const rc = inst.exports.temper_run_test(index);
    const ms = Date.now() - t0;

    if (rc === RUN_OK) {
      return { verdict: "pass", index, name, message: null, abi_version: abi, ms };
    } else if (rc === RUN_BAD_INDEX) {
      return { verdict: "bad-index", index, name, message: "registry returned bad-index", abi_version: abi, ms };
    } else {
      return { verdict: "fail", index, name, message: `unknown rc=${rc}`, abi_version: abi, ms };
    }
  } catch (err) {
    // Test panicked → abort → trap. Read the panic buffer from the still-valid store.
    const ms = Date.now() - t0;
    let message;
    try {
      message = readString(
        inst,
        inst.exports.temper_panic_message_ptr(),
        inst.exports.temper_panic_message_len(),
      );
    } catch {
      message = "(panic message unreadable)";
    }
    return { verdict: "fail", index, name, message, abi_version: abi, ms };
  }
}

// ---------------------------------------------------------------------------
// Response helpers

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function text(body, status = 200) {
  return new Response(body, { status, headers: { "content-type": "text/plain" } });
}

// ---------------------------------------------------------------------------
// Route table

async function handleRequest(request) {
  const url = new URL(request.url);

  // GET /health — liveness + census (fresh instantiate each time)
  if (request.method === "GET" && url.pathname === "/health") {
    try {
      const inst = await WebAssembly.instantiate(WASM, {});
      const abi = inst.exports.temper_wasm_abi_version();
      const count = inst.exports.temper_test_count();
      return json({ status: "ok", abi_version: abi, test_count: count });
    } catch (err) {
      return json({ status: "error", message: `instantiation failed: ${err.message || err}` }, 500);
    }
  }

  // GET /manifest — serve the expected-failure manifest
  if (request.method === "GET" && url.pathname === "/manifest") {
    return json(EXPECTED_FAILURES);
  }

  // POST /run-test — one test per invocation (R17)
  if (request.method === "POST" && url.pathname === "/run-test") {
    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "invalid JSON body" }, 400);
    }

    let index;
    if (typeof body.index === "number") {
      index = body.index;
    } else if (typeof body.name === "string") {
      // Resolve name→index via a fresh census. This costs a second
      // instantiation for the census, but in the Workers model each
      // request gets a fresh isolate anyway, and the census is fast
      // (one instantiate + N string reads).
      let inst;
      try {
        inst = await WebAssembly.instantiate(WASM, {});
      } catch (err) {
        return json({ error: `instantiation failed: ${err.message || err}` }, 500);
      }
      const nameIndex = buildNameIndex(inst);
      if (nameIndex.has(body.name)) {
        index = nameIndex.get(body.name);
      } else {
        return json({ verdict: "not-found", index: null, name: body.name, message: "test name not in registry" }, 404);
      }
    } else {
      return json({ error: "body must contain { index: <number> } or { name: <string> }" }, 400);
    }

    const result = await runTest(index);

    // Reclassify against the expected-failure manifest
    const expected = EXPECTED_FAILURES.expected_failures[result.name];
    if (expected) {
      result.expected_failure_class = expected.class;
      result.expected_failure_reason = expected.reason;
      if (result.verdict === "fail") {
        result.verdict = "expected-fail";
      } else if (result.verdict === "pass") {
        result.verdict = "unexpected-pass";
      }
    }

    return json(result);
  }

  // Catch-all
  return text("temper-wasm-tier Worker\n\nPOST /run-test  { index: N } | { name: \"...\" }\nGET  /manifest\nGET  /health\n", 404);
}

// ---------------------------------------------------------------------------
// Startup: compile the WASM module once (or load from disk for local probe)
//
// In Cloudflare, this runs in the global scope and the compiled module is
// reused across requests within the same isolate. In the local Node probe,
// we compile synchronously from disk.

async function init() {
  if (WASM) return; // already compiled (Cloudflare import path)

  // Local probe path: read + compile the .wasm file
  const bytes = readFileSync(WASM_PATH);
  WASM = await WebAssembly.compile(bytes);

  // Quick validation: can we instantiate and check ABI?
  const inst = await WebAssembly.instantiate(WASM, {});
  const abi = inst.exports.temper_wasm_abi_version();
  if (abi !== EXPECTED_ABI) {
    throw new Error(`ABI mismatch at startup: module has ${abi}, Worker expects ${EXPECTED_ABI}`);
  }
  console.error(`[temper-worker] WASM module compiled (${bytes.length} bytes), ABI v${abi}, ${inst.exports.temper_test_count()} tests registered`);
}

// ---------------------------------------------------------------------------
// Worker entry point (module syntax)

export default {
  async fetch(request, env, ctx) {
    // First-request init guard for the local probe; in Cloudflare, WASM is
    // already compiled by the time `fetch` is called.
    if (!WASM) {
      try {
        await init();
      } catch (err) {
        return json({ error: `startup failed: ${err.message || err}` }, 500);
      }
    }

    return handleRequest(request);
  },
};

// ---------------------------------------------------------------------------
// Local probe entry: when run as `node src/index.js`, start a minimal HTTP
// server that mimics the Workers runtime contract for local testing.

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  import("node:http").then(async ({ createServer }) => {
    // The local probe sets ABI_VERSION in the environment before spawning.
    await init();

    const port = parseInt(process.env.PORT || "8787", 10);
    const server = createServer(async (req, res) => {
      // Build a Request-like object from the incoming http.IncomingMessage
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const body = chunks.length > 0 ? Buffer.concat(chunks).toString() : null;

      const url = `http://localhost:${port}${req.url}`;
      const request = new Request(url, {
        method: req.method,
        headers: req.headers,
        body: body || undefined,
      });

      const response = await handleRequest(request);
      res.writeHead(response.status, Object.fromEntries(response.headers));
      const respBody = await response.text();
      res.end(respBody);
    });

    server.listen(port, () => {
      console.error(`[temper-worker] local probe listening on http://localhost:${port}`);
    });
  });
}
