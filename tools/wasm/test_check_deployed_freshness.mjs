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
 * 121, safety 25, placement 18, routing 18, emc 15, erc 12 = 1719, and
 * temper-wasm-geometry's 722.
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

function freshCensus() {
  const census = { "temper-wasm-tier": { test_count: DRC_BUILT, abi_version: 1 } };
  for (const [family, count] of Object.entries(DRC_SHARDS)) {
    census[`temper-wasm-${family}`] = { test_count: count, abi_version: 1 };
  }
  census["temper-wasm-geometry"] = { test_count: GEOMETRY_BUILT, abi_version: 1 };
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
console.log(`fresh census: drc=${DRC_BUILT} (7 shards), geometry=${GEOMETRY_BUILT}\n`);

// ---------------------------------------------------------------------------
// 1. The control passes when everything is current. Without this the rest of
//    the file could be satisfied by a checker that always fails.
// ---------------------------------------------------------------------------
console.log("A. correct counts -> green");
expect(
  "both tiers current",
  run(["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY], freshCensus()),
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
    run(["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY], stale),
    1,
    "STALE DEPLOYED CORPUS (temper-geometry)",
  );
}
{
  const stale = freshCensus();
  stale["temper-wasm-tier"] = { test_count: DRC_BUILT - 11, abi_version: 1 };
  expect(
    "temper-drc-rs deployed 11 short (the real 2026-08-10 gap)",
    run(["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY], stale),
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
    run(["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY], stale),
    1,
    "STALE OR NON-PARTITIONING FAMILY SHARDS (temper-drc-rs)",
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
  const res = run(["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY], stale);
  expect("union total unchanged, both crates wrong", res, 1, "STALE DEPLOYED CORPUS (temper-drc-rs)");
  expect("  ...and the geometry tier is named too", res, 1, "STALE DEPLOYED CORPUS (temper-geometry)");
}

// ---------------------------------------------------------------------------
// 4. THE CHECK CANNOT BE SWITCHED OFF BY OMITTING AN ARGUMENT. A tier with no
//    built count is a usage error naming that tier -- never a narrower run that
//    exits 0 having checked one crate.
// ---------------------------------------------------------------------------
console.log("\nD. a tier with no built count -> exit 2, never a quiet pass");
expect(
  "--built-json-geometry omitted",
  run(["--built-json", BUILT_DRC], freshCensus()),
  2,
  "No expected test count available for tier temper-geometry",
);
expect(
  "--built-json omitted",
  run(["--built-json-geometry", BUILT_GEOMETRY], freshCensus()),
  2,
  "No expected test count available for tier temper-drc-rs",
);
expect("no counts at all", run([], freshCensus()), 2, "No expected test count available");

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
    run(["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY], census),
    1,
    "did not report a usable /health census",
  );
}
{
  const census = freshCensus();
  census["temper-wasm-geometry"] = { test_count: GEOMETRY_BUILT, abi_version: 2 };
  expect(
    "temper-wasm-geometry speaks ABI 2",
    run(["--built-json", BUILT_DRC, "--built-json-geometry", BUILT_GEOMETRY], census),
    1,
    "ABI mismatch",
  );
}

// ---------------------------------------------------------------------------
// 6. --expected-count overrides behave per tier.
// ---------------------------------------------------------------------------
console.log("\nF. --expected-count overrides, per tier");
expect(
  "geometry override matching the deployed count",
  run(["--expected-count", String(DRC_BUILT), "--expected-count-geometry", String(GEOMETRY_BUILT)], freshCensus()),
  0,
  "every tier's deployed corpus matches",
);
expect(
  "geometry override NOT matching the deployed count",
  run(["--expected-count", String(DRC_BUILT), "--expected-count-geometry", "999"], freshCensus()),
  1,
  "STALE DEPLOYED CORPUS (temper-geometry)",
);

console.log(
  failures === 0
    ? "\nAll cases passed: the freshness check goes green on a current tier and red on every divergence above."
    : `\n${failures} case(s) FAILED.`,
);
process.exit(failures === 0 ? 0 : 1);
