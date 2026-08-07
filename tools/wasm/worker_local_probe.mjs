/**
 * Local verification probe for the temper Worker.
 *
 * Runs the Worker's per-test-invocation logic against the real
 * `temper_wasm_test_runner.wasm` artifact under Node's V8 — the Phase-0-
 * sanctioned workerd substitution (workerd embeds V8). The probe:
 *
 * 1. Compiles the .wasm module (one-time cost).
 * 2. Instantiates a fresh module per test invocation (Workers model).
 * 3. Runs a few canonical indexes:
 *    - #0  — a passing test (static-data assertion, O(µs))
 *    - #26 — a known expected-fail (B7 pow-divergence, traps)
 *    - #50 — another expected-fail (B7 pow-divergence, traps)
 * 4. Records cold-start (compile + first instantiate) and per-invocation
 *    wall-time, then prints the numbers for the U7 evidence doc.
 *
 * Usage:
 *   node tools/wasm/worker_local_probe.mjs [path/to/module.wasm]
 *
 * If no path is given, the script looks for the artifact at:
 *   <repo>/target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm
 *
 * If the artifact is missing, the script exits with instructions to build it.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { hrtime } from "node:process";
import { join, dirname } from "node:path";

// ---------------------------------------------------------------------------
// Constants (mirrors the wasm-test-runner ABI and the Worker)

const ABI_VERSION = 1;
const RUN_OK = 0;
const RUN_BAD_INDEX = 1;

// Expected-fail tests, keyed by NAME (from the committed manifest) rather than
// by hardcoded index, so the probe stays correct as the census grows. The
// registry appends new families at the end, but name-keying removes the need
// to track shifts at all.
const EXPECTED_FAIL_NAMES = new Set(
  Object.keys(
    JSON.parse(
      readFileSync(new URL("./wasm_expected_failures.json", import.meta.url), "utf8"),
    ).expected_failures ?? {},
  ),
);

// ---------------------------------------------------------------------------
// Helpers

function readString(inst, ptr, len) {
  if (ptr === 0 || len === 0) return "";
  return new TextDecoder().decode(
    new Uint8Array(inst.exports.memory.buffer, ptr, len),
  );
}

function ms(a, b) {
  return Number(b - a) / 1e6;
}

// ---------------------------------------------------------------------------
// Main

async function main() {
  // Resolve .wasm path
  const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
  const defaultWasm = join(
    repoRoot,
    "target-shared",
    "wasm32-unknown-unknown",
    "release",
    "temper_wasm_test_runner.wasm",
  );
  const wasmPath = process.argv[2] || defaultWasm;

  let bytes;
  try {
    bytes = readFileSync(wasmPath);
  } catch {
    console.error(`WASM module not found at: ${wasmPath}`);
    console.error("");
    console.error("Build it first:");
    console.error(
      "  cargo build --release --target wasm32-unknown-unknown --no-default-features \\",
    );
    console.error(
      "    --manifest-path packages/temper-wasm-test-runner/Cargo.toml",
    );
    process.exit(2);
  }

  // -------------------------------------------------------------------
  // 1. Cold start: compile + first instantiate
  console.error("=== cold start ===");

  const tCompileStart = hrtime.bigint();
  const module = await WebAssembly.compile(bytes);
  const tCompileEnd = hrtime.bigint();
  const compileMs = ms(tCompileStart, tCompileEnd);

  const tFirstInstStart = hrtime.bigint();
  // WebAssembly.instantiate(compiledModule, importObject) returns the Instance directly.
  let instance = await WebAssembly.instantiate(module, {});
  const tFirstInstEnd = hrtime.bigint();
  const firstInstantiateMs = ms(tFirstInstStart, tFirstInstEnd);

  console.error(
    `  compile       ${compileMs.toFixed(3)} ms`,
  );
  console.error(
    `  instantiate   ${firstInstantiateMs.toFixed(3)} ms`,
  );
  console.error(
    `  cold start    ${(compileMs + firstInstantiateMs).toFixed(3)} ms`,
  );

  // Validate ABI and census
  const abi = instance.exports.temper_wasm_abi_version();
  if (abi !== ABI_VERSION) {
    console.error(`ABI mismatch: module ${abi}, probe expects ${ABI_VERSION}`);
    process.exit(2);
  }

  const registered = instance.exports.temper_test_count();

  // Read test names once
  const names = [];
  for (let i = 0; i < registered; i++) {
    names.push(
      readString(
        instance,
        instance.exports.temper_test_name_ptr(i),
        instance.exports.temper_test_name_len(i),
      ),
    );
  }

  console.error(
    `  module        ${bytes.length.toLocaleString()} bytes, ${registered} tests registered`,
  );
  console.error(
    `  imports       ${
      WebAssembly.Module.imports(module).length === 0
        ? "NONE (deployable)"
        : `${WebAssembly.Module.imports(module).length} imports`
    }`,
  );
  console.error("");

  // Quick function: fresh instantiate (in Cloudflare, the module is compiled
  // at upload; instantiate is what recurs per request — see wrangler.toml).
  // WebAssembly.instantiate(compiledModule, importObject) returns the
  // WebAssembly.Instance directly (not a {module, instance} wrapper).
  async function newInstance() {
    const t0 = hrtime.bigint();
    const inst = await WebAssembly.instantiate(module, {});
    return { inst, ms: ms(t0, hrtime.bigint()) };
  }

  // -------------------------------------------------------------------
  // 2. Probe a few canonical indexes
  console.error("=== per-invocation probe ===");

  const probeIndices = [
    { index: 0,  label: "first passing test (index 0)" },
    { index: 26, label: "expected-fail (dfm::thermal_via_side_round..., B7)" },
    { index: 50, label: "expected-fail (pymath::pow_is_not_a_multiply..., B7)" },
    { index: 1,  label: "second passing test (index 1)" },
  ];

  const results = [];

  for (const probe of probeIndices) {
    const { index, label } = probe;
    const name = names[index] || `(unknown index ${index})`;

    // Fresh instantiate per invocation (Workers model)
    const fresh = await newInstance();
    const tTest0 = hrtime.bigint();

    let verdict, message;
    try {
      const rc = fresh.inst.exports.temper_run_test(index);
      const elapsed = ms(tTest0, hrtime.bigint());

      if (rc === RUN_OK) {
        verdict = "pass";
      } else if (rc === RUN_BAD_INDEX) {
        verdict = "bad-index";
      } else {
        verdict = `unknown-rc-${rc}`;
      }
      message = null;
      results.push({ index, label, name, verdict, elapsed, instantiateMs: fresh.ms });
    } catch (err) {
      const elapsed = ms(tTest0, hrtime.bigint());

      // Read panic buffer from the dying instance
      try {
        message = readString(
          fresh.inst,
          fresh.inst.exports.temper_panic_message_ptr(),
          fresh.inst.exports.temper_panic_message_len(),
        );
      } catch {
        message = "(panic message unreadable)";
      }

      const isExpectedFail = EXPECTED_FAIL_NAMES.has(name);
      verdict = isExpectedFail ? "expected-fail" : "fail";
      results.push({
        index,
        label,
        name,
        verdict,
        elapsed,
        instantiateMs: fresh.ms,
        message: message ? message.split("\n")[0] : null,
      });
    }
  }

  // -------------------------------------------------------------------
  // 3. Warm instantiate benchmark (N instantiations without test execution)
  console.error("=== warm instantiate benchmark (100 samples) ===");

  const instantiateSamples = [];
  for (let i = 0; i < 100; i++) {
    const fresh = await newInstance();
    instantiateSamples.push(fresh.ms);
  }
  instantiateSamples.sort((a, b) => a - b);

  const pct = (arr, p) =>
    arr[Math.min(arr.length - 1, Math.floor(arr.length * p))];
  const mean = (arr) => arr.reduce((a, b) => a + b, 0) / arr.length;

  console.error(
    `  instantiate mean   ${mean(instantiateSamples).toFixed(3)} ms`,
  );
  console.error(
    `  instantiate median ${pct(instantiateSamples, 0.5).toFixed(3)} ms`,
  );
  console.error(
    `  instantiate p95    ${pct(instantiateSamples, 0.95).toFixed(3)} ms`,
  );
  console.error(
    `  instantiate max    ${instantiateSamples[instantiateSamples.length - 1].toFixed(3)} ms`,
  );
  console.error("");

  // -------------------------------------------------------------------
  // 4. Summary for evidence doc
  console.error("=== summary ===");
  for (const r of results) {
    console.error(
      `  #${r.index} [${r.verdict}] ${r.label}`,
    );
    console.error(
      `      instantiate: ${r.instantiateMs.toFixed(3)} ms  test: ${r.elapsed.toFixed(4)} ms  total: ${(r.instantiateMs + r.elapsed).toFixed(3)} ms`,
    );
    if (r.message) {
      console.error(`      ${r.message}`);
    }
  }

  // Print JSON for the evidence doc
  console.log(
    JSON.stringify(
      {
        cold_start: {
          compile_ms: +compileMs.toFixed(3),
          first_instantiate_ms: +firstInstantiateMs.toFixed(3),
          total_cold_start_ms: +(compileMs + firstInstantiateMs).toFixed(3),
        },
        warm_instantiate: {
          samples: instantiateSamples.length,
          mean_ms: +mean(instantiateSamples).toFixed(3),
          median_ms: +pct(instantiateSamples, 0.5).toFixed(3),
          p95_ms: +pct(instantiateSamples, 0.95).toFixed(3),
          max_ms: +instantiateSamples[instantiateSamples.length - 1].toFixed(3),
        },
        module: {
          path: wasmPath,
          size_bytes: bytes.length,
          imports: WebAssembly.Module.imports(module).length,
          registered_tests: registered,
        },
        probe_results: results.map((r) => ({
          index: r.index,
          name: r.name,
          verdict: r.verdict,
          instantiate_ms: +r.instantiateMs.toFixed(3),
          test_ms: +r.elapsed.toFixed(4),
          total_ms: +(r.instantiateMs + r.elapsed).toFixed(3),
          message: r.message || null,
        })),
      },
      null,
      2,
    ),
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
