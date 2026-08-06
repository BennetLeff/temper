// Host driver for `temper-wasm-test-runner`.
//
// Runs every test in the `temper-drc-rs` wasm32 registry, one call at a time,
// and reports the numbers that decide whether the Cloudflare Workers tier is
// viable: cold start, per-test wall time, peak linear memory, and the import
// list (a module importing anything beyond the empty object needs host glue
// and is not deployable to a bare isolate).
//
// Only Node built-ins are used. Node's WebAssembly implementation is V8's --
// the same engine workerd embeds -- so trap behaviour and instantiation cost
// here are representative of a Worker, though not identical to one.
//
// Usage:
//   node tools/wasm/run_wasm_tests.mjs <module.wasm> [--json out.json]
//
// Exits non-zero if any test fails, so it can gate CI.

import { readFileSync, writeFileSync } from "node:fs";

const ABI_VERSION = 1;
const RUN_OK = 0;
const RUN_BAD_INDEX = 1;

const args = process.argv.slice(2);
const wasmPath = args[0];
if (!wasmPath) {
  console.error("usage: run_wasm_tests.mjs <module.wasm> [--json out.json]");
  process.exit(2);
}
const jsonFlag = args.indexOf("--json");
const jsonPath = jsonFlag === -1 ? null : args[jsonFlag + 1];

const expectFlag = args.indexOf("--expected-failures");
const expectPath =
  expectFlag === -1
    ? new URL("./wasm_expected_failures.json", import.meta.url).pathname
    : args[expectFlag + 1];

// Tests that execute on wasm32 and legitimately fail there because they assert
// a native-host property. See the manifest's own _comment for why they are
// listed rather than removed from the registry.
let expectedFailures = {};
try {
  expectedFailures = JSON.parse(readFileSync(expectPath, "utf8")).expected_failures ?? {};
} catch (err) {
  console.error(`could not read expected-failure manifest ${expectPath}: ${err.message}`);
  process.exit(2);
}

const bytes = readFileSync(wasmPath);

// ---------------------------------------------------------------- cold start
//
// Split compile from instantiate because they have different costs in a
// Worker: Cloudflare compiles the module once when the script is uploaded and
// instantiates per isolate, so the instantiate number is the one that recurs.

const tCompileStart = process.hrtime.bigint();
const module = await WebAssembly.compile(bytes);
const tCompileEnd = process.hrtime.bigint();

const imports = WebAssembly.Module.imports(module);
const exports = WebAssembly.Module.exports(module);

const tInstStart = process.hrtime.bigint();
let instance = await WebAssembly.instantiate(module, {});
const tInstEnd = process.hrtime.bigint();

const ms = (a, b) => Number(b - a) / 1e6;
const compileMs = ms(tCompileStart, tCompileEnd);
const instantiateMs = ms(tInstStart, tInstEnd);

// Re-instantiation is what the runner does after a trap, so measure it on its
// own rather than reusing the first (cache-cold) instantiate number.
async function newInstance() {
  const t0 = process.hrtime.bigint();
  const inst = await WebAssembly.instantiate(module, {});
  return { inst, ms: ms(t0, process.hrtime.bigint()) };
}

const abi = instance.exports.temper_wasm_abi_version();
if (abi !== ABI_VERSION) {
  console.error(`ABI mismatch: module reports ${abi}, host expects ${ABI_VERSION}`);
  process.exit(2);
}

// ------------------------------------------------------------------- census

const registered = instance.exports.temper_test_count();

/** Read a UTF-8 string out of the instance's linear memory. */
function readString(inst, ptr, len) {
  if (ptr === 0 || len === 0) return "";
  return new TextDecoder().decode(
    new Uint8Array(inst.exports.memory.buffer, ptr, len),
  );
}

function testName(inst, i) {
  return readString(
    inst,
    inst.exports.temper_test_name_ptr(i),
    inst.exports.temper_test_name_len(i),
  );
}

const names = [];
for (let i = 0; i < registered; i++) names.push(testName(instance, i));

// A registry that reports N tests but whose names are empty or duplicated is
// not actually N distinct tests. Check before trusting the count.
const distinctNames = new Set(names.filter((n) => n.length > 0)).size;

// ---------------------------------------------------------------- execution

const results = [];
let executed = 0;
let reinstantiations = 0;
let reinstantiateMsTotal = 0;
let survivedTrapProbe = null;
let peakMemoryBytes = instance.exports.memory.buffer.byteLength;

for (let i = 0; i < registered; i++) {
  const name = names[i];
  const t0 = process.hrtime.bigint();
  let status;
  let message = null;
  try {
    const rc = instance.exports.temper_run_test(i);
    const elapsed = ms(t0, process.hrtime.bigint());
    executed++;
    if (rc === RUN_OK) {
      status = "pass";
    } else if (rc === RUN_BAD_INDEX) {
      // The host looped within temper_test_count(), so this means the module's
      // count and its get() disagree -- a registry bug, not a test failure.
      status = "bad-index";
    } else {
      status = `unknown-rc-${rc}`;
    }
    results.push({ index: i, name, status, ms: elapsed });
  } catch (err) {
    // A panicking test aborts, which on wasm32 is the `unreachable`
    // instruction, which V8 surfaces as RuntimeError. This -- not a return
    // value -- is the failure signal.
    const elapsed = ms(t0, process.hrtime.bigint());
    executed++;
    status = err instanceof WebAssembly.RuntimeError ? "fail" : "host-error";

    // Read the panic text off the trapped instance before replacing it. The
    // wasm store survives a trap, so this is well-defined.
    try {
      message = readString(
        instance,
        instance.exports.temper_panic_message_ptr(),
        instance.exports.temper_panic_message_len(),
      );
      // Probe whether the trapped instance is still callable at all. Recorded
      // once: it decides whether a Worker must re-instantiate per failure.
      if (survivedTrapProbe === null) {
        survivedTrapProbe = instance.exports.temper_test_count() === registered;
      }
    } catch {
      message = "(panic message unreadable: instance unusable after trap)";
      if (survivedTrapProbe === null) survivedTrapProbe = false;
    }

    results.push({
      index: i,
      name,
      status,
      ms: elapsed,
      error: String(err && err.message ? err.message : err),
      panic: message,
    });

    // Rust's abort leaves the allocator mid-mutation, so continuing on a
    // poisoned heap would make every later result suspect. Start clean.
    const fresh = await newInstance();
    instance = fresh.inst;
    reinstantiations++;
    reinstantiateMsTotal += fresh.ms;
  }
  peakMemoryBytes = Math.max(peakMemoryBytes, instance.exports.memory.buffer.byteLength);
}

// ------------------------------------------------------------------ reporting

// Reclassify against the manifest. A listed test that fails is accounted for;
// a listed test that *passes* means the exclusion has gone stale and is now
// suppressing a test that would otherwise be doing work -- so it fails the run
// too, in the opposite direction.
for (const r of results) {
  const expected = expectedFailures[r.name];
  if (!expected) continue;
  r.expectedFailureClass = expected.class;
  r.expectedFailureReason = expected.reason;
  if (r.status === "fail") r.status = "expected-fail";
  else if (r.status === "pass") r.status = "unexpected-pass";
}

const count = (s) => results.filter((r) => r.status === s).length;
const passed = count("pass");
const failed = count("fail");
const expectedFail = count("expected-fail");
const unexpectedPass = count("unexpected-pass");
const other = results.length - passed - failed - expectedFail - unexpectedPass;

// An exclusion for a test that is not in the registry at all is dead weight and
// hides drift just as effectively as a stale one.
const registryNames = new Set(names);
const orphanExclusions = Object.keys(expectedFailures).filter((n) => !registryNames.has(n));

const times = results.map((r) => r.ms).sort((a, b) => a - b);
const pct = (p) => (times.length ? times[Math.min(times.length - 1, Math.floor(times.length * p))] : 0);
const totalMs = times.reduce((a, b) => a + b, 0);

const summary = {
  module: wasmPath,
  moduleBytes: bytes.length,
  imports: imports.map((i) => `${i.module}.${i.name} (${i.kind})`),
  exportCount: exports.length,
  abi,
  registered,
  executed,
  distinctNames,
  passed,
  failed,
  expectedFail,
  unexpectedPass,
  other,
  orphanExclusions,
  compileMs: +compileMs.toFixed(3),
  instantiateMs: +instantiateMs.toFixed(3),
  coldStartMs: +(compileMs + instantiateMs).toFixed(3),
  totalTestMs: +totalMs.toFixed(3),
  meanTestMs: +(totalMs / (times.length || 1)).toFixed(4),
  medianTestMs: +pct(0.5).toFixed(4),
  p95TestMs: +pct(0.95).toFixed(4),
  maxTestMs: +(times[times.length - 1] ?? 0).toFixed(4),
  peakMemoryBytes,
  peakMemoryMiB: +(peakMemoryBytes / 1048576).toFixed(2),
  reinstantiations,
  reinstantiateMsMean: reinstantiations
    ? +(reinstantiateMsTotal / reinstantiations).toFixed(3)
    : null,
  instanceCallableAfterTrap: survivedTrapProbe,
};

console.log("=== module ===");
console.log(`  file            ${wasmPath}`);
console.log(`  size            ${bytes.length} bytes`);
console.log(`  imports         ${imports.length === 0 ? "NONE (deployable to a bare isolate)" : summary.imports.join(", ")}`);
console.log(`  exports         ${exports.length}`);
console.log("=== cold start ===");
console.log(`  compile         ${summary.compileMs} ms`);
console.log(`  instantiate     ${summary.instantiateMs} ms`);
console.log(`  cold start      ${summary.coldStartMs} ms`);
console.log("=== census ===");
console.log(`  registered      ${registered}`);
console.log(`  executed        ${executed}`);
console.log(`  distinct names  ${distinctNames}`);
console.log("=== results ===");
console.log(`  passed            ${passed}`);
console.log(`  failed            ${failed}`);
console.log(`  expected-fail     ${expectedFail}  (native-only properties; see manifest)`);
console.log(`  unexpected-pass   ${unexpectedPass}  (stale exclusions)`);
console.log(`  other             ${other}`);
console.log("=== timing (per test) ===");
console.log(`  total           ${summary.totalTestMs} ms`);
console.log(`  mean            ${summary.meanTestMs} ms`);
console.log(`  median          ${summary.medianTestMs} ms`);
console.log(`  p95             ${summary.p95TestMs} ms`);
console.log(`  max             ${summary.maxTestMs} ms`);
console.log("=== memory ===");
console.log(`  peak linear     ${summary.peakMemoryMiB} MiB (isolate limit 128 MiB)`);
console.log("=== trap handling ===");
console.log(`  reinstantiations       ${reinstantiations}`);
console.log(`  mean reinstantiate ms  ${summary.reinstantiateMsMean ?? "n/a"}`);
console.log(`  instance usable after trap  ${survivedTrapProbe ?? "n/a (no traps)"}`);

for (const r of results) {
  if (r.status === "pass") continue;
  console.log(`\n  [${r.status.toUpperCase()}] #${r.index} ${r.name}`);
  if (r.expectedFailureClass) console.log(`      class: ${r.expectedFailureClass}`);
  if (r.panic) console.log(`      ${r.panic.split("\n").join("\n      ")}`);
  else if (r.error) console.log(`      ${r.error}`);
}

if (orphanExclusions.length) {
  console.log("\n  [ORPHAN EXCLUSIONS] named in the manifest but not in the registry:");
  for (const n of orphanExclusions) console.log(`      ${n}`);
}

if (jsonPath) {
  writeFileSync(jsonPath, JSON.stringify({ summary, results }, null, 2));
  console.log(`\nwrote ${jsonPath}`);
}

// The vacuity check this whole exercise exists to rule out: a harness that
// reports green because it ran nothing. Registered must equal executed, and
// both must be non-zero.
if (registered === 0) {
  console.error("\nFATAL: registry is empty -- a green result here would be meaningless.");
  process.exit(3);
}
if (executed !== registered) {
  console.error(`\nFATAL: executed ${executed} of ${registered} registered tests.`);
  process.exit(3);
}
if (distinctNames !== registered) {
  console.error(`\nFATAL: ${registered} tests registered but only ${distinctNames} distinct names.`);
  process.exit(3);
}

if (unexpectedPass > 0) {
  console.error(
    `\n${unexpectedPass} test(s) named in the expected-failure manifest now PASS. ` +
      `The exclusion is stale -- remove it so the test counts again.`,
  );
}
if (orphanExclusions.length) {
  console.error(`\n${orphanExclusions.length} manifest entr(ies) name no registered test.`);
}

process.exit(failed + other + unexpectedPass + orphanExclusions.length > 0 ? 1 : 0);
