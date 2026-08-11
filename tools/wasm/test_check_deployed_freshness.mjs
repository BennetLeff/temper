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
 * Per-shard numbers are today's deployed reality (2026-08-11): drc 1510, infra
 * 121, safety 25, placement 18, routing 18, emc 15, erc 12 = 1719,
 * temper-wasm-geometry's 722, temper-wasm-thermal's 143,
 * temper-wasm-router-core's 111, temper-wasm-constraint-compiler's 69,
 * temper-wasm-design-bundle's 24, temper-wasm-quality-oracle's 125 and
 * temper-wasm-io-types's 144. Eight tiers, 3057 tests.
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
// The three tiers added 2026-08-11, all EXECUTABLE counts (`summary.registered`
// from run_wasm_tests.mjs, i.e. `temper_test_count()` of the built module), for
// the same reason THERMAL_BUILT is:
//
//   temper-design-bundle        24 registered, 24 executable -- the one tier
//                               where the two coincide, because its registry
//                               has no `cfg`-carrying entry. Pinned here so
//                               that stops being an assumption.
//   temper-rust-router-core    111 registered, 111 executable, 111 passing.
//                               This number is the sharpest available
//                               illustration of issue #945, the known
//                               limitation of this control: on 2026-08-10 the
//                               same 111 was 88 pass + 23 expected-fail
//                               (`no-clock`), on 2026-08-11 #947 made the
//                               rewrite trace clock lazy and all 23 became
//                               passes -- and THIS CHECK CANNOT SEE THAT. It
//                               was 111 before and 111 after. Verdict changes
//                               are run_wasm_tests.mjs's job (an
//                               unexpected-pass is a non-zero exit) and
//                               r19_compare.py's; a count check is blind to
//                               them by construction, which is exactly what
//                               #945 says and why it is not papered over here.
//   temper-constraint-compiler  70 registered, 69 executable. The 70th,
//                               constraints::tests::
//                               host_libm_symbols_actually_resolve, carries
//                               `#[cfg(not(target_arch = "wasm32"))]`, so it is
//                               compiled out rather than skipped.
const DESIGN_BUNDLE_BUILT = 24;
const ROUTER_CORE_BUILT = 111;
const CONSTRAINT_COMPILER_BUILT = 69;
// The two tiers added after the six above (job: "deploy the last two
// registered crates"). Both EXECUTABLE counts, for the same reason every
// other BUILT constant above is:
//
//   temper-quality-oracle  126 registered, 125 executable. The 126th,
//                          placement_metrics::tests::
//                          py_pow_resolves_to_host_libm_not_sqrt, carries
//                          `#[cfg(not(target_arch = "wasm32"))]` — same shape
//                          as temper-geometry's 724/722 and
//                          temper-constraint-compiler's 70/69 gaps.
//   temper-io-types        144 registered, 144 executable — coincide, like
//                          temper-design-bundle's 24/24, because no registry
//                          entry in this crate carries its own cfg.
const QUALITY_ORACLE_BUILT = 125;
const IO_TYPES_BUILT = 144;

/**
 * Content-hash identity (issue #945), one fixed fake digest per full-corpus
 * Worker. Not real sha256 hex — check_deployed_freshness.mjs never validates
 * the shape of `summary.sha256` / `module_sha256`, only compares them for
 * equality, so a readable tag serves the same purpose as a real hash and
 * keeps the diffs in section G legible. Only full-corpus Workers get one:
 * the digest check is scoped to `full_corpus_worker` per tier (see
 * check_deployed_freshness.mjs's header, "CONTENT HASH" — the shard-sum
 * partition check has no digest analogue), so temper-drc-rs's seven shards
 * (drc, emc, erc, safety, placement, routing, infra) never carry one.
 */
const DRC_SHA = "sha-drc-rs-fresh";
const GEOMETRY_SHA = "sha-geometry-fresh";
const THERMAL_SHA = "sha-thermal-fresh";
const DESIGN_BUNDLE_SHA = "sha-design-bundle-fresh";
const ROUTER_CORE_SHA = "sha-router-core-fresh";
const CONSTRAINT_COMPILER_SHA = "sha-constraint-compiler-fresh";
const QUALITY_ORACLE_SHA = "sha-quality-oracle-fresh";
const IO_TYPES_SHA = "sha-io-types-fresh";

function freshCensus() {
  const census = {
    "temper-wasm-tier": { test_count: DRC_BUILT, abi_version: 1, module_sha256: DRC_SHA },
  };
  for (const [family, count] of Object.entries(DRC_SHARDS)) {
    census[`temper-wasm-${family}`] = { test_count: count, abi_version: 1 };
  }
  census["temper-wasm-geometry"] = { test_count: GEOMETRY_BUILT, abi_version: 1, module_sha256: GEOMETRY_SHA };
  census["temper-wasm-thermal"] = { test_count: THERMAL_BUILT, abi_version: 1, module_sha256: THERMAL_SHA };
  census["temper-wasm-design-bundle"] = {
    test_count: DESIGN_BUNDLE_BUILT,
    abi_version: 1,
    module_sha256: DESIGN_BUNDLE_SHA,
  };
  census["temper-wasm-router-core"] = {
    test_count: ROUTER_CORE_BUILT,
    abi_version: 1,
    module_sha256: ROUTER_CORE_SHA,
  };
  census["temper-wasm-constraint-compiler"] = {
    test_count: CONSTRAINT_COMPILER_BUILT,
    abi_version: 1,
    module_sha256: CONSTRAINT_COMPILER_SHA,
  };
  census["temper-wasm-quality-oracle"] = {
    test_count: QUALITY_ORACLE_BUILT,
    abi_version: 1,
    module_sha256: QUALITY_ORACLE_SHA,
  };
  census["temper-wasm-io-types"] = {
    test_count: IO_TYPES_BUILT,
    abi_version: 1,
    module_sha256: IO_TYPES_SHA,
  };
  return census;
}

/**
 * Write a run_wasm_tests.mjs-shaped census file and return its path.
 * `sha256`, when given, lands in `summary.sha256` exactly where
 * check_deployed_freshness.mjs's `builtCountFor` reads it (issue #945) —
 * omit it to exercise the "missing built digest" soft-pass path (section G).
 */
function builtJson(name, registered, sha256) {
  const path = join(TMP, `${name}.json`);
  const summary = sha256 !== undefined ? { registered, sha256 } : { registered };
  writeFileSync(path, JSON.stringify({ summary, results: [] }));
  return path;
}

const BUILT_DRC = builtJson("built_drc", DRC_BUILT, DRC_SHA);
const BUILT_GEOMETRY = builtJson("built_geometry", GEOMETRY_BUILT, GEOMETRY_SHA);
const BUILT_THERMAL = builtJson("built_thermal", THERMAL_BUILT, THERMAL_SHA);
const BUILT_DESIGN_BUNDLE = builtJson("built_design_bundle", DESIGN_BUNDLE_BUILT, DESIGN_BUNDLE_SHA);
const BUILT_ROUTER_CORE = builtJson("built_router_core", ROUTER_CORE_BUILT, ROUTER_CORE_SHA);
const BUILT_CONSTRAINT_COMPILER = builtJson(
  "built_constraint_compiler",
  CONSTRAINT_COMPILER_BUILT,
  CONSTRAINT_COMPILER_SHA,
);
const BUILT_QUALITY_ORACLE = builtJson("built_quality_oracle", QUALITY_ORACLE_BUILT, QUALITY_ORACLE_SHA);
const BUILT_IO_TYPES = builtJson("built_io_types", IO_TYPES_BUILT, IO_TYPES_SHA);

/**
 * The full, correct argument set: one built count per tier in the topology.
 * Spelled as a constant rather than repeated per case so that adding a tier is
 * one edit here — and so the cases in section D, which deliberately drop one
 * flag, are visibly the exception rather than indistinguishable from an
 * oversight.
 *
 * The flag suffixes are `tierFlagSuffix(crate)` — the crate name minus the
 * leading `temper-`, `-` kept. Note `--built-json-rust-router-core` rather than
 * `--built-json-router-core`: the crate is `temper-rust-router-core` while its
 * Worker, family and staged module are all `router-core`. Writing the shorter
 * one is the natural mistake, and it is not a silent one — the checker would
 * exit 2 saying temper-rust-router-core has no count, which is the guard-rail
 * working. The COVERAGE ASSERTION below derives the crate names from these
 * flags, so it would catch it here too.
 */
const ALL_BUILT = [
  "--built-json",
  BUILT_DRC,
  "--built-json-geometry",
  BUILT_GEOMETRY,
  "--built-json-thermal",
  BUILT_THERMAL,
  "--built-json-design-bundle",
  BUILT_DESIGN_BUNDLE,
  "--built-json-rust-router-core",
  BUILT_ROUTER_CORE,
  "--built-json-constraint-compiler",
  BUILT_CONSTRAINT_COMPILER,
  "--built-json-quality-oracle",
  BUILT_QUALITY_ORACLE,
  "--built-json-io-types",
  BUILT_IO_TYPES,
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

/**
 * ALL_BUILT plus one `--expected-count-<suffix>` override. The checker lets an
 * explicit count win over the census file for that tier (and says so on stderr),
 * so this exercises a wrong count for ONE tier while every other tier is still
 * supplied — which is what makes the resulting failure attributable to the
 * count rather than to a missing argument. Dropping the tier's --built-json
 * instead would work too, but then a regression that made the checker skip
 * unsupplied tiers would show up as a PASS here rather than in section D.
 */
function withOverride(flag, value) {
  return [...ALL_BUILT, flag, value];
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
  `fresh census: drc=${DRC_BUILT} (7 shards), geometry=${GEOMETRY_BUILT}, ` +
    `thermal=${THERMAL_BUILT}, design-bundle=${DESIGN_BUNDLE_BUILT}, ` +
    `router-core=${ROUTER_CORE_BUILT}, constraint-compiler=${CONSTRAINT_COMPILER_BUILT}, ` +
    `quality-oracle=${QUALITY_ORACLE_BUILT}, io-types=${IO_TYPES_BUILT}\n`,
);

// ---------------------------------------------------------------------------
// 1. The control passes when everything is current. Without this the rest of
//    the file could be satisfied by a checker that always fails.
// ---------------------------------------------------------------------------
console.log("A. correct counts -> green");
expect(
  "all eight tiers current",
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
  // Registered-vs-executable, the trap this tier has now hit three times:
  // geometry registers 724 and executes 722, thermal 145/143, and
  // constraint-compiler 70/69. Handing the checker the REGISTERED number is the
  // natural mistake, and it must be a loud failure rather than a rounding
  // difference nobody notices.
  const stale = freshCensus();
  expect(
    "thermal built count given as 145 registered, not 143 executable",
    run(withOverride("--expected-count-thermal", "145"), stale),
    1,
    "STALE DEPLOYED CORPUS (temper-thermal)",
  );
}
{
  // The same trap on the newest tier to carry it: temper-constraint-compiler's
  // registry names 70 tests and the wasm32 module carries 69, because
  // constraints::tests::host_libm_symbols_actually_resolve is
  // `#[cfg(not(target_arch = "wasm32"))]` and is compiled out. 70 is the number
  // a reader gets by counting the registry file, which is why this case exists.
  const stale = freshCensus();
  expect(
    "constraint-compiler built count given as 70 registered, not 69 executable",
    run(withOverride("--expected-count-constraint-compiler", "70"), stale),
    1,
    "STALE DEPLOYED CORPUS (temper-constraint-compiler)",
  );
}
{
  // temper-design-bundle's own bite. This is the smallest tier on the wasm
  // tier (24 tests), and small is the point: a 24-test corpus is well inside
  // the noise of a 2788-test total, so if the invariant were ever restated over
  // a union this whole crate could go stale without moving the headline enough
  // to notice. Per tier, 4 missing tests out of 24 is a named failure.
  const stale = freshCensus();
  stale["temper-wasm-design-bundle"] = {
    test_count: DESIGN_BUNDLE_BUILT - 4,
    abi_version: 1,
  };
  expect(
    "temper-design-bundle deployed 4 short",
    run(ALL_BUILT, stale),
    1,
    "STALE DEPLOYED CORPUS (temper-design-bundle)",
  );
}
{
  // The degenerate-shard trap, at the one place it could bite: for a
  // single-family tier the shard IS the full-corpus Worker, so a wrong count
  // must produce BOTH failures for that tier rather than one. If a future
  // refactor deduplicated the two checks by script name instead of by tier, the
  // partition message would silently stop being emitted, and the day one of
  // these crates is sharded by size that check would be gone.
  const stale = freshCensus();
  stale["temper-wasm-design-bundle"] = {
    test_count: DESIGN_BUNDLE_BUILT - 4,
    abi_version: 1,
  };
  expect(
    "  ...and its singleton shard set is reported as non-partitioning too",
    run(ALL_BUILT, stale),
    1,
    "STALE OR NON-PARTITIONING FAMILY SHARDS (temper-design-bundle)",
  );
}
{
  // temper-rust-router-core deployed one test short. 1, not 4, deliberately:
  // the smallest possible drift must fail exactly as loudly as a large one,
  // because the realistic drift is "someone added a test and did not redeploy"
  // and the newest test is the one the tier has never run.
  const stale = freshCensus();
  stale["temper-wasm-router-core"] = { test_count: ROUTER_CORE_BUILT - 1, abi_version: 1 };
  const res = run(ALL_BUILT, stale);
  expect(
    "temper-rust-router-core deployed 1 short",
    res,
    1,
    "STALE DEPLOYED CORPUS (temper-rust-router-core)",
  );
  // ...and the singular/plural branch in the message is exercised by it.
  expect("  ...and the message says '1 ... is missing', not '1 tests are'", res, 1, "is missing from");
}
{
  // temper-constraint-compiler deployed LONG: a Worker still carrying tests
  // this commit no longer builds. Deleting a test and not redeploying is as
  // much a staleness bug as adding one.
  const stale = freshCensus();
  stale["temper-wasm-constraint-compiler"] = {
    test_count: CONSTRAINT_COMPILER_BUILT + 5,
    abi_version: 1,
  };
  expect(
    "temper-constraint-compiler deployed 5 long (deleted tests still live)",
    run(ALL_BUILT, stale),
    1,
    "are not in this commit's temper-constraint-compiler build",
  );
}
{
  // temper-quality-oracle's own bite: the last of the two crates this PR
  // deploys a Worker for.
  const stale = freshCensus();
  stale["temper-wasm-quality-oracle"] = { test_count: QUALITY_ORACLE_BUILT - 3, abi_version: 1 };
  expect(
    "temper-quality-oracle deployed 3 short",
    run(ALL_BUILT, stale),
    1,
    "STALE DEPLOYED CORPUS (temper-quality-oracle)",
  );
}
{
  // Registered-vs-executable on temper-quality-oracle, the trap this tier has
  // now hit four times: geometry 724/722, thermal 145/143,
  // constraint-compiler 70/69, and this crate 126/125
  // (placement_metrics::tests::py_pow_resolves_to_host_libm_not_sqrt carries
  // its own `#[cfg(not(target_arch = "wasm32"))]`). Handing the checker the
  // REGISTERED number is the natural mistake reading the registry file
  // invites, and it must be a loud failure.
  const stale = freshCensus();
  expect(
    "quality-oracle built count given as 126 registered, not 125 executable",
    run(withOverride("--expected-count-quality-oracle", "126"), stale),
    1,
    "STALE DEPLOYED CORPUS (temper-quality-oracle)",
  );
}
{
  // temper-io-types deployed short. Registered and executable coincide at 144
  // for this crate (like temper-design-bundle's 24/24), so this is a plain
  // drift case rather than a registered-vs-executable trap.
  const stale = freshCensus();
  stale["temper-wasm-io-types"] = { test_count: IO_TYPES_BUILT - 2, abi_version: 1 };
  expect(
    "temper-io-types deployed 2 short",
    run(ALL_BUILT, stale),
    1,
    "STALE DEPLOYED CORPUS (temper-io-types)",
  );
}
{
  // The other direction on temper-io-types: deployed LONG.
  const stale = freshCensus();
  stale["temper-wasm-io-types"] = { test_count: IO_TYPES_BUILT + 6, abi_version: 1 };
  expect(
    "temper-io-types deployed 6 long (deleted tests still live)",
    run(ALL_BUILT, stale),
    1,
    "are not in this commit's temper-io-types build",
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
{
  // The six-crate version, and the one that shows why adding tiers makes a
  // union check WORSE rather than merely no better. Every tier drifts, the
  // signs are chosen so the union total is identical (-156 +22 +7 -24 +111 +40
  // = 0), and two of the drifts are a whole crate's corpus: temper-design-
  // bundle's Worker is serving an EMPTY registry (24 -> 0) and
  // temper-wasm-router-core is serving DOUBLE its corpus (111 -> 222). A union
  // check passes this. Per tier, all six must be named, and a tier whose shard
  // set is the singleton {itself} must additionally be named as
  // non-partitioning.
  const stale = freshCensus();
  stale["temper-wasm-tier"] = { test_count: DRC_BUILT - 156, abi_version: 1 };
  stale["temper-wasm-drc"] = { test_count: DRC_SHARDS.drc - 156, abi_version: 1 };
  stale["temper-wasm-geometry"] = { test_count: GEOMETRY_BUILT + 22, abi_version: 1 };
  stale["temper-wasm-thermal"] = { test_count: THERMAL_BUILT + 7, abi_version: 1 };
  stale["temper-wasm-design-bundle"] = { test_count: 0, abi_version: 1 };
  stale["temper-wasm-router-core"] = { test_count: ROUTER_CORE_BUILT * 2, abi_version: 1 };
  stale["temper-wasm-constraint-compiler"] = {
    test_count: CONSTRAINT_COMPILER_BUILT + 40,
    abi_version: 1,
  };
  // The arithmetic this case rests on, asserted rather than trusted: if a
  // future edit changed one of the numbers above the case would quietly stop
  // being a cancellation and would pass for the wrong reason.
  const builtTotal =
    DRC_BUILT + GEOMETRY_BUILT + THERMAL_BUILT + DESIGN_BUNDLE_BUILT + ROUTER_CORE_BUILT +
    CONSTRAINT_COMPILER_BUILT;
  const deployedTotal = [
    "temper-wasm-tier",
    "temper-wasm-geometry",
    "temper-wasm-thermal",
    "temper-wasm-design-bundle",
    "temper-wasm-router-core",
    "temper-wasm-constraint-compiler",
  ].reduce((a, s) => a + stale[s].test_count, 0);
  if (builtTotal !== deployedTotal) {
    console.error(
      `six-way cancellation case is malformed: built total ${builtTotal} != deployed total ` +
        `${deployedTotal}. The case is only meaningful if a union check would PASS it; as ` +
        "written a union check would fail it too, and it would prove nothing about per-tier.",
    );
    process.exit(1);
  }
  const res = run(ALL_BUILT, stale);
  expect(
    `six-way cancellation, union total identical at ${builtTotal}`,
    res,
    1,
    "STALE DEPLOYED CORPUS (temper-drc-rs)",
  );
  expect("  ...geometry named", res, 1, "STALE DEPLOYED CORPUS (temper-geometry)");
  expect("  ...thermal named", res, 1, "STALE DEPLOYED CORPUS (temper-thermal)");
  expect("  ...design-bundle named (deployed corpus is empty)", res, 1, "STALE DEPLOYED CORPUS (temper-design-bundle)");
  expect("  ...router-core named (deployed corpus is double)", res, 1, "STALE DEPLOYED CORPUS (temper-rust-router-core)");
  expect("  ...constraint-compiler named", res, 1, "STALE DEPLOYED CORPUS (temper-constraint-compiler)");
  expect(
    "  ...and design-bundle's singleton shard set is non-partitioning too",
    res,
    1,
    "STALE OR NON-PARTITIONING FAMILY SHARDS (temper-design-bundle)",
  );
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
// THE CASE THIS PR IS. Yesterday's complete argument set -- drc + geometry +
// thermal, which is exactly what wasm-tier-nightly.yml passed before this
// change -- against a topology that now has six tiers. It must be exit 2, and
// it must name a tier, not check three crates in green. Tiers are evaluated in
// topology order and the first miss is fatal, so design-bundle is the one
// named; the two cases below walk the caller forward one flag at a time and
// show that each remaining tier is named in turn rather than the check quietly
// narrowing once "most" of the flags are present.
const YESTERDAYS_ARGS = [
  "--built-json",
  BUILT_DRC,
  "--built-json-geometry",
  BUILT_GEOMETRY,
  "--built-json-thermal",
  BUILT_THERMAL,
];
expect(
  "the pre-existing three-tier argument set against a six-tier topology",
  run(YESTERDAYS_ARGS, freshCensus()),
  2,
  "No expected test count available for tier temper-design-bundle",
);
expect(
  "  ...+ design-bundle: now router-core is named",
  run([...YESTERDAYS_ARGS, "--built-json-design-bundle", BUILT_DESIGN_BUNDLE], freshCensus()),
  2,
  "No expected test count available for tier temper-rust-router-core",
);
expect(
  "  ...+ router-core: now constraint-compiler is named",
  run(
    [
      ...YESTERDAYS_ARGS,
      "--built-json-design-bundle",
      BUILT_DESIGN_BUNDLE,
      "--built-json-rust-router-core",
      BUILT_ROUTER_CORE,
    ],
    freshCensus(),
  ),
  2,
  "No expected test count available for tier temper-constraint-compiler",
);
// The flag-name trap this tier's naming makes available: the crate is
// `temper-rust-router-core` but its Worker, family and staged module are all
// `router-core`, so `--built-json-router-core` is the natural thing to type and
// is NOT a flag. It must fail as a missing count for the real crate rather than
// being silently accepted for something.
expect(
  "--built-json-router-core (the plausible wrong suffix) is not a flag",
  run(
    [
      ...YESTERDAYS_ARGS,
      "--built-json-design-bundle",
      BUILT_DESIGN_BUNDLE,
      "--built-json-router-core",
      BUILT_ROUTER_CORE,
      "--built-json-constraint-compiler",
      BUILT_CONSTRAINT_COMPILER,
    ],
    freshCensus(),
  ),
  2,
  "No expected test count available for tier temper-rust-router-core",
);
// An unreadable census file, on the newest tier: wasm-tier-nightly.yml passes
// paths into a downloaded artifact, and if local-sweep-r19 died before building
// router-core's module that path does not exist. It must not become
// "router-core is fine".
expect(
  "--built-json-rust-router-core pointing at a file that does not exist",
  run(
    [
      ...YESTERDAYS_ARGS,
      "--built-json-design-bundle",
      BUILT_DESIGN_BUNDLE,
      "--built-json-rust-router-core",
      join(TMP, "nope.json"),
      "--built-json-constraint-compiler",
      BUILT_CONSTRAINT_COMPILER,
    ],
    freshCensus(),
  ),
  2,
  "Cannot read the built-corpus census for temper-rust-router-core",
);
// The walk continues past the original six-tier topology into the two
// crates this PR adds: quality-oracle, then io-types. Same property as
// above, restated at eight tiers -- a caller that has caught up to exactly
// yesterday's complete flag set is still exit 2, one named tier at a time,
// never a quiet pass over six of eight.
expect(
  "  ...+ constraint-compiler: now quality-oracle is named",
  run(
    [
      ...YESTERDAYS_ARGS,
      "--built-json-design-bundle",
      BUILT_DESIGN_BUNDLE,
      "--built-json-rust-router-core",
      BUILT_ROUTER_CORE,
      "--built-json-constraint-compiler",
      BUILT_CONSTRAINT_COMPILER,
    ],
    freshCensus(),
  ),
  2,
  "No expected test count available for tier temper-quality-oracle",
);
expect(
  "  ...+ quality-oracle: now io-types is named",
  run(
    [
      ...YESTERDAYS_ARGS,
      "--built-json-design-bundle",
      BUILT_DESIGN_BUNDLE,
      "--built-json-rust-router-core",
      BUILT_ROUTER_CORE,
      "--built-json-constraint-compiler",
      BUILT_CONSTRAINT_COMPILER,
      "--built-json-quality-oracle",
      BUILT_QUALITY_ORACLE,
    ],
    freshCensus(),
  ),
  2,
  "No expected test count available for tier temper-io-types",
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
{
  // The state THIS PR leaves the tier in until the operator deploys: all three
  // of the new Workers are in the topology and none of them exists. All three
  // must be named in one failure — not just the first — because an operator
  // reading "temper-wasm-design-bundle (HTTP 404)" and deploying only that one
  // would be back here twice more. This is also the run that proves the change
  // is live: on this branch, against the real tier, the checker exits 1 saying
  // exactly this.
  const census = freshCensus();
  delete census["temper-wasm-design-bundle"];
  delete census["temper-wasm-router-core"];
  delete census["temper-wasm-constraint-compiler"];
  const res = run(ALL_BUILT, census);
  expect("none of the three new Workers deployed yet", res, 1, "did not report a usable /health census");
  expect("  ...design-bundle named", res, 1, "temper-wasm-design-bundle (HTTP 404)");
  expect("  ...router-core named", res, 1, "temper-wasm-router-core (HTTP 404)");
  expect("  ...constraint-compiler named", res, 1, "temper-wasm-constraint-compiler (HTTP 404)");
}
{
  // An unreachable Worker must beat a stale count to the failure, and must not
  // be silently downgraded to one: the census is incomplete, so no comparison
  // is available at all. design-bundle is absent AND router-core is stale here;
  // the run must fail on the census, not report a partial verdict.
  const census = freshCensus();
  delete census["temper-wasm-design-bundle"];
  census["temper-wasm-router-core"] = { test_count: 1, abi_version: 1 };
  const res = run(ALL_BUILT, census);
  expect(
    "an unreachable Worker fails the whole census, not just its tier",
    res,
    1,
    "The staleness comparison cannot be made",
  );
}
{
  const census = freshCensus();
  census["temper-wasm-router-core"] = { test_count: ROUTER_CORE_BUILT, abi_version: 2 };
  expect(
    "temper-wasm-router-core speaks ABI 2",
    run(ALL_BUILT, census),
    1,
    "ABI mismatch",
  );
}
{
  // The state THIS PR (job 1 — "deploy the last two registered crates") leaves
  // the tier in until the operator deploys: temper-wasm-quality-oracle and
  // temper-wasm-io-types are in the topology and neither exists yet. Both must
  // be named in one failure, for the same reason the three-Worker case above
  // names all three.
  const census = freshCensus();
  delete census["temper-wasm-quality-oracle"];
  delete census["temper-wasm-io-types"];
  const res = run(ALL_BUILT, census);
  expect("neither of the two newest Workers deployed yet", res, 1, "did not report a usable /health census");
  expect("  ...quality-oracle named", res, 1, "temper-wasm-quality-oracle (HTTP 404)");
  expect("  ...io-types named", res, 1, "temper-wasm-io-types (HTTP 404)");
}
{
  const census = freshCensus();
  census["temper-wasm-quality-oracle"] = { test_count: QUALITY_ORACLE_BUILT, abi_version: 2 };
  expect(
    "temper-wasm-quality-oracle speaks ABI 2",
    run(ALL_BUILT, census),
    1,
    "ABI mismatch",
  );
}
{
  const census = freshCensus();
  census["temper-wasm-io-types"] = { test_count: IO_TYPES_BUILT, abi_version: 2 };
  expect(
    "temper-wasm-io-types speaks ABI 2",
    run(ALL_BUILT, census),
    1,
    "ABI mismatch",
  );
}

// ---------------------------------------------------------------------------
// 6. --expected-count overrides behave per tier.
// ---------------------------------------------------------------------------
console.log("\nF. --expected-count overrides, per tier");
/** Every tier's count as an explicit override, with one substituted. */
function allCounts(overrides = {}) {
  const base = {
    "temper-drc-rs": DRC_BUILT,
    "temper-geometry": GEOMETRY_BUILT,
    "temper-thermal": THERMAL_BUILT,
    "temper-design-bundle": DESIGN_BUNDLE_BUILT,
    "temper-rust-router-core": ROUTER_CORE_BUILT,
    "temper-constraint-compiler": CONSTRAINT_COMPILER_BUILT,
    "temper-quality-oracle": QUALITY_ORACLE_BUILT,
    "temper-io-types": IO_TYPES_BUILT,
  };
  return Object.entries({ ...base, ...overrides }).flatMap(([crate, n]) => [
    // temper-drc-rs is additionally reachable as the unsuffixed flag, and this
    // uses the SUFFIXED one for every tier including it — so these cases prove
    // the general form works, not just the two grandfathered aliases.
    `--expected-count-${crate.replace(/^temper-/, "")}`,
    String(n),
  ]);
}
expect(
  "overrides matching the deployed counts",
  run(allCounts(), freshCensus()),
  0,
  "every tier's deployed corpus matches",
);
expect(
  "geometry override NOT matching the deployed count",
  run(allCounts({ "temper-geometry": 999 }), freshCensus()),
  1,
  "STALE DEPLOYED CORPUS (temper-geometry)",
);
expect(
  "thermal override NOT matching the deployed count",
  run(allCounts({ "temper-thermal": 999 }), freshCensus()),
  1,
  "STALE DEPLOYED CORPUS (temper-thermal)",
);
expect(
  "design-bundle override NOT matching the deployed count",
  run(allCounts({ "temper-design-bundle": 999 }), freshCensus()),
  1,
  "STALE DEPLOYED CORPUS (temper-design-bundle)",
);
expect(
  "router-core override NOT matching the deployed count",
  run(allCounts({ "temper-rust-router-core": 999 }), freshCensus()),
  1,
  "STALE DEPLOYED CORPUS (temper-rust-router-core)",
);
expect(
  "constraint-compiler override NOT matching the deployed count",
  run(allCounts({ "temper-constraint-compiler": 999 }), freshCensus()),
  1,
  "STALE DEPLOYED CORPUS (temper-constraint-compiler)",
);
expect(
  "quality-oracle override NOT matching the deployed count",
  run(allCounts({ "temper-quality-oracle": 999 }), freshCensus()),
  1,
  "STALE DEPLOYED CORPUS (temper-quality-oracle)",
);
expect(
  "io-types override NOT matching the deployed count",
  run(allCounts({ "temper-io-types": 999 }), freshCensus()),
  1,
  "STALE DEPLOYED CORPUS (temper-io-types)",
);

// ---------------------------------------------------------------------------
// 7. CONTENT HASH (issue #945) — the fix this PR adds. `test_count` is a weak
//    proxy for "is this the same content": PR #941's clock-bug fix moved 7
//    temper-geometry tests from trapping to passing on wasm32 while the
//    registered count stayed 722 both before and after, and the count-only
//    check reported the stale pre-#941 module fresh for four commits. Every
//    case below runs against ALL_BUILT / freshCensus(), where every full-
//    corpus tier's built and deployed sha256 already match (section A already
//    proved that passes) — each case here perturbs exactly one side of one
//    tier's digest.
// ---------------------------------------------------------------------------
console.log("\nG. content hash (issue #945): count alone is not identity");
{
  // THE #945 CASE, restated as a pinned test: COUNT RIGHT, DIGEST WRONG. This
  // is the exact shape count_check could not see and only R19 caught live.
  // temper-thermal is picked because it also carries the registered-vs-
  // executable gap (145/143), so this proves the digest check fires
  // independently of that trap too.
  const stale = freshCensus();
  stale["temper-wasm-thermal"] = {
    test_count: THERMAL_BUILT, // count matches exactly
    abi_version: 1,
    module_sha256: "sha-thermal-STALE-pre-941",
  };
  const res = run(ALL_BUILT, stale);
  expect(
    "temper-thermal: count right, digest wrong (the #945 case)",
    res,
    1,
    "STALE DEPLOYED MODULE CONTENT (temper-thermal, issue #945)",
  );
  // Proves the digest check is independent, not riding the count failure:
  // the count check must NOT also fire, or this case would not actually pin
  // "digest catches what count cannot".
  if (res.out.includes("STALE DEPLOYED CORPUS (temper-thermal)")) {
    failures += 1;
    console.log(
      "  FAIL   count-right-digest-wrong case also tripped the COUNT check — the two checks are not independent",
    );
  } else {
    console.log("  PASS   ...and confirmed: STALE DEPLOYED CORPUS (temper-thermal) did NOT fire");
  }
}
{
  // WRONG DIGEST, plain form, on a different tier: temper-quality-oracle,
  // the newest tier with a registered-vs-executable gap of its own (126/125).
  const stale = freshCensus();
  stale["temper-wasm-quality-oracle"] = {
    test_count: QUALITY_ORACLE_BUILT,
    abi_version: 1,
    module_sha256: "sha-quality-oracle-WRONG",
  };
  expect(
    "temper-quality-oracle: wrong digest -> red",
    run(ALL_BUILT, stale),
    1,
    "STALE DEPLOYED MODULE CONTENT (temper-quality-oracle, issue #945)",
  );
}
{
  // DIGEST PRESENT BUT COUNT WRONG. The digest check must not mask or
  // suppress the count check: even with a well-formed (if now-mismatched,
  // because the count moved) digest present on both sides, a count drift must
  // still fail exactly as it always has.
  const stale = freshCensus();
  stale["temper-wasm-io-types"] = {
    test_count: IO_TYPES_BUILT - 5,
    abi_version: 1,
    module_sha256: IO_TYPES_SHA, // digest still "matches" — count is what's wrong
  };
  const res = run(ALL_BUILT, stale);
  expect(
    "temper-io-types: digest present (and matching) but count wrong -> red",
    res,
    1,
    "STALE DEPLOYED CORPUS (temper-io-types)",
  );
}
{
  // MISSING DEPLOYED DIGEST -> soft pass. The Worker predates issue #945 (or
  // has not been redeployed since) and simply omits module_sha256 from
  // /health. The run must still be green — the count/partition checks below
  // are what's carrying it — and it must say so via a visible warning, not
  // silently.
  const stale = freshCensus();
  delete stale["temper-wasm-router-core"].module_sha256;
  const res = run(ALL_BUILT, stale);
  expect(
    "temper-rust-router-core: deployed /health has no module_sha256 -> still green",
    res,
    0,
    "every tier's deployed corpus matches",
  );
  expect(
    "  ...and it is a visible warning, not silent",
    res,
    0,
    "content-hash check skipped for tier temper-rust-router-core",
  );
}
{
  // MISSING BUILT DIGEST -> soft pass, the other side. Simulates a built
  // census produced by a run_wasm_tests.mjs that predates the sha256 field
  // (or a census that was hand-written / from a cache without it).
  const builtNoDigest = builtJson("built_constraint_compiler_no_digest", CONSTRAINT_COMPILER_BUILT);
  const argsNoDigest = ALL_BUILT.map((a, i) =>
    ALL_BUILT[i - 1] === "--built-json-constraint-compiler" ? builtNoDigest : a,
  );
  const res = run(argsNoDigest, freshCensus());
  expect(
    "temper-constraint-compiler: built census has no summary.sha256 -> still green",
    res,
    0,
    "every tier's deployed corpus matches",
  );
  expect(
    "  ...and it is a visible warning, not silent",
    res,
    0,
    "content-hash check skipped for tier temper-constraint-compiler",
  );
}
{
  // BOTH SIDES MISSING -> soft pass, the rollout-day-one case: neither the
  // build pipeline nor the deployed Worker has picked up issue #945's fix
  // yet. Every OTHER tier still has its digest checked in the same run (this
  // reuses freshCensus()/ALL_BUILT, where every other tier matches), which is
  // the point: the soft pass is per tier, not a global escape hatch that
  // disables the whole feature the moment one tier lags.
  const builtNoDigest = builtJson("built_design_bundle_no_digest", DESIGN_BUNDLE_BUILT);
  const argsNoDigest = ALL_BUILT.map((a, i) =>
    ALL_BUILT[i - 1] === "--built-json-design-bundle" ? builtNoDigest : a,
  );
  const census = freshCensus();
  delete census["temper-wasm-design-bundle"].module_sha256;
  const res = run(argsNoDigest, census);
  expect(
    "temper-design-bundle: digest missing on BOTH sides -> still green",
    res,
    0,
    "every tier's deployed corpus matches",
  );
  expect(
    "  ...every OTHER tier's digest is still checked in the same run",
    res,
    0,
    "temper-thermal",
  );
}

console.log(
  failures === 0
    ? "\nAll cases passed: the freshness check goes green on a current tier and red on every divergence above."
    : `\n${failures} case(s) FAILED.`,
);
process.exit(failures === 0 ? 0 : 1);
