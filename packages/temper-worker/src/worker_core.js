/**
 * Request-handling core for the temper WASM verification tier.
 *
 * Shared between the Cloudflare Worker entry (`src/index.js`) and the local
 * Node smoke-test harness (`tools/wasm/worker_local_server.mjs`), so the
 * deployed logic and the locally-tested logic are the same code.
 *
 * The core is environment-agnostic: it receives a compiled `WebAssembly.Module`
 * (`createWorker(module)`) and never touches Node or Workers-specific globals.
 *
 * Contract (R17):
 *
 *   POST /run-test  { "index": <number> }  |  { "name": "<string>" }
 *     → { verdict, index, name, message, abi_version, ms }
 *   GET /manifest   → expected-failure manifest (bundled)
 *   GET /health     → { status: "ok", abi_version, test_count }
 *
 * Per-request instantiation model: each HTTP request instantiates a fresh
 * `WebAssembly.Instance` from the compiled module, so a panicking test that
 * traps within its own instance cannot poison the next request. The module is
 * compiled once (Cloudflare: at upload time; Node: at server start).
 */

// ---------------------------------------------------------------------------
// Constants matching the wasm-test-runner ABI

const RUN_OK = 0;
const RUN_BAD_INDEX = 1;

// ---------------------------------------------------------------------------
// Expected-failure manifest — hand-maintained, bundled with the Worker.
// Kept in sync with tools/wasm/wasm_expected_failures.json; the bidirectional
// gate in tools/wasm/run_wasm_tests.mjs fails a run when a listed test passes.

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
// Worker factory

/**
 * Build a Worker fetch handler around a compiled WebAssembly.Module.
 *
 * @param {WebAssembly.Module} wasmModule compiled once at startup
 * @returns {{ fetch: (request: Request, env: object) => Promise<Response> }}
 */
export function createWorker(wasmModule) {
  /**
   * Instantiate the WASM module and run a single test by index.
   *
   * Returns { verdict, index, name, message, abi_version, ms }.
   * On trap, the panic buffer is read from the dying instance before the
   * WebAssembly store is released.
   */
  async function runTest(index, expectedAbi) {
    const t0 = Date.now();

    let inst;
    try {
      // WebAssembly.instantiate(compiledModule, importObject) returns the Instance directly.
      inst = await WebAssembly.instantiate(wasmModule, {});
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
    if (abi !== expectedAbi) {
      return {
        verdict: "fail",
        index,
        name: null,
        message: `ABI mismatch: module has ${abi}, Worker expects ${expectedAbi}`,
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

  // -----------------------------------------------------------------------
  // Route table

  async function handleRequest(request, env) {
    const expectedAbi = parseInt((env && env.ABI_VERSION) || "1", 10);
    const url = new URL(request.url);

    // GET /health — liveness + census (fresh instantiate each time)
    if (request.method === "GET" && url.pathname === "/health") {
      try {
        const inst = await WebAssembly.instantiate(wasmModule, {});
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
          inst = await WebAssembly.instantiate(wasmModule, {});
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

      const result = await runTest(index, expectedAbi);

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

  return {
    async fetch(request, env, ctx) {
      return handleRequest(request, env);
    },
  };
}
