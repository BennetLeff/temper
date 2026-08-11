#!/usr/bin/env node
/**
 * ANTI-VACUITY TEST for tools/wasm/check_deployed_freshness.mjs.
 *
 *   node tools/wasm/test_check_deployed_freshness.mjs
 *
 * A staleness control that cannot be shown to fail is not a control. This file
 * is the demonstration, kept in the repo rather than pasted into a PR body once,
 * because the property it pins is exactly the property a future refactor of that
 * script would quietly remove: the checker must go RED when a deployed count
 * diverges from the built count, for EVERY crate independently, and must refuse
 * to run at all when a crate has no built count to compare against.
 *
 * Deliberately not wired into any required check (the WASM tier is advisory by
 * design — see wasm-tier-deploy.yml's header). Run it by hand, or from the
 * nightly, when touching the checker.
 *
 * ## How the deployed census is faked
 *
 * check_deployed_freshness.mjs talks to the real Workers over `fetch`. Each case
 * below runs it in a child process under `--import`, with a tiny stub module
 * that replaces `globalThis.fetch` with one that answers `/health` from a census
 * supplied in the environment. Nothing in the checker is modified, mocked out or
 * bypassed: the same argument parsing, the same topology file, the same
 * comparisons, the same exit codes. Only the network is substituted.
 */

import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { loadTopology } from "./tier_topology.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const CHECKER = join(HERE, "check_deployed_freshness.mjs");
const TMP = mkdtempSync(join(tmpdir(), "freshness-test-"));

const STUB = join(TMP, "fetch_stub.mjs");
writeFileSync(
  STUB,
  `const census = JSON.parse(process.env.FAKE_HEALTH_CENSUS);
globalThis.fetch = async (url) => {
  const script = new URL(url).hostname.split(".")[0];
  const entry = census[script];
  if (entry === undefined) {
    return new Response("not found", { status: 404 });
  }
  return new Response(JSON.stringify({ status: "ok", ...entry }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
};
`,
);

const topology = loadTopology();

/**
 * The census the tier reports when everything is current, derived from the
 * topology so this file does not carry its own copy of the Worker list.
 * Per-shard numbers are today's deployed reality (2026-08-10): drc 1510, infra
 * 121, safety 25, placement 18, routing 18, emc 15, erc 12 = 1719,
 * temper-wasm-geometry's 722, and temper-wasm-thermal's 143.
 */
const DRC_SHARDS = {
  drc: 1510,
  infra: 121,
  safety: 25,
  placement: 18,
  routing: 18,
  emc: 15,
  erc: 12,
};
const DRC_BUILT = Object.values(DRC_SHARDS).reduce((a, b) => a + b, 0); // 1719
const GEOMETRY_BUILT = 722;
// EXECUTABLE, not registered. packages/temper-thermal/src/wasm_test_registry.rs
// names 145; two entries carry their own `cfg` and are compiled out of the
// wasm32 module rather than skipped at runtime
// (device_power::tests::host_libm_symbols_actually_resolve is
// `#[cfg(not(target_arch = "wasm32"))]`, hostmath::tests::dlsym_resolves_on_macos
// is `#[cfg(target_os = "macos")]`), so the module -- and therefore /health --
// reports 143. Using 145 here would make every case below fail for a reason
// that has nothing to do with staleness, which is exactly the confusion the
// geometry 724-vs-722 gap already caused once.
const THERMAL_BUILT = 143;

function freshCensus() {
  const census = { "temper-wasm-tier": { test_count: DRC_BUILT, abi_version: 1 } };
  for (const [family, count] of Object.entries(DRC_SHARDS)) {
    census[`temper-wasm-${family}`] = { test_count: count, abi_version: 1 };
  }
  census["temper-wasm-geometry"] = { test_count: GEOMETRY_BUILT, abi_version: 1 };
  census["temper-wasm-thermal"] = { test_count: THERMAL_BUILT, abi_version: 1 };
  return census;
}

/** Write a run_wasm_tests.mjs-shaped census file and return its path. */
function builtJson(name, registered) {
  const path = join(TMP, `${name}.json`);
  writeFileSync(path, JSON.stringify({ summary: { registered }, results: [] }));
  return path;
}

const BUILT_DRC = builtJson("built_drc", DRC_BUILT);
const BUILT_GEOMETRY = builtJson("built_geometry", GEOMETRY_BUILT);
const BUILT_THERMAL = builtJson("built_thermal", THERMAL_BUILT);

/**
 * The full, correct argument set: one built count per tier in the topology.
 * Spelled as a constant rather than repeated per case so that adding a tier is
 * one edit here — and so the cases in section D, which deliberately drop one
 * flag, are visibly the exception rather than indistinguishable from an
 * oversight.
 */
const ALL_BUILT = [
  "--built-json",
  BUILT_DRC,
  "--built-json-geometry",
  BUILT_GEOMETRY,
  "--built-json-thermal",
  BUILT_THERMAL,
];

/**
 * Fails if the topology grows a tier that this file does not supply a count
 * for. Without it, the new tier's cases would simply not exist while the suite
 * still printed "All cases passed" — a green anti-vacuity suite that stopped
 * covering part of the thing it exists to cover. Section D proves the CHECKER
 * refuses that; this proves the TEST FILE refuses it too.
 */
{
  const covered = new Set(
    ALL_BUILT.filter((a) => a.startsWith("--built-json")).map((a) =>
      a === "--built-json" ? "temper-drc-rs" : `temper-${a.replace("--built-json-", "")}`,
    ),
  );
  const uncovered = topology.tiers.map((t) => t.crate).filter((c) => !covered.has(c));
  if (uncovered.length) {
    console.error(
      `This suite supplies no built count for tier(s) ${uncovered.join(", ")}, which are in ` +
        "tools/wasm/wasm_tier_topology.json. Every case below would then exercise the " +
        "checker's usage-error path (exit 2) instead of its staleness path, and the file " +
        "would stop testing what it claims to. Add the tier to ALL_BUILT, to freshCensus(), " +
        "and give it its own staleness case.",
    );
    process.exit(1);
  }
}

function run(args, census) {
  const res = spawnSync(process.execPath, ["--import", STUB, CHECKER, ...args], {
    env: { ...process.env, FAKE_HEALTH_CENSUS: JSON.stringify(census) },
    encoding: "utf8",
  });
  return { code: res.status, out: `${res.stdout}\n${res.stderr}` };
}

let failures = 0;
function expect(label, { code, out }, wantCode, wantSubstring) {
  const okCode = code === wantCode;
  const okText = wantSubstring === undefined || out.includes(wantSubstring);
  if (okCode && okText) {
    console.log(`  PASS  ${label}  (exit ${code})`);
    return;
  }
  failures += 1;
  console.log(`  FAIL  ${label}`);
  console.log(`        wanted exit ${wantCode}, got ${code}`);
  if (!okText) console.log(`        wanted output containing: ${wantSubstring}`);
  console.log(out.split("\n").map((l) => `        | ${l}`).join("\n"));
}

console.log(`checker: ${CHECKER}`);
console.log(`topology tiers: ${topology.tiers.map((t) => t.crate).join(", ")}`);
console.log(
  `fresh census: drc=${DRC_BUILT} (7 shards), geometry=${GEOMETRY_BUILT}, thermal=${THERMAL_BUILT}\n`,
);

// ---------------------------------------------------------------------------
// 1. The control passes when everything is current. Without this the rest of
//    the file could be satisfied by a checker that always fails.
// ---------------------------------------------------------------------------
console.log("A. correct counts -> green");
expect(
  "all three tiers current",
  run(ALL_BUILT, freshCensus()),
  0,
  "every tier's deployed corpus matches",
);

// ---------------------------------------------------------------------------
// 2. THE BITE. Each crate's deployed count must equal its own built count, and
//    a divergence in either one must fail on its own.
// ---------------------------------------------------------------------------
console.log("\nB. a stale deployed count -> red, per crate");
{
  const stale = freshCensus();
  stale["temper-wasm-geometry"] = { test_count: GEOMETRY_BUILT - 22, abi_version: 1 };
  expect(
    "temper-geometry deployed 22 short",
    run(ALL_BUILT, stale),
    1,
    "STALE DEPLOYED CORPUS (temper-geometry)",
  );
}
{
  const stale = freshCensus();
  stale["temper-wasm-tier"] = { test_count: DRC_BUILT - 11, abi_version: 1 };
  expect(
    "temper-drc-rs deployed 11 short (the real 2026-08-10 gap)",
    run(ALL_BUILT, stale),
    1,
    "STALE DEPLOYED CORPUS (temper-drc-rs)",
  );
}
{
  // The dispatched path, not the headline number: temper-wasm-tier is fresh
  // while a shard the sweep actually calls is behind.
  const stale = freshCensus();
  stale["temper-wasm-infra"] = { test_count: 110, abi_version: 1 };
  expect(
    "temper-drc-rs shards no longer partition (infra behind)",
    run(ALL_BUILT, stale),
    1,
    "STALE OR NON-PARTITIONING FAMILY SHARDS (temper-drc-rs)",
  );
}
{
  // temper-thermal's own bite, at the size the gap would realistically be:
  // the four b7-pow-divergence-absent tests are the crate's newest and most
  // fragile, so a module 4 behind is a module missing exactly the tests whose
  // absence is least visible in an aggregate.
  const stale = freshCensus();
  stale["temper-wasm-thermal"] = { test_count: THERMAL_BUILT - 4, abi_version: 1 };
  expect(
    "temper-thermal deployed 4 short",
    run(ALL_BUILT, stale),
    1,
    "STALE DEPLOYED CORPUS (temper-thermal)",
  );
}
{
  // The other direction: a Worker still carrying a corpus this commit no
  // longer builds. Deleting a test and not redeploying is as much a staleness
  // bug as adding one, and the message must say so rather than reporting a
  // shortfall percentage over 100%.
  const stale = freshCensus();
  stale["temper-wasm-thermal"] = { test_count: THERMAL_BUILT + 2, abi_version: 1 };
  expect(
    "temper-thermal deployed 2 long (deleted tests still live)",
    run(ALL_BUILT, stale),
    1,
    "are not in this commit's temper-thermal build",
  );
}
{
  // Registered-vs-executable, the trap this tier has now hit twice: geometry
  // registers 724 and executes 722, thermal registers 145 and executes 143.
  // Handing the checker the REGISTERED number is the natural mistake, and it
  // must be a loud failure rather than a rounding difference nobody notices.
  const stale = freshCensus();
  expect(
    "thermal built count given as 145 registered, not 143 executable",
    run(
      ["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY, "--expected-count-thermal", "145"],
      stale,
    ),
    1,
    "STALE DEPLOYED CORPUS (temper-thermal)",
  );
}

// ---------------------------------------------------------------------------
// 3. NO CROSS-CRATE CANCELLATION. This is the case a naive "everything sums to
//    the total" generalisation would have passed: drc is 11 short, geometry is
//    11 long, the union is exactly right, and BOTH modules are stale.
// ---------------------------------------------------------------------------
console.log("\nC. offsetting drift across crates -> still red (no cancellation)");
{
  const stale = freshCensus();
  stale["temper-wasm-tier"] = { test_count: DRC_BUILT - 11, abi_version: 1 };
  stale["temper-wasm-drc"] = { test_count: DRC_SHARDS.drc - 11, abi_version: 1 };
  stale["temper-wasm-geometry"] = { test_count: GEOMETRY_BUILT + 11, abi_version: 1 };
  const res = run(ALL_BUILT, stale);
  expect("union total unchanged, both crates wrong", res, 1, "STALE DEPLOYED CORPUS (temper-drc-rs)");
  expect("  ...and the geometry tier is named too", res, 1, "STALE DEPLOYED CORPUS (temper-geometry)");
}
{
  // The three-crate version, which is the case a union check would now pass
  // most easily: thermal is the smallest tier, so its whole corpus is smaller
  // than the drift a drc-vs-geometry cancellation can absorb. drc is 7 short,
  // geometry 4 long, thermal 3 long -- union total identical, three stale
  // modules, and every one of them must be named.
  const stale = freshCensus();
  stale["temper-wasm-tier"] = { test_count: DRC_BUILT - 7, abi_version: 1 };
  stale["temper-wasm-drc"] = { test_count: DRC_SHARDS.drc - 7, abi_version: 1 };
  stale["temper-wasm-geometry"] = { test_count: GEOMETRY_BUILT + 4, abi_version: 1 };
  stale["temper-wasm-thermal"] = { test_count: THERMAL_BUILT + 3, abi_version: 1 };
  const res = run(ALL_BUILT, stale);
  expect("three-way cancellation, union unchanged", res, 1, "STALE DEPLOYED CORPUS (temper-drc-rs)");
  expect("  ...geometry named", res, 1, "STALE DEPLOYED CORPUS (temper-geometry)");
  expect("  ...thermal named", res, 1, "STALE DEPLOYED CORPUS (temper-thermal)");
}

// ---------------------------------------------------------------------------
// 4. THE CHECK CANNOT BE SWITCHED OFF BY OMITTING AN ARGUMENT. A tier with no
//    built count is a usage error naming that tier -- never a narrower run that
//    exits 0 having checked one crate.
// ---------------------------------------------------------------------------
console.log("\nD. a tier with no built count -> exit 2, never a quiet pass");
expect(
  "--built-json-geometry omitted",
  run(["--built-json", BUILT_DRC, "--built-json-thermal", BUILT_THERMAL], freshCensus()),
  2,
  "No expected test count available for tier temper-geometry",
);
expect(
  "--built-json omitted",
  run(["--built-json-geometry", BUILT_GEOMETRY, "--built-json-thermal", BUILT_THERMAL], freshCensus()),
  2,
  "No expected test count available for tier temper-drc-rs",
);
// The case this PR is: a tier joins the topology and a caller keeps passing the
// arguments it passed yesterday. That must not be "check the two crates I was
// given" -- it is exactly how a Worker ends up deployed, swept, and proven
// current by nothing.
expect(
  "--built-json-thermal omitted (the pre-existing callers' argument set)",
  run(["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY], freshCensus()),
  2,
  "No expected test count available for tier temper-thermal",
);
// ...and it stays exit 2 even when the thermal Worker is perfectly current, so
// the failure is about the MISSING ARGUMENT, not about anything observable at
// the edge. A checker that quietly passed here would be one redeploy away from
// passing when it was not.
expect(
  "  ...even with temper-wasm-thermal deployed and correct",
  run(["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY], freshCensus()),
  2,
  "there is deliberately no flag that skips one",
);
expect("no counts at all", run([], freshCensus()), 2, "No expected test count available");
// An unreadable census file is a usage error too, not a reason to assume a
// count. wasm-tier-nightly.yml passes a path into a downloaded artifact; if
// local-sweep-r19 died before building thermal's module, that path does not
// exist and this must not become "thermal is fine".
expect(
  "--built-json-thermal pointing at a file that does not exist",
  run(
    ["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY, "--built-json-thermal", join(TMP, "nope.json")],
    freshCensus(),
  ),
  2,
  "Cannot read the built-corpus census for temper-thermal",
);

// ---------------------------------------------------------------------------
// 5. Unreachable and ABI-mismatched Workers still fail rather than being
//    treated as absent. Includes the state this PR leaves the tier in until the
//    operator deploys: temper-wasm-geometry does not exist yet.
// ---------------------------------------------------------------------------
console.log("\nE. unreachable / wrong ABI -> red");
{
  const census = freshCensus();
  delete census["temper-wasm-geometry"];
  expect(
    "temper-wasm-geometry not deployed yet",
    run(ALL_BUILT, census),
    1,
    "did not report a usable /health census",
  );
}
{
  const census = freshCensus();
  census["temper-wasm-geometry"] = { test_count: GEOMETRY_BUILT, abi_version: 2 };
  expect(
    "temper-wasm-geometry speaks ABI 2",
    run(ALL_BUILT, census),
    1,
    "ABI mismatch",
  );
}
{
  // The state this PR leaves the tier in until the operator deploys:
  // temper-wasm-thermal is in the topology and does not exist yet. It must fail
  // as "unreachable", loudly and by name — never be treated as a Worker with
  // nothing to say.
  const census = freshCensus();
  delete census["temper-wasm-thermal"];
  const res = run(ALL_BUILT, census);
  expect("temper-wasm-thermal not deployed yet", res, 1, "did not report a usable /health census");
  expect("  ...and it is named in the failure", res, 1, "temper-wasm-thermal");
}
{
  const census = freshCensus();
  census["temper-wasm-thermal"] = { test_count: THERMAL_BUILT, abi_version: 2 };
  expect(
    "temper-wasm-thermal speaks ABI 2",
    run(ALL_BUILT, census),
    1,
    "ABI mismatch",
  );
}

// ---------------------------------------------------------------------------
// 6. --expected-count overrides behave per tier.
// ---------------------------------------------------------------------------
console.log("\nF. --expected-count overrides, per tier");
const ALL_COUNTS = [
  "--expected-count",
  String(DRC_BUILT),
  "--expected-count-geometry",
  String(GEOMETRY_BUILT),
  "--expected-count-thermal",
  String(THERMAL_BUILT),
];
expect(
  "overrides matching the deployed counts",
  run(ALL_COUNTS, freshCensus()),
  0,
  "every tier's deployed corpus matches",
);
expect(
  "geometry override NOT matching the deployed count",
  run(["--expected-count", String(DRC_BUILT), "--expected-count-geometry", "999", "--expected-count-thermal", String(THERMAL_BUILT)], freshCensus()),
  1,
  "STALE DEPLOYED CORPUS (temper-geometry)",
);
expect(
  "thermal override NOT matching the deployed count",
  run(["--expected-count", String(DRC_BUILT), "--expected-count-geometry", String(GEOMETRY_BUILT), "--expected-count-thermal", "999"], freshCensus()),
  1,
  "STALE DEPLOYED CORPUS (temper-thermal)",
);

console.log(
  failures === 0
    ? "\nAll cases passed: the freshness check goes green on a current tier and red on every divergence above."
    : `\n${failures} case(s) FAILED.`,
);
process.exit(failures === 0 ? 0 : 1);
