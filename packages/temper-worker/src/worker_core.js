/**
 * Request-handling core for the temper WASM verification tier.
 *
 * Shared between the Cloudflare Worker entry (`src/index.js`) and the local
 * Node smoke-test harness, so the deployed logic and the locally-tested
 * logic are the same code.
 *
 * The core is environment-agnostic: it receives compiled `WebAssembly.Module`
 * objects (`createWorker(module)` or `createMultiFamilyWorker(families)`)
 * and never touches Node or Workers-specific globals.
 *
 * ## Per-family sharding (Phase 1 U8)
 *
 * `createMultiFamilyWorker` accepts a map of family-name → compiled module.
 * Each family route (`/drc`, `/emc`, …) compiles+instantiates its module
 * lazily on the first request and caches the instance for subsequent
 * requests.  `POST /run-test` accepts `{ family, index }` to select a
 * family; the legacy `{ index }` or `{ name }` routes to a default module
 * (the full 147-test registry or whichever module is provided as `default`).
 *
 * Contract (R17):
 *
 *   POST /run-test  { "family": "<family>", "index": <number> }
 *                |  { "family": "<family>", "name": "<string>" }
 *                |  { "index": <number> }  |  { "name": "<string>" }
 *     → { verdict, index, name, message, abi_version, ms, family }
 *   GET  /manifest   → expected-failure manifest (bundled)
 *   GET  /health     → { status: "ok", abi_version, test_count, module_sha256? }
 *   GET  /families   → { families: { <name>: { abi_version, test_count, module_sha256? } } }
 *   GET  /<family>/health  → per-family health
 *
 * Per-request instantiation model: each HTTP request instantiates a fresh
 * `WebAssembly.Instance` from the compiled module, so a panicking test that
 * traps within its own instance cannot poison the next request. The module is
 * compiled once (Cloudflare: at upload time; Node: at server start).
 *
 * ## `module_sha256` (issue #945)
 *
 * `test_count` answers "how many tests does the deployed module carry", which
 * is silent about a change that edits or fixes a test's BODY without moving
 * the count -- PR #941 (a clock-bug fix) is the real incident: 7 tests moved
 * from trapping to passing on wasm32, the registered count stayed 722 both
 * before and after, and the count-based freshness check
 * (tools/wasm/check_deployed_freshness.mjs) reported the stale pre-#941
 * module "fresh" for four commits. `module_sha256`, when the caller supplies
 * one, is the sha256 of the exact `.wasm` bytes `scripts/stage_wasm_families.sh`
 * staged for this Worker (computed there, into a `<module>.sha256.json`
 * sidecar imported alongside the module -- see families/thermal/index.js for
 * the pattern). Two builds with the same test COUNT but different BEHAVIOUR
 * produce different bytes and therefore different digests, which is exactly
 * the case a count comparison cannot see. This is additive: `test_count`
 * keeps its exact prior meaning and is still what the count/partition checks
 * compare, because it produces a far more actionable message when it fires
 * (it names how many tests, not just that the bytes differ) -- see
 * check_deployed_freshness.mjs's header for why both are kept.
 */

// ---------------------------------------------------------------------------
// Constants matching the wasm-test-runner ABI

const RUN_OK = 0;
const RUN_BAD_INDEX = 1;

// ---------------------------------------------------------------------------
// Expected-failure manifest — hand-maintained, bundled with the Worker.
// Kept in sync with tools/wasm/wasm_expected_failures.json; the bidirectional
// gate in tools/wasm/run_wasm_tests.mjs fails a run when a listed test passes.
//
// This one covers temper-drc-rs, and it is the DEFAULT rather than the only
// manifest. A Worker carrying a different crate must pass its own — see
// `createWorker`'s second parameter and families/geometry/index.js. Applying
// this manifest to another crate's module would be worse than applying none:
// every entry would be an orphan (naming no registered test) and every genuine
// divergence in that crate would come back as a bare `fail`, which
// tools/wasm/r19_compare.py scores as a DISAGREEMENT against the crate's own
// manifest — a red run whose cause is two files away from the message.

const DRC_EXPECTED_FAILURES = {
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
// Single-module worker (backward-compatible factory)

/**
 * Build a Worker fetch handler around a single compiled WebAssembly.Module.
 * This is the original R17 single-module model, kept for backward compat
 * with the CI run_wasm_tests.mjs flow and for the local Node smoke test.
 *
 * @param {WebAssembly.Module} wasmModule compiled once at startup
 * @param {object} [expectedFailures] the crate's expected-failure manifest, in
 *        the `{ _comment?, expected_failures: { name: {class, reason} } }` shape
 *        of tools/wasm/wasm_expected_failures*.json. Defaults to
 *        temper-drc-rs's, which is what every caller meant before a second
 *        crate joined the tier.
 * @param {string|null} [moduleDigest] sha256 (hex) of the exact `.wasm` bytes
 *        `wasmModule` was compiled from, if the caller has one (see this
 *        file's header, "module_sha256 (issue #945)"). Returned from
 *        `/health` as `module_sha256`; omitted from the response when absent
 *        so an older Worker or a caller mid-rollout is distinguishable from
 *        one asserting a (wrong) digest.
 * @returns {{ fetch: (request: Request, env: object) => Promise<Response> }}
 */
export function createWorker(wasmModule, expectedFailures = DRC_EXPECTED_FAILURES, moduleDigest = null) {
  return createMultiFamilyWorker({ default: wasmModule }, expectedFailures, { default: moduleDigest });
}

// ---------------------------------------------------------------------------
// Multi-family worker (Phase 1 U8)

/**
 * Build a Worker fetch handler around a map of family→compiled module.
 *
 * Each family gets its own lazy-instantiated cached instance.  The first
 * request to a family pays the cold-compile cost for that family's (smaller)
 * module; subsequent requests reuse the cached instance.
 *
 * @param {Record<string, WebAssembly.Module>} familyModules
 *        e.g. { drc: moduleDrc, emc: moduleEmc, ... }
 *        Must include a "default" key for backward-compatible /run-test
 *        without a `family` field, and for /health.
 * @param {object} [expectedFailures] see `createWorker`. One manifest per
 *        Worker, not per family: every family in a single Worker comes from one
 *        crate's registry (the tier shards a crate, never mixes two).
 * @param {Record<string, string|null>} [familyDigests] see `createWorker`'s
 *        `moduleDigest` -- one sha256 (hex) per family, keyed the same as
 *        `familyModules`. A family with no entry (or `null`/falsy) simply
 *        omits `module_sha256` from its health responses; nothing requires
 *        every family to carry one, which is what lets this roll out
 *        Worker-by-Worker rather than needing a synchronized flag day.
 * @returns {{ fetch: (request: Request, env: object) => Promise<Response> }}
 */
export function createMultiFamilyWorker(familyModules, expectedFailures = DRC_EXPECTED_FAILURES, familyDigests = {}) {
  const families = new Set(Object.keys(familyModules));
  const EXPECTED_FAILURES = expectedFailures;
  const DIGESTS = familyDigests || {};

  /** `module_sha256` field to splice into a health payload, or {} if none. */
  function digestField(fam) {
    const d = DIGESTS[fam];
    return typeof d === "string" && d ? { module_sha256: d } : {};
  }

  // Per-family cached instances (lazy, one per family per isolate).
  const instances = Object.create(null);

  async function getInstance(family) {
    const mod = familyModules[family];
    if (!mod) return null;
    if (instances[family]) return instances[family];
    try {
      instances[family] = await WebAssembly.instantiate(mod, {});
    } catch {
      return null;
    }
    return instances[family];
  }

  /**
   * Instantiate the WASM module and run a single test by index.
   *
   * Returns { verdict, index, name, message, abi_version, ms, family }.
   */
  async function runTest(family, index, expectedAbi) {
    const t0 = Date.now();

    const inst = await getInstance(family);
    if (!inst) {
      return {
        verdict: "fail",
        index,
        name: null,
        message: `instantiation trap: family ${family} module could not be instantiated`,
        abi_version: null,
        ms: Date.now() - t0,
        family,
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
        family,
      };
    }

    const count = inst.exports.temper_test_count();
    if (index < 0 || index >= count) {
      return {
        verdict: "bad-index",
        index,
        name: null,
        message: `index ${index} out of range [0, ${count}) for family ${family}`,
        abi_version: abi,
        ms: Date.now() - t0,
        family,
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
        return { verdict: "pass", index, name, message: null, abi_version: abi, ms, family };
      } else if (rc === RUN_BAD_INDEX) {
        return { verdict: "bad-index", index, name, message: "registry returned bad-index", abi_version: abi, ms, family };
      } else {
        return { verdict: "fail", index, name, message: `unknown rc=${rc}`, abi_version: abi, ms, family };
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
      return { verdict: "fail", index, name, message, abi_version: abi, ms, family };
    }
  }

  /**
   * Resolve a test name to (family, index) by searching all
   * instantiated families.  For the initial census.
   */
  async function resolveFamilyAndIndex(testName) {
    for (const fam of families) {
      const inst = await getInstance(fam);
      if (!inst) continue;
      const count = inst.exports.temper_test_count();
      for (let i = 0; i < count; i++) {
        const n = readString(
          inst,
          inst.exports.temper_test_name_ptr(i),
          inst.exports.temper_test_name_len(i),
        );
        if (n === testName) return { family: fam, index: i };
      }
    }
    return null;
  }

  // -----------------------------------------------------------------------
  // Route table

  async function handleRequest(request, env) {
    const expectedAbi = parseInt((env && env.ABI_VERSION) || "1", 10);
    const url = new URL(request.url);
    const pathname = url.pathname;

    // GET /health — liveness + census for the default module
    if (request.method === "GET" && pathname === "/health") {
      try {
        const inst = await getInstance("default");
        if (!inst) return json({ status: "error", message: "instantiation failed" }, 500);
        const abi = inst.exports.temper_wasm_abi_version();
        const count = inst.exports.temper_test_count();
        return json({ status: "ok", abi_version: abi, test_count: count, ...digestField("default") });
      } catch (err) {
        return json({ status: "error", message: `instantiation failed: ${err.message || err}` }, 500);
      }
    }

    // GET /families — per-family census (all families)
    if (request.method === "GET" && pathname === "/families") {
      const result = {};
      for (const fam of families) {
        try {
          const inst = await getInstance(fam);
          if (!inst) {
            result[fam] = { error: "instantiation failed" };
          } else {
            result[fam] = {
              abi_version: inst.exports.temper_wasm_abi_version(),
              test_count: inst.exports.temper_test_count(),
              ...digestField(fam),
            };
          }
        } catch (err) {
          result[fam] = { error: `instantiation failed: ${err.message || err}` };
        }
      }
      return json({ families: result });
    }

    // GET /manifest — serve the expected-failure manifest
    if (request.method === "GET" && pathname === "/manifest") {
      return json(EXPECTED_FAILURES);
    }

    // GET /<family>/health — per-family health check
    const familyHealthMatch = pathname.match(/^\/([a-z]+)\/health$/);
    if (request.method === "GET" && familyHealthMatch) {
      const fam = familyHealthMatch[1];
      if (!families.has(fam)) {
        return json({ error: `unknown family: ${fam}` }, 404);
      }
      try {
        const inst = await getInstance(fam);
        if (!inst) return json({ status: "error", message: "instantiation failed" }, 500);
        const abi = inst.exports.temper_wasm_abi_version();
        const count = inst.exports.temper_test_count();
        return json({ status: "ok", family: fam, abi_version: abi, test_count: count, ...digestField(fam) });
      } catch (err) {
        return json({ status: "error", message: `instantiation failed: ${err.message || err}` }, 500);
      }
    }

    // POST /run-test — one test per invocation (R17)
    if (request.method === "POST" && pathname === "/run-test") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ error: "invalid JSON body" }, 400);
      }

      // Determine family: explicit in body, or default.
      let family = body.family || "default";
      if (!families.has(family)) {
        return json({ error: `unknown family: ${family}. Known: ${[...families].join(", ")}` }, 400);
      }

      let index;
      if (typeof body.index === "number") {
        index = body.index;
      } else if (typeof body.name === "string") {
        if (family !== "default") {
          // Name lookup within a specific family
          let inst;
          try {
            inst = await getInstance(family);
          } catch (err) {
            return json({ error: `instantiation failed: ${err.message || err}` }, 500);
          }
          if (!inst) return json({ error: "instantiation failed" }, 500);
          const nameIndex = buildNameIndex(inst);
          if (nameIndex.has(body.name)) {
            index = nameIndex.get(body.name);
          } else {
            return json({ verdict: "not-found", index: null, name: body.name, family, message: "test name not in registry" }, 404);
          }
        } else {
          // When family is not specified, search all families for the name
          const resolved = await resolveFamilyAndIndex(body.name);
          if (resolved) {
            family = resolved.family;
            index = resolved.index;
          } else {
            return json({ verdict: "not-found", index: null, name: body.name, message: "test name not found in any family registry" }, 404);
          }
        }
      } else {
        return json({ error: "body must contain { index: <number> } or { name: <string> }" }, 400);
      }

      const result = await runTest(family, index, expectedAbi);

      // Reclassify against the expected-failure manifest
      const expected = (EXPECTED_FAILURES?.expected_failures ?? {})[result.name];
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

    // GET / — help page
    if (request.method === "GET" && (pathname === "/" || pathname === "")) {
      const famList = [...families].map(f => `  GET /${f}/health`).join("\n");
      return text(
        "temper-wasm-tier Worker (multi-family)\n\n" +
        "POST /run-test  { family: \"...\", index: N } | { family: \"...\", name: \"...\" }\n" +
        "                { index: N } | { name: \"...\" }  (uses default family)\n" +
        "GET  /health\n" +
        "GET  /families\n" +
        "GET  /manifest\n" +
        famList + "\n",
        200
      );
    }

    // Catch-all
    return text("temper-wasm-tier Worker\n\nPOST /run-test  { family, index } | { family, name }\nGET  /families\nGET  /health\nGET  /manifest\n", 404);
  }

  return {
    async fetch(request, env, ctx) {
      return handleRequest(request, env);
    },
  };
}
