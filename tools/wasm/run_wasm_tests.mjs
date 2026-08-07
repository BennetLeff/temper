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
//   node tools/wasm/run_wasm_tests.mjs <module.wasm> [--json out.json] [--repeat K]
//
// --repeat K runs the full suite K times with a fresh module instantiation per
// repetition, matching the Workers model (one isolate per invocation).
// Aggregate timing (median / p95 / max per repetition) is reported.
// When absent, defaults to 1 (single run, same behaviour as before).
//
// Exits non-zero if any test fails, so it can gate CI.

import { readFileSync, writeFileSync } from "node:fs";

const ABI_VERSION = 1;
const RUN_OK = 0;
const RUN_BAD_INDEX = 1;

const args = process.argv.slice(2);
const wasmPath = args[0];
if (!wasmPath) {
  console.error("usage: run_wasm_tests.mjs <module.wasm> [--json out.json] [--repeat K]");
  process.exit(2);
}
const jsonFlag = args.indexOf("--json");
const jsonPath = jsonFlag === -1 ? null : args[jsonFlag + 1];

const expectFlag = args.indexOf("--expected-failures");
const expectPath =
  expectFlag === -1
    ? new URL("./wasm_expected_failures.json", import.meta.url).pathname
    : args[expectFlag + 1];

const repeatFlag = args.indexOf("--repeat");
const repeatCount = repeatFlag === -1 ? 1 : Math.max(1, parseInt(args[repeatFlag + 1], 10) || 1);

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

/**
 * Run every registered test on `inst`, one index at a time.
 *
 * Returns { results, executed, reinstantiations, reinstantiateMsTotal,
 *           survivedTrapProbe, peakMemoryBytes }.
 * Callers may need to re-instantiate between runs (for `--repeat`).
 */
async function runSuite(inst) {
  const results = [];
  let executed = 0;
  let reinstantiations = 0;
  let reinstantiateMsTotal = 0;
  let survivedTrapProbe = null;
  let peakMemoryBytes = inst.exports.memory.buffer.byteLength;

  for (let i = 0; i < registered; i++) {
    const name = names[i];
    const t0 = process.hrtime.bigint();
    let status;
    let message = null;
    try {
      const rc = inst.exports.temper_run_test(i);
      const elapsed = ms(t0, process.hrtime.bigint());
      executed++;
      if (rc === RUN_OK) {
        status = "pass";
      } else if (rc === RUN_BAD_INDEX) {
        status = "bad-index";
      } else {
        status = `unknown-rc-${rc}`;
      }
      results.push({ index: i, name, status, ms: elapsed });
    } catch (err) {
      const elapsed = ms(t0, process.hrtime.bigint());
      executed++;
      status = err instanceof WebAssembly.RuntimeError ? "fail" : "host-error";

      try {
        message = readString(
          inst,
          inst.exports.temper_panic_message_ptr(),
          inst.exports.temper_panic_message_len(),
        );
        if (survivedTrapProbe === null) {
          survivedTrapProbe = inst.exports.temper_test_count() === registered;
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

      const fresh = await newInstance();
      inst = fresh.inst;
      reinstantiations++;
      reinstantiateMsTotal += fresh.ms;
    }
    peakMemoryBytes = Math.max(peakMemoryBytes, inst.exports.memory.buffer.byteLength);
  }
  return { results, executed, reinstantiations, reinstantiateMsTotal, survivedTrapProbe, peakMemoryBytes };
}

// ---------- repeat loop: fresh instantiation per repetition ----------

const repStats = [];
let allResults = [];
let totalExecuted = 0;
let totalFailures = 0;
let totalUnexpectedPass = 0;
let totalOther = 0;
let globalPeakMemoryBytes = instance.exports.memory.buffer.byteLength;
let globalReinstantiations = 0;
let globalReinstantiateMsTotal = 0;
let globalSurvivedTrapProbe = null;

const tStart = process.hrtime.bigint();

for (let rep = 0; rep < repeatCount; rep++) {
  const tRepStart = process.hrtime.bigint();

  // For the first repetition when repeatCount === 1, reuse the census
  // instance to preserve the original single-run timing behaviour.
  const isFirstRep = rep === 0;
  const useCensusInstance = repeatCount === 1 && isFirstRep;
  const fresh = useCensusInstance ? { inst: instance, ms: instantiateMs } : await newInstance();

  const suite = await runSuite(fresh.inst);

  const repWallMs = ms(tRepStart, process.hrtime.bigint());
  repStats.push({
    repetition: rep,
    wallMs: +repWallMs.toFixed(3),
    instantiateMs: +fresh.ms.toFixed(3),
    executed: suite.executed,
    reinstantiations: suite.reinstantiations,
    reinstantiateMsMean: suite.reinstantiations
      ? +(suite.reinstantiateMsTotal / suite.reinstantiations).toFixed(3)
      : null,
    peakMemoryMiB: +(suite.peakMemoryBytes / 1048576).toFixed(2),
  });

  allResults.push(...suite.results);
  totalExecuted += suite.executed;
  if (suite.survivedTrapProbe !== null) globalSurvivedTrapProbe = suite.survivedTrapProbe;
  globalPeakMemoryBytes = Math.max(globalPeakMemoryBytes, suite.peakMemoryBytes);
  globalReinstantiations += suite.reinstantiations;
  globalReinstantiateMsTotal += suite.reinstantiateMsTotal;

  const repFail = suite.results.filter((r) => r.status === "fail").length;
  const repUnexp = suite.results.filter((r) => r.status === "unexpected-pass").length;
  const repOther = suite.results.filter(
    (r) => r.status !== "pass" && r.status !== "fail" && r.status !== "unexpected-pass",
  ).length;
  totalFailures += repFail;
  totalUnexpectedPass += repUnexp;
  totalOther += repOther;
}

const totalWallMs = ms(tStart, process.hrtime.bigint());

// ------------------------------------------------------------------ reporting

// Reclassify against the manifest (applied across all repetitions).
for (const r of allResults) {
  const expected = expectedFailures[r.name];
  if (!expected) continue;
  r.expectedFailureClass = expected.class;
  r.expectedFailureReason = expected.reason;
  if (r.status === "fail") r.status = "expected-fail";
  else if (r.status === "pass") r.status = "unexpected-pass";
}

const count = (s) => allResults.filter((r) => r.status === s).length;
const passed = count("pass");
const failed = count("fail");
const expectedFail = count("expected-fail");
const unexpectedPass = count("unexpected-pass");
const other = allResults.length - passed - failed - expectedFail - unexpectedPass;

const registryNames = new Set(names);
const orphanExclusions = Object.keys(expectedFailures).filter((n) => !registryNames.has(n));

const times = allResults.map((r) => r.ms).sort((a, b) => a - b);
const pct = (p) => (times.length ? times[Math.min(times.length - 1, Math.floor(times.length * p))] : 0);
const totalTestMs = times.reduce((a, b) => a + b, 0);

// Per-repetition wall times for aggregate reporting
const repWalls = repStats.map((r) => r.wallMs).sort((a, b) => a - b);
const repPct = (p) => repWalls.length
  ? repWalls[Math.min(repWalls.length - 1, Math.floor(repWalls.length * p))]
  : 0;

const summary = {
  module: wasmPath,
  moduleBytes: bytes.length,
  imports: imports.map((i) => `${i.module}.${i.name} (${i.kind})`),
  exportCount: exports.length,
  abi,
  registered,
  executed: totalExecuted,
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
  totalTestMs: +totalTestMs.toFixed(3),
  meanTestMs: +(totalTestMs / (times.length || 1)).toFixed(4),
  medianTestMs: +pct(0.5).toFixed(4),
  p95TestMs: +pct(0.95).toFixed(4),
  maxTestMs: +(times[times.length - 1] ?? 0).toFixed(4),
  peakMemoryBytes: globalPeakMemoryBytes,
  peakMemoryMiB: +(globalPeakMemoryBytes / 1048576).toFixed(2),
  reinstantiations: globalReinstantiations,
  reinstantiateMsMean: globalReinstantiations
    ? +(globalReinstantiateMsTotal / globalReinstantiations).toFixed(3)
    : null,
  instanceCallableAfterTrap: globalSurvivedTrapProbe,
  // Repeat-mode aggregates
  repetitions: repeatCount,
  totalWallMs: +totalWallMs.toFixed(3),
  repMeanWallMs: +(totalWallMs / repeatCount).toFixed(3),
  repMedianWallMs: +repPct(0.5).toFixed(3),
  repP95WallMs: +repPct(0.95).toFixed(3),
  repMaxWallMs: +(repWalls[repWalls.length - 1] ?? 0).toFixed(3),
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
if (repeatCount > 1) {
  console.log(`  repetitions     ${repeatCount}`);
  console.log(`  total wall      ${summary.totalWallMs} ms`);
  console.log(`  rep mean        ${summary.repMeanWallMs} ms`);
  console.log(`  rep median      ${summary.repMedianWallMs} ms`);
  console.log(`  rep p95         ${summary.repP95WallMs} ms`);
  console.log(`  rep max         ${summary.repMaxWallMs} ms`);
}
console.log("=== census ===");
console.log(`  registered      ${registered}`);
console.log(`  executed        ${totalExecuted}`);
console.log(`  distinct names  ${distinctNames}`);
console.log("=== results ===");
console.log(`  passed            ${passed}`);
console.log(`  failed            ${failed}`);
console.log(`  expected-fail     ${expectedFail}  (native-only properties; see manifest)`);
console.log(`  unexpected-pass   ${unexpectedPass}  (stale exclusions)`);
console.log(`  other             ${other}`);
console.log("=== timing (per test invocation) ===");
console.log(`  total           ${summary.totalTestMs} ms`);
console.log(`  mean            ${summary.meanTestMs} ms`);
console.log(`  median          ${summary.medianTestMs} ms`);
console.log(`  p95             ${summary.p95TestMs} ms`);
console.log(`  max             ${summary.maxTestMs} ms`);
console.log("=== memory ===");
console.log(`  peak linear     ${summary.peakMemoryMiB} MiB (isolate limit 128 MiB)`);
console.log("=== trap handling ===");
console.log(`  reinstantiations       ${globalReinstantiations}`);
console.log(`  mean reinstantiate ms  ${summary.reinstantiateMsMean ?? "n/a"}`);
console.log(`  instance usable after trap  ${globalSurvivedTrapProbe ?? "n/a (no traps)"}`);

// Only show non-pass results from the first repetition (to keep output manageable
// in repeat mode — verdicts are stable across repetitions).
const firstRepResults = repeatCount <= 1
  ? allResults
  : allResults.slice(0, registered);  // first repetition only

for (const r of firstRepResults) {
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
  // For --json in repeat mode, include per-repetition stats and the full result
  // set (flattened across all repetitions).
  writeFileSync(
    jsonPath,
    JSON.stringify({ summary, results: allResults, repStats }, null, 2),
  );
  console.log(`\nwrote ${jsonPath}`);
}

// Vacuity checks: applied across all repetitions.
if (registered === 0) {
  console.error("\nFATAL: registry is empty -- a green result here would be meaningless.");
  process.exit(3);
}

// In repeat mode, each repetition runs all N tests, so totalExecuted should be
// N * repeatCount. Check per-rep consistency instead.
const repExecutedSet = new Set(repStats.map((r) => r.executed));
if (repExecutedSet.size !== 1 || !repExecutedSet.has(registered)) {
  console.error(`\nFATAL: not all repetitions executed exactly ${registered} tests (got ${[...repExecutedSet]})`);
  process.exit(3);
}
if (distinctNames !== registered) {
  console.error(`\nFATAL: ${registered} tests registered but only ${distinctNames} distinct names.`);
  process.exit(3);
}

if (unexpectedPass > 0) {
  console.error(
    `\n${unexpectedPass} test invocation(s) named in the expected-failure manifest now PASS. ` +
      `The exclusion is stale -- remove it so the test counts again.`,
  );
}
if (orphanExclusions.length) {
  console.error(`\n${orphanExclusions.length} manifest entr(ies) name no registered test.`);
}

process.exit(failed + other + unexpectedPass + orphanExclusions.length > 0 ? 1 : 0);
