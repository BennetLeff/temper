#!/usr/bin/env node
/**
 * R5.1 — deployed-artifact staleness control.
 *
 * Asks every deployed WASM-tier Worker how many tests it carries, and compares
 * that against the counts compiled from the commit under test. Exits non-zero,
 * loudly, when they disagree.
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
 * The partition check is part of the same property, not a bonus. The per-family
 * Workers are what the sweep actually dispatches
 * (tools/wasm/sweep_multi_worker.mjs); a tier's full-corpus Worker is not in
 * that fan-out at all. A fresh full-corpus module and a stale shard would leave
 * the dispatched path stale while the headline number looked right, so a tier's
 * shard counts must sum to exactly its built count -- no double-counting, no
 * orphans.
 *
 * ---------------------------------------------------------------------------
 * MULTI-TIER (2026-08-10): the invariant is stated PER CRATE, which is stricter
 * than it was, not looser.
 * ---------------------------------------------------------------------------
 *
 * The tier now carries two crates: temper-drc-rs (temper-wasm-tier + 7 family
 * shards) and temper-geometry (temper-wasm-geometry, which is simultaneously
 * its tier's full-corpus Worker and its only shard). They are two separate
 * `cargo build` invocations producing two .wasm files with two independent
 * counts, and tools/wasm/wasm_tier_topology.json is the committed description
 * of that shape.
 *
 * The naive generalisation -- "all deployed Workers sum to the total built
 * count" -- would have been a REAL WEAKENING and is not what this does. Summing
 * across crates lets errors cancel: temper-drc-rs deployed 11 short while
 * temper-geometry is deployed 11 long, and a union check passes with two stale
 * modules. Per tier, each crate's deployed count must equal ITS OWN built
 * count, so nothing cancels and the 11-test gap this control caught on
 * 2026-08-10 still fails exactly as it did.
 *
 * The second anti-weakening rule is here in code, not in a comment: EVERY tier
 * in the topology must be given a built count. There is no flag that skips a
 * tier and no default that assumes one. Omitting `--built-json-geometry` does
 * not quietly check drc alone -- it exits 2 and says which tier has no count.
 * A check that can be disabled by leaving out an argument is a check that will
 * eventually be disabled by leaving out an argument.
 *
 * Usage:
 *   node tools/wasm/check_deployed_freshness.mjs \
 *     --built-json <path>              # temper-drc-rs census (run_wasm_tests.mjs --json)
 *     --built-json-geometry <path>     # temper-geometry census
 *     [--expected-count N]             # override for temper-drc-rs; wins over --built-json
 *     [--expected-count-geometry N]    # override for temper-geometry
 *     [--base-domain bennetleff.workers.dev]
 *     [--abi-version 1]
 *     [--json out.json]
 *     [--timeout-ms 15000]
 *
 * The per-tier flag suffix is the crate name with the leading `temper-` dropped
 * and `-` kept (`temper-geometry` -> `--built-json-geometry`). temper-drc-rs is
 * additionally reachable as the unsuffixed `--built-json` / `--expected-count`,
 * because it is the tier those flags meant before this file grew a second one.
 *
 * Exit codes:
 *   0  every tier's deployed corpus matches its built corpus, and its shards
 *      partition it
 *   1  staleness / unreachable Worker / ABI mismatch -- the failure this exists for
 *   2  usage error (a tier with no expected count, unreadable --built-json,
 *     unreadable topology)
 */

import { readFileSync, writeFileSync } from "node:fs";
import { loadTopology, workerUrl } from "./tier_topology.mjs";

function arg(name, dflt = null) {
  const i = process.argv.indexOf(name);
  return i === -1 ? dflt : process.argv[i + 1];
}

function die(code, msg) {
  // `::error::` renders as a GitHub Actions annotation; the plain echo keeps
  // the same text readable when this is run from a terminal.
  console.error(`::error::${msg.replace(/\n/g, " ")}`);
  console.error(`\n${msg}\n`);
  process.exit(code);
}

let topology;
try {
  topology = loadTopology();
} catch (e) {
  die(2, e.message);
}

const BASE_DOMAIN = arg("--base-domain", topology.base_domain);
const EXPECTED_ABI = parseInt(arg("--abi-version", String(topology.abi_version ?? 1)), 10);
const TIMEOUT_MS = parseInt(arg("--timeout-ms", "15000"), 10);
const JSON_OUT = arg("--json");

/** The flag suffix a tier's per-crate arguments carry. */
function tierSuffix(crate) {
  return crate.replace(/^temper-/, "");
}

/** The fix, named in every failure message. Staleness is only actionable if
 *  the reader is told what to run. */
const DEPLOY_DIRS = topology.tiers
  .flatMap((t) => [t.wrangler_dir, ...t.shards.map((s) => s.wrangler_dir)])
  .filter((d, i, a) => a.indexOf(d) === i);
const WORKER_COUNT = DEPLOY_DIRS.length;
const FIX =
  `FIX: re-run the deploy -- \`gh workflow run wasm-tier-deploy.yml\` (or the ` +
  "'WASM Tier Deploy (operator-triggered)' workflow's Run workflow button), " +
  "which runs `bash scripts/stage_wasm_families.sh` and `wrangler deploy` for " +
  `all ${WORKER_COUNT} Workers from the commit under test. Manual equivalent: ` +
  "`bash scripts/stage_wasm_families.sh` then `npx wrangler@4 deploy` in each of " +
  DEPLOY_DIRS.join(", ") +
  " (docs/evidence/2026-08-07-phase1-u7-deploy-runbook.md). The Worker list is " +
  "tools/wasm/wasm_tier_topology.json; all of the above read it.";

// ---------------------------------------------------------------------------
// 1. What does the commit under test compile to, for each tier?
//
// One count per tier, and a tier with no count is a usage error -- never a
// silently skipped tier. See the header's second anti-weakening rule.
// ---------------------------------------------------------------------------
function builtCountFor(tier) {
  const suffix = tierSuffix(tier.crate);
  const isDefaultTier = tier.crate === "temper-drc-rs";
  const builtJsonFlag = `--built-json-${suffix}`;
  const countFlag = `--expected-count-${suffix}`;

  const builtJson = arg(builtJsonFlag, isDefaultTier ? arg("--built-json") : null);
  const countArg = arg(countFlag, isDefaultTier ? arg("--expected-count") : null);

  let count = null;
  let source = null;

  if (builtJson) {
    let parsed;
    try {
      parsed = JSON.parse(readFileSync(builtJson, "utf8"));
    } catch (e) {
      die(
        2,
        `Cannot read the built-corpus census for ${tier.crate} from ${builtJson}: ${e.message}\n` +
          "This file is run_wasm_tests.mjs's --json output, produced by " +
          "wasm-tier-nightly.yml's local-sweep-r19 job and downloaded here as an " +
          "artifact. Its absence means local-sweep-r19 failed before running that " +
          "crate's wasm32 registry, so there is no count to compare against and this " +
          "check FAILS rather than passing on an unknown. Fix that job first.",
      );
    }
    const registered = parsed?.summary?.registered;
    if (typeof registered !== "number") {
      die(
        2,
        `${builtJson} has no numeric summary.registered — cannot establish ${tier.crate}'s ` +
          "built corpus size. (run_wasm_tests.mjs writes " +
          "{summary:{registered,...}, results:[...]}.)",
      );
    }
    count = registered;
    source = `${builtJson} (summary.registered — temper_test_count() of the ${tier.crate} wasm32 module built from the commit under test)`;
  }

  if (countArg !== null) {
    const override = parseInt(countArg, 10);
    if (!Number.isInteger(override)) {
      die(2, `${countFlag} must be an integer, got ${JSON.stringify(countArg)}`);
    }
    if (count !== null && count !== override) {
      console.error(
        `note: ${countFlag} ${override} overrides summary.registered ${count} from ${builtJson}`,
      );
    }
    count = override;
    source = `${countFlag} ${override}`;
  }

  if (count === null) {
    die(
      2,
      `No expected test count available for tier ${tier.crate}: pass ${builtJsonFlag} ` +
        `(run_wasm_tests.mjs output for that crate at the commit under test) or ${countFlag} N` +
        (isDefaultTier ? `, or the unsuffixed --built-json / --expected-count.` : ".") +
        ` Every tier in ${"tools/wasm/wasm_tier_topology.json"} must be given a count: ` +
        "there is deliberately no flag that skips one, because a check that can be " +
        "switched off by omitting an argument will be. Refusing to report the deployed " +
        `corpus 'fresh' while ${tier.crate}'s ${tier.full_corpus_worker} is compared against nothing.`,
    );
  }

  return { count, source };
}

const built = new Map(topology.tiers.map((t) => [t.crate, builtCountFor(t)]));

// ---------------------------------------------------------------------------
// 2. What do the deployed Workers say they carry?
// ---------------------------------------------------------------------------
async function health(script) {
  const url = `${workerUrl({ base_domain: BASE_DOMAIN }, script)}/health`;
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

// Deduplicated: temper-wasm-geometry is both its tier's full-corpus Worker and
// its only shard, and asking it twice would be two round-trips for one answer.
const scripts = [
  ...new Set(
    topology.tiers.flatMap((t) => [t.full_corpus_worker, ...t.shards.map((s) => s.worker)]),
  ),
];
const healths = await Promise.all(scripts.map(health));
const byScript = Object.fromEntries(healths.map((h) => [h.script, h]));

for (const tier of topology.tiers) {
  const b = built.get(tier.crate);
  console.log(`tier ${tier.crate}:`);
  console.log(`  built corpus:  ${b.count} tests`);
  console.log(`  source:        ${b.source}`);
  console.log("  deployed census:");
  // Deduplicated for the same reason the fetches are: temper-wasm-geometry is
  // both its tier's full-corpus Worker and its only shard, and listing one
  // Cloudflare script twice reads as two Workers.
  for (const script of new Set([tier.full_corpus_worker, ...tier.shards.map((s) => s.worker)])) {
    const h = byScript[script];
    console.log(
      h.error
        ? `    ${script.padEnd(24)} ERROR ${h.error}`
        : `    ${script.padEnd(24)} ${String(h.test_count).padStart(5)} tests (abi=${h.abi_version})`,
    );
  }
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
// 3. The two comparisons, per tier.
// ---------------------------------------------------------------------------
const failures = [];
const tierReports = [];

for (const tier of topology.tiers) {
  const builtCount = built.get(tier.crate).count;
  const deployedFull = byScript[tier.full_corpus_worker].test_count;
  const shardCounts = Object.fromEntries(
    tier.shards.map((s) => [s.family, byScript[s.worker].test_count]),
  );
  const shardSum = Object.values(shardCounts).reduce((a, b) => a + b, 0);

  if (deployedFull !== builtCount) {
    const drift = builtCount - deployedFull;
    const shortfall =
      drift > 0
        ? `${drift} of this commit's ${tier.crate} test${drift === 1 ? " is" : "s are"} missing from ` +
          `the deployed module — it carries ` +
          `${((deployedFull / builtCount) * 100).toFixed(1)}% of that crate's suite`
        : `${-drift} test${drift === -1 ? "" : "s"} in the deployed module ` +
          `${drift === -1 ? "is" : "are"} not in this commit's ${tier.crate} build`;
    failures.push(
      `STALE DEPLOYED CORPUS (${tier.crate}): ${tier.full_corpus_worker} carries ` +
        `${deployedFull} tests; the commit under test compiles ${tier.crate} to ` +
        `${builtCount} tests (${shortfall}). ` +
        "Every agreement number from the deployed path is computed over the " +
        "deployed corpus only, so it reports green while the difference is " +
        "untested — the same failure mode as the 147-vs-1708 window of " +
        "2026-08-07..2026-08-10, at whatever size the gap happens to be today. " +
        "A small delta is not a small problem: it is usually the newest tests, " +
        "which are the ones the tier has never run.",
    );
  }

  // For a tier whose shard set is the singleton {full_corpus_worker} this is
  // the same equation as the check above, and the report says so rather than
  // implying a second independent check happened.
  const degenerate =
    tier.shards.length === 1 && tier.shards[0].worker === tier.full_corpus_worker;

  if (shardSum !== builtCount) {
    failures.push(
      `STALE OR NON-PARTITIONING FAMILY SHARDS (${tier.crate}): the ` +
        `${tier.shards.length} per-family Worker${tier.shards.length === 1 ? "" : "s"} sum to ` +
        `${shardSum} tests; the commit under test compiles ${tier.crate} to ${builtCount} ` +
        `(${Object.entries(shardCounts).map(([f, c]) => `${f}=${c}`).join(", ")}). ` +
        "The per-family Workers are the ones sweep_multi_worker.mjs actually " +
        "dispatches, so a stale shard leaves the dispatched path stale even when " +
        `${tier.full_corpus_worker} is current.`,
    );
  }

  tierReports.push({
    crate: tier.crate,
    built_count: builtCount,
    built_source: built.get(tier.crate).source,
    full_corpus_worker: tier.full_corpus_worker,
    deployed_full_corpus: deployedFull,
    deployed_shard_counts: shardCounts,
    deployed_shard_sum: shardSum,
    shard_check_is_degenerate: degenerate,
  });
}

const ok = failures.length === 0;

if (JSON_OUT) {
  writeFileSync(
    JSON_OUT,
    JSON.stringify(
      {
        ok,
        tiers: tierReports,
        // Retained at the top level for readers (and any dashboard) that were
        // written against the single-crate shape. These are temper-drc-rs's
        // numbers, which is what these keys always meant.
        built_count: tierReports[0].built_count,
        built_source: tierReports[0].built_source,
        deployed_full_corpus: tierReports[0].deployed_full_corpus,
        deployed_family_counts: tierReports[0].deployed_shard_counts,
        deployed_family_sum: tierReports[0].deployed_shard_sum,
        abi_version: EXPECTED_ABI,
        base_domain: BASE_DOMAIN,
        worker_count: scripts.length,
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
  `\nOK — every tier's deployed corpus matches the commit under test:\n` +
    tierReports
      .map(
        (r) =>
          `  ${r.crate.padEnd(16)} ${r.full_corpus_worker}=${r.deployed_full_corpus}, ` +
          `shard sum=${r.deployed_shard_sum}, built=${r.built_count}` +
          (r.shard_check_is_degenerate
            ? " (single shard == full-corpus Worker; the shard sum restates the line above)"
            : ""),
      )
      .join("\n"),
);
