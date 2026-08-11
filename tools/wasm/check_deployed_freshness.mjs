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
 * The tier now carries eight crates: temper-drc-rs (temper-wasm-tier + 7 family
 * shards, 1719), temper-geometry (722), temper-thermal (143),
 * temper-rust-router-core (111), temper-constraint-compiler (69),
 * temper-design-bundle (24), temper-quality-oracle (125) and temper-io-types
 * (144). The latter seven each declare exactly one family, so each of their
 * single scripts is simultaneously its tier's full-corpus Worker and its only
 * shard. They are eight separate `cargo build` invocations producing eight
 * .wasm files with eight independent counts, and
 * tools/wasm/wasm_tier_topology.json is the committed description of that shape.
 *
 * The naive generalisation -- "all deployed Workers sum to the total built
 * count" -- would have been a REAL WEAKENING and is not what this does. Summing
 * across crates lets errors cancel: temper-drc-rs deployed 11 short while
 * temper-geometry is deployed 11 long, and a union check passes with two stale
 * modules. Per tier, each crate's deployed count must equal ITS OWN built
 * count, so nothing cancels and the 11-test gap this control caught on
 * 2026-08-10 still fails exactly as it did. Each crate added widens the surface
 * a union check could hide drift across; it does not widen this one. The 3057
 * total is now large enough that an ENTIRE TIER could vanish inside a union
 * check's noise -- temper-design-bundle's whole corpus is 24 tests, twice the
 * gap that already went unnoticed for three days -- which is the argument for
 * per-tier restated at the size the tier has actually reached.
 *
 * The second anti-weakening rule is here in code, not in a comment: EVERY tier
 * in the topology must be given a built count. There is no flag that skips a
 * tier and no default that assumes one. Omitting `--built-json-thermal` does
 * not quietly check the other two -- it exits 2 and says which tier has no
 * count. A check that can be disabled by leaving out an argument is a check
 * that will eventually be disabled by leaving out an argument. That rule is
 * also why adding a tier to the topology is a COMPLETE change on its own: every
 * caller that does not learn to pass the new flag fails loudly on the next run
 * rather than silently checking one crate fewer. Verified again on 2026-08-11,
 * when the topology went from three tiers to six: a caller still passing the
 * old three flags exits 2 naming the first tier it has no count for (the tiers
 * are checked in topology order and the first miss is fatal, so a caller
 * catching up flag-by-flag gets one named tier per run until all six are
 * supplied -- never a quieter check). That is why the three new Workers cannot
 * be deployed and swept while being proven current by nothing.
 *
 * ---------------------------------------------------------------------------
 * CONTENT HASH (issue #945): a test COUNT is a weak proxy for "is this the
 * same content", additive to the count check above, not a replacement for it.
 * ---------------------------------------------------------------------------
 *
 * Live on 2026-08-11 (nightly `31449478989`): PR #941 fixed an unconditional
 * `Instant::now()` in `build_capacitated_graph`, moving 7 temper-geometry
 * tests from trapping to passing on wasm32. `summary.registered` was 722
 * before the fix and 722 after -- same test COUNT, different test BEHAVIOUR --
 * so the count check above reported the pre-#941 deployed module "fresh" for
 * four commits. Only the independent R19 comparison (native vs. deployed
 * verdicts) caught it, and issue #945 is explicit that a crate with no native
 * arm to compare against would have had nothing catch it at all. Other shapes
 * that leave a count untouched: a test renamed, a test's body edited, a kernel
 * changed under an unchanged test, or one test added and one removed in the
 * same commit -- the last is indistinguishable from a no-op under a count
 * alone.
 *
 * The fix, per `scripts/check_measurement_provenance.py`'s module docstring
 * making the identical argument for `power_pcb_dataset/drc_ceiling.json`
 * (rejecting a commit SHA as primary freshness identity "for exactly this
 * class of reason"): give the deployed module a CONTENT identity, not just a
 * cardinality. `run_wasm_tests.mjs --json` already reads `<module>.wasm`'s
 * bytes to instantiate it; it now also sha256s them into `summary.sha256`,
 * riding the exact same `--built-json-<suffix>` file this script already
 * requires for the count -- NO NEW CLI FLAG. `scripts/stage_wasm_families.sh`
 * sha256s the same staged bytes into a `<module>.wasm.sha256.json` sidecar
 * that each `families/<name>/index.js` imports and returns from `/health` as
 * `module_sha256` (see `packages/temper-worker/src/worker_core.js`'s header
 * for why the Worker cannot compute this itself: a deployed Worker only ever
 * gets a compiled `WebAssembly.Module`, and there is no supported way to
 * recover the original bytes from one to hash at request time).
 *
 * Scope: compared per tier against the FULL-CORPUS Worker only, mirroring the
 * count check's primary bite (the shard-sum PARTITION check has no digest
 * analogue -- hashes don't sum -- and stays exactly the count-only control it
 * was; not weakened, not extended).
 *
 * MISSING DIGEST IS A SOFT PASS, NOT EXIT 2 -- the one place this check is
 * deliberately looser than the count check, and the reason is rollout, not
 * principle. Every tier existing before this change is deployed today without
 * a `module_sha256` in its `/health` response; nothing here can retroactively
 * bake a digest into an already-running Worker (this repo does not deploy --
 * `wasm-tier-deploy.yml` is `workflow_dispatch`-only and run by an operator).
 * If a missing digest were exit 2 the same way a missing built count is, this
 * check would go from green to a hard failure on the commit that adds this
 * feature, for every tier, until an operator happens to redeploy all of
 * them -- punishing the PR that ships the fix rather than the staleness the
 * fix exists to catch. So: digest present on BOTH sides and DIFFERENT is a
 * hard failure (exit 1), exactly as loud as a count mismatch. Digest absent on
 * either side is a warning (`::warning::`, visible, not silent) and the run
 * proceeds on the count check alone -- the check this repo has always had,
 * unweakened. Once every Worker has been redeployed at least once after this
 * PR, every tier will have a digest on both sides and the soft path stops
 * being exercised in practice; it is not removed, because a Worker can always
 * be rolled back to a pre-digest wrangler bundle and rollout leniency should
 * survive that too.
 *
 * Usage (one --built-json per tier in the topology; ALL of them required):
 *   node tools/wasm/check_deployed_freshness.mjs \
 *     --built-json <path>                        # temper-drc-rs census (run_wasm_tests.mjs --json)
 *     --built-json-geometry <path>               # temper-geometry census
 *     --built-json-thermal <path>                # temper-thermal census
 *     --built-json-design-bundle <path>          # temper-design-bundle census
 *     --built-json-rust-router-core <path>       # temper-rust-router-core census
 *     --built-json-constraint-compiler <path>    # temper-constraint-compiler census
 *     --built-json-quality-oracle <path>         # temper-quality-oracle census
 *     --built-json-io-types <path>                # temper-io-types census
 *     [--expected-count N]                       # override for temper-drc-rs; wins over --built-json
 *     [--expected-count-<suffix> N]              # the same override, per tier
 *     [--base-domain bennetleff.workers.dev]
 *     [--abi-version 1]
 *     [--json out.json]
 *     [--timeout-ms 15000]
 *
 * There is no `--expected-sha256-*` override to match `--expected-count-*`:
 * unlike a count, there is no legitimate reason to hand this script a digest
 * by hand instead of letting it read `summary.sha256` from the same
 * `--built-json` file, and adding one would be a second way to assert a
 * digest that could disagree with the census file's own.
 *
 * The per-tier flag suffix is the crate name with the leading `temper-` dropped
 * and `-` kept (`temper-geometry` -> `--built-json-geometry`), computed by
 * `tierFlagSuffix` in tier_topology.mjs -- the same export the deploy workflow
 * and the Makefile use to GENERATE these flags, so the two sides cannot drift.
 * temper-drc-rs is additionally reachable as the unsuffixed `--built-json` /
 * `--expected-count`, because it is the tier those flags meant before this file
 * grew a second one.
 *
 * Exit codes:
 *   0  every tier's deployed corpus matches its built corpus, its shards
 *      partition it, and every tier with a digest on both sides matches (a
 *      tier missing a digest on either side does not block this)
 *   1  staleness / unreachable Worker / ABI mismatch / content-hash mismatch
 *      (both sides had a digest and they differed) -- the failure this exists
 *      for
 *   2  usage error (a tier with no expected count, unreadable --built-json,
 *     unreadable topology)
 */

import { readFileSync, writeFileSync } from "node:fs";
import { loadTopology, workerUrl, tierFlagSuffix } from "./tier_topology.mjs";

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
  const suffix = tierFlagSuffix(tier.crate);
  const isDefaultTier = tier.crate === "temper-drc-rs";
  const builtJsonFlag = `--built-json-${suffix}`;
  const countFlag = `--expected-count-${suffix}`;

  const builtJson = arg(builtJsonFlag, isDefaultTier ? arg("--built-json") : null);
  const countArg = arg(countFlag, isDefaultTier ? arg("--expected-count") : null);

  let count = null;
  let source = null;
  // sha256 of the exact bytes run_wasm_tests.mjs compiled, per issue #945 —
  // see this file's header, "CONTENT HASH". null when the built-corpus census
  // predates that field or was not supplied at all; a missing digest is a
  // soft-pass note in the comparison below, never a reason to die(2) the way
  // a missing count is — see the header for why the two are deliberately
  // asymmetric.
  let digest = null;

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
    const sha = parsed?.summary?.sha256;
    digest = typeof sha === "string" && sha ? sha : null;
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

  return { count, source, digest };
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
    // module_sha256 (issue #945): optional. A Worker deployed before this
    // change, or a Worker whose Cargo.toml/wrangler.toml has not been
    // redeployed since, simply omits it — see the header's "MISSING DIGEST"
    // note for why that is a soft pass rather than an error here.
    const digest = typeof body.module_sha256 === "string" && body.module_sha256 ? body.module_sha256 : null;
    return { script, url, test_count: body.test_count, abi_version: body.abi_version, module_sha256: digest };
  } catch (e) {
    return { script, url, error: e.message || String(e) };
  }
}

// Deduplicated: each of the five single-family tiers' one script is both its
// tier's full-corpus Worker and its only shard, and asking one twice would be
// two round-trips for one answer.
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
  console.log(`  built sha256:  ${b.digest ?? "(none supplied)"}`);
  console.log("  deployed census:");
  // Deduplicated for the same reason the fetches are: a single-family tier's
  // one script is both its full-corpus Worker and its only shard, and listing
  // one Cloudflare script twice reads as two Workers.
  for (const script of new Set([tier.full_corpus_worker, ...tier.shards.map((s) => s.worker)])) {
    const h = byScript[script];
    console.log(
      h.error
        ? `    ${script.padEnd(24)} ERROR ${h.error}`
        : `    ${script.padEnd(24)} ${String(h.test_count).padStart(5)} tests (abi=${h.abi_version}) sha256=${h.module_sha256 ?? "(none reported)"}`,
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

  // ---------------------------------------------------------------------
  // Content hash (issue #945), additive to the count check above. Compared
  // ONLY against the full-corpus Worker -- see the header's "CONTENT HASH"
  // section for why the shard-sum partition check has no digest analogue.
  //
  // Both present and different: a hard failure, exactly as loud as a count
  // mismatch (exit 1) -- this is the case the count check CANNOT see, because
  // it is the whole reason this section exists. #941's clock-bug fix is the
  // worked example: temper-geometry's registered count was 722 before and
  // after, so only a content hash catches the deployed module still being the
  // pre-fix build.
  //
  // Either side missing: a soft pass. Logged as a GitHub Actions `::warning::`
  // (visible, not silent) rather than added to `failures`, and for a reason
  // specific to rollout -- see the header's "MISSING DIGEST IS A SOFT PASS"
  // paragraph. This never substitutes for the count check: a tier with a
  // missing digest still has its count and partition checks run in full,
  // unweakened, above.
  // ---------------------------------------------------------------------
  const builtDigest = built.get(tier.crate).digest;
  const deployedDigest = byScript[tier.full_corpus_worker].module_sha256;
  let digestChecked = false;
  if (builtDigest && deployedDigest) {
    digestChecked = true;
    if (builtDigest !== deployedDigest) {
      failures.push(
        `STALE DEPLOYED MODULE CONTENT (${tier.crate}, issue #945): ` +
          `${tier.full_corpus_worker} reports module_sha256=${deployedDigest}; the commit ` +
          `under test builds ${tier.crate} to sha256=${builtDigest}. The TEST COUNT can ` +
          "still match here — that is exactly the gap this check closes: a behaviour " +
          "change (a bug fix, a renamed test, a kernel edited under an unchanged test " +
          "name, or one test added and one removed in the same commit) can leave the " +
          "count untouched while the deployed bytes are still the old build. This is " +
          "the real 2026-08-11 incident (PR #941 fixed a clock bug in " +
          "build_capacitated_graph; temper-geometry's registered count was 722 both " +
          "before and after; only the independent R19 comparison caught the deployed " +
          `module still being pre-#941). ${FIX}`,
      );
    }
  } else if (!builtDigest && !deployedDigest) {
    console.warn(
      `::warning::content-hash check skipped for tier ${tier.crate}: neither the built ` +
        `census nor ${tier.full_corpus_worker}'s /health reports a sha256. Falling back ` +
        "to the count/partition check above for this tier (issue #945's fix has not " +
        "reached this tier's build+deploy pipeline yet).",
    );
  } else if (!builtDigest) {
    console.warn(
      `::warning::content-hash check skipped for tier ${tier.crate}: the built census ` +
        `(${built.get(tier.crate).source.split(" (")[0]}) has no summary.sha256. Produced ` +
        "by an older run_wasm_tests.mjs, or the crate was censused before issue #945's " +
        "fix. Falling back to the count/partition check above for this tier.",
    );
  } else {
    console.warn(
      `::warning::content-hash check skipped for tier ${tier.crate}: ` +
        `${tier.full_corpus_worker}'s /health has no module_sha256. The deployed Worker ` +
        "predates issue #945's fix and has not been redeployed since. Falling back to " +
        "the count/partition check above for this tier.",
    );
  }

  tierReports.push({
    crate: tier.crate,
    built_count: builtCount,
    built_source: built.get(tier.crate).source,
    built_sha256: builtDigest,
    full_corpus_worker: tier.full_corpus_worker,
    deployed_full_corpus: deployedFull,
    deployed_sha256: deployedDigest,
    content_hash_checked: digestChecked,
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
        built_sha256: tierReports[0].built_sha256,
        deployed_full_corpus: tierReports[0].deployed_full_corpus,
        deployed_sha256: tierReports[0].deployed_sha256,
        content_hash_checked: tierReports[0].content_hash_checked,
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
            : "") +
          (r.content_hash_checked
            ? `, sha256 matches (${r.deployed_sha256})`
            : ", sha256 not compared (missing on one side — see any ::warning:: above)"),
      )
      .join("\n"),
);
