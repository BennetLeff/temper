#!/usr/bin/env node
/**
 * R5.1 — deployed-artifact staleness control.
 *
 * Asks the 8 deployed WASM-tier Workers how many tests they carry, and
 * compares that against the count compiled from the commit under test.
 * Exits non-zero, loudly, when they disagree.
 *
 * WHY THIS EXISTS (docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md,
 * D5.3). Between 2026-08-07 and 2026-08-10 the deployed Workers carried 147
 * tests while `temper-drc-rs`'s suite had grown to 1,708. The nightly reported
 * `agreement_rate: 1.0` the entire time, because r19_compare.py compares the
 * verdicts it is handed -- the 147 the Workers happened to carry -- and a
 * test the deployed corpus does not contain is `native_only`, not `disagree`.
 * Worse, BOTH arms of wasm-tier-nightly.yml published the discrepancy in the
 * same run (local arm: 1,708; deployed arm: 147) and nothing compared them.
 * That comparison is this script. A tier answering for a corpus other than the
 * repository's is reporting on nothing, and it reports it in green.
 *
 * The partition check is part of the same property, not a bonus. The 7
 * per-family Workers are what the sweep actually dispatches
 * (tools/wasm/sweep_multi_worker.mjs); the full-corpus Worker is not in that
 * fan-out at all. A fresh full-corpus module and a stale shard would leave the
 * dispatched path stale while the headline number looked right, so the shards'
 * counts must sum to exactly the built count -- no double-counting, no orphans.
 *
 * Usage:
 *   node tools/wasm/check_deployed_freshness.mjs \
 *     --built-json /tmp/wasm_local.json        # run_wasm_tests.mjs output
 *     [--expected-count N]                     # override; wins over --built-json
 *     [--base-domain bennetleff.workers.dev]
 *     [--abi-version 1]
 *     [--json out.json]
 *     [--timeout-ms 15000]
 *
 * Exactly one of --built-json / --expected-count is required (both is fine if
 * they agree; --expected-count wins and the difference is reported).
 *
 * Exit codes:
 *   0  deployed corpus matches the built corpus, and the shards partition it
 *   1  staleness / unreachable Worker / ABI mismatch -- the failure this exists for
 *   2  usage error (no expected count available, unreadable --built-json)
 */

import { readFileSync, writeFileSync } from "node:fs";

const FULL_CORPUS_WORKER = "temper-wasm-tier";
const FAMILIES = ["drc", "emc", "erc", "safety", "placement", "routing", "infra"];

function arg(name, dflt = null) {
  const i = process.argv.indexOf(name);
  return i === -1 ? dflt : process.argv[i + 1];
}

const BASE_DOMAIN = arg("--base-domain", "bennetleff.workers.dev");
const EXPECTED_ABI = parseInt(arg("--abi-version", "1"), 10);
const TIMEOUT_MS = parseInt(arg("--timeout-ms", "15000"), 10);
const BUILT_JSON = arg("--built-json");
const EXPECTED_COUNT_ARG = arg("--expected-count");
const JSON_OUT = arg("--json");

/** The fix, named in every failure message. Staleness is only actionable if
 *  the reader is told what to run. */
const FIX =
  "FIX: re-run the deploy -- `gh workflow run wasm-tier-deploy.yml` (or the " +
  "'WASM Tier Deploy (operator-triggered)' workflow's Run workflow button), " +
  "which runs `bash scripts/stage_wasm_families.sh` and `wrangler deploy` for " +
  "all 8 Workers from the commit under test. Manual equivalent: " +
  "`bash scripts/stage_wasm_families.sh` then `npx wrangler@4 deploy` in each " +
  "of packages/temper-worker/families/{drc,emc,erc,safety,placement,routing,infra} " +
  "and in packages/temper-worker (docs/evidence/2026-08-07-phase1-u7-deploy-runbook.md).";

function die(code, msg) {
  // `::error::` renders as a GitHub Actions annotation; the plain echo keeps
  // the same text readable when this is run from a terminal.
  console.error(`::error::${msg.replace(/\n/g, " ")}`);
  console.error(`\n${msg}\n`);
  process.exit(code);
}

// ---------------------------------------------------------------------------
// 1. What does the commit under test compile to?
// ---------------------------------------------------------------------------
let builtCount = null;
let builtSource = null;

if (BUILT_JSON) {
  let parsed;
  try {
    parsed = JSON.parse(readFileSync(BUILT_JSON, "utf8"));
  } catch (e) {
    die(
      2,
      `Cannot read the built-corpus census from ${BUILT_JSON}: ${e.message}\n` +
        "This file is run_wasm_tests.mjs's --json output, produced by " +
        "wasm-tier-nightly.yml's local-sweep-r19 job and downloaded here as an " +
        "artifact. Its absence means local-sweep-r19 failed before running the " +
        "wasm32 registry, so there is no count to compare against and this " +
        "check FAILS rather than passing on an unknown. Fix that job first.",
    );
  }
  const registered = parsed?.summary?.registered;
  if (typeof registered !== "number") {
    die(
      2,
      `${BUILT_JSON} has no numeric summary.registered — cannot establish the ` +
        "built corpus size. (run_wasm_tests.mjs writes " +
        "{summary:{registered,...}, results:[...]}.)",
    );
  }
  builtCount = registered;
  builtSource = `${BUILT_JSON} (summary.registered — temper_test_count() of the wasm32 module built from the commit under test)`;
}

if (EXPECTED_COUNT_ARG !== null) {
  const override = parseInt(EXPECTED_COUNT_ARG, 10);
  if (!Number.isInteger(override)) {
    die(2, `--expected-count must be an integer, got ${JSON.stringify(EXPECTED_COUNT_ARG)}`);
  }
  if (builtCount !== null && builtCount !== override) {
    console.error(
      `note: --expected-count ${override} overrides summary.registered ${builtCount} from ${BUILT_JSON}`,
    );
  }
  builtCount = override;
  builtSource = `--expected-count ${override}`;
}

if (builtCount === null) {
  die(
    2,
    "No expected test count available: pass --built-json (run_wasm_tests.mjs " +
      "output for the commit under test) or --expected-count N. Refusing to " +
      "report the deployed corpus 'fresh' against nothing.",
  );
}

// ---------------------------------------------------------------------------
// 2. What do the deployed Workers say they carry?
// ---------------------------------------------------------------------------
async function health(script) {
  const url = `https://${script}.${BASE_DOMAIN}/health`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(TIMEOUT_MS) });
    if (!res.ok) return { script, url, error: `HTTP ${res.status}` };
    const body = await res.json();
    if (typeof body?.test_count !== "number") {
      return { script, url, error: `/health lacks numeric test_count: ${JSON.stringify(body)}` };
    }
    return { script, url, test_count: body.test_count, abi_version: body.abi_version };
  } catch (e) {
    return { script, url, error: e.message || String(e) };
  }
}

const scripts = [FULL_CORPUS_WORKER, ...FAMILIES.map((f) => `temper-wasm-${f}`)];
const healths = await Promise.all(scripts.map(health));
const byScript = Object.fromEntries(healths.map((h) => [h.script, h]));

console.log(`built corpus:    ${builtCount} tests`);
console.log(`  source:        ${builtSource}`);
console.log("deployed census:");
for (const h of healths) {
  console.log(
    h.error
      ? `  ${h.script.padEnd(24)} ERROR ${h.error}`
      : `  ${h.script.padEnd(24)} ${String(h.test_count).padStart(5)} tests (abi=${h.abi_version})`,
  );
}

const unreachable = healths.filter((h) => h.error);
if (unreachable.length) {
  die(
    1,
    "Deployed Worker(s) did not report a usable /health census: " +
      unreachable.map((h) => `${h.script} (${h.error})`).join(", ") +
      ". The staleness comparison cannot be made, so this FAILS rather than " +
      `passing on a partial census. ${FIX}`,
  );
}

const badAbi = healths.filter((h) => h.abi_version !== EXPECTED_ABI);
if (badAbi.length) {
  die(
    1,
    `ABI mismatch: expected abi_version=${EXPECTED_ABI}, got ` +
      badAbi.map((h) => `${h.script}=${h.abi_version}`).join(", ") +
      `. The deployed module speaks a different host protocol than this commit. ${FIX}`,
  );
}

// ---------------------------------------------------------------------------
// 3. The two comparisons.
// ---------------------------------------------------------------------------
const deployedFull = byScript[FULL_CORPUS_WORKER].test_count;
const familyCounts = Object.fromEntries(
  FAMILIES.map((f) => [f, byScript[`temper-wasm-${f}`].test_count]),
);
const familySum = Object.values(familyCounts).reduce((a, b) => a + b, 0);

const failures = [];

if (deployedFull !== builtCount) {
  const drift = builtCount - deployedFull;
  const shortfall =
    drift > 0
      ? `${drift} of this commit's test${drift === 1 ? " is" : "s are"} missing from ` +
        `the deployed module — it carries ` +
        `${((deployedFull / builtCount) * 100).toFixed(1)}% of the suite`
      : `${-drift} test${drift === -1 ? "" : "s"} in the deployed module ` +
        `${drift === -1 ? "is" : "are"} not in this commit's build`;
  failures.push(
    `STALE DEPLOYED CORPUS: ${FULL_CORPUS_WORKER} carries ${deployedFull} tests; ` +
      `the commit under test compiles to ${builtCount} tests (${shortfall}). ` +
      "Every agreement number from the deployed path is computed over the " +
      "deployed corpus only, so it reports green while the difference is " +
      "untested — the same failure mode as the 147-vs-1708 window of " +
      "2026-08-07..2026-08-10, at whatever size the gap happens to be today. " +
      "A small delta is not a small problem: it is usually the newest tests, " +
      "which are the ones the tier has never run.",
  );
}

if (familySum !== builtCount) {
  failures.push(
    `STALE OR NON-PARTITIONING FAMILY SHARDS: the 7 per-family Workers sum to ` +
      `${familySum} tests; the commit under test compiles to ${builtCount} ` +
      `(${Object.entries(familyCounts).map(([f, c]) => `${f}=${c}`).join(", ")}). ` +
      "The per-family Workers are the ones sweep_multi_worker.mjs actually " +
      "dispatches, so a stale shard leaves the dispatched path stale even when " +
      `${FULL_CORPUS_WORKER} is current.`,
  );
}

const ok = failures.length === 0;

if (JSON_OUT) {
  writeFileSync(
    JSON_OUT,
    JSON.stringify(
      {
        ok,
        built_count: builtCount,
        built_source: builtSource,
        deployed_full_corpus: deployedFull,
        deployed_family_counts: familyCounts,
        deployed_family_sum: familySum,
        abi_version: EXPECTED_ABI,
        base_domain: BASE_DOMAIN,
        failures,
        checked_at: new Date().toISOString(),
      },
      null,
      2,
    ),
  );
  console.log(`\nwrote ${JSON_OUT}`);
}

if (!ok) {
  die(1, `${failures.join("\n\n")}\n\n${FIX}`);
}

console.log(
  `\nOK — deployed corpus matches the commit under test: ` +
    `${FULL_CORPUS_WORKER}=${deployedFull}, family shards sum=${familySum}, built=${builtCount}.`,
);
