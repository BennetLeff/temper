#!/usr/bin/env node
/**
 * ANTI-VACUITY TEST for wasm-tier-deploy.yml's `on.push.paths:` filter.
 *
 *   node tools/wasm/test_deploy_trigger_paths.mjs
 *
 * Job 1 of the PR that added this file makes `wasm-tier-deploy.yml` fire
 * automatically on a `push` to `main` that touches a corpus-affecting path
 * (see that workflow's "AUTOMATIC DEPLOY" header section). A path filter
 * that is too broad wastes the gate/deploy jobs' runner time on unrelated
 * commits; one that is too narrow silently reintroduces the staleness
 * window this whole feature exists to close, deferred to the next
 * `schedule` run. Both failure modes are silent unless something exercises
 * the filter against real paths before merge — this file is that exercise.
 *
 * It caught a real bug during development: the first draft of the filter
 * used `packages/*''/src/**` as a single glob standing in for "every
 * wasm-tier crate's source". That also matches
 * `packages/temper-placer/src/**` — a large, frequently-changed Python
 * package with no wasm32 registry at all — which would have auto-deployed
 * on a large fraction of this repo's daily commit volume, defeating the
 * cost argument the whole `gate` design makes. The fix was to enumerate the
 * wasm-tier crate directories explicitly; this file is what proves that fix
 * and pins it against regressing back to the broad glob.
 *
 * ## How the pattern list is obtained
 *
 * `on.push.paths:` is evaluated by GitHub at TRIGGER time, before any code
 * in this repository runs — so, unlike every other WASM-tier consumer, it
 * CANNOT read `tools/wasm/wasm_tier_topology.json` and must be a literal
 * list in the workflow YAML (see that file's own comment on this). This
 * repo's `tools/wasm/*.mjs` are deliberately dependency-free (no
 * `js-yaml`, no `node_modules` at all — see `tier_topology.mjs`'s header),
 * so rather than add a YAML-parsing dependency for one paths block (now
 * fourteen entries, one of which is the nested
 * `packages/temper-placer/temper-constraints/**` path),
 * this file extracts the `paths:` list with a small, deliberately narrow
 * regex scoped to the exact `on: push: paths:` shape the workflow uses
 * today. It is NOT a general YAML parser and does not try to be one — if
 * the block's shape changes (a different indentation, a `paths-ignore:`
 * swap, `paths:` moved under a different trigger), this extractor fails
 * LOUDLY (an assertion below) rather than silently reading zero patterns
 * and passing every case by matching nothing.
 */

import { matchesGlob } from "node:path";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKFLOW = join(HERE, "..", "..", ".github", "workflows", "wasm-tier-deploy.yml");

function extractPushPaths(yamlText) {
  const lines = yamlText.split("\n");
  const pushIdx = lines.findIndex((l) => /^\s{2}push:\s*$/.test(l));
  if (pushIdx === -1) {
    throw new Error(`Could not find a top-level 'on: push:' block in ${WORKFLOW}. The extractor's assumed shape has changed — update it rather than let this test silently check nothing.`);
  }
  const pathsIdx = lines.findIndex((l, i) => i > pushIdx && /^\s{4}paths:\s*$/.test(l));
  if (pathsIdx === -1) {
    throw new Error(`Could not find 'push: paths:' below line ${pushIdx + 1} of ${WORKFLOW}.`);
  }
  const patterns = [];
  for (let i = pathsIdx + 1; i < lines.length; i++) {
    const stripped = lines[i].trim();
    // A comment or blank line between bullets does not end the list: the
    // workflow's paths: block carries a prose warning immediately before the
    // nested `packages/temper-placer/temper-constraints/**` entry, and a
    // `break` on it would silently truncate the extraction there -- reading
    // 10 of 14 patterns and then passing every case against a filter that no
    // longer exists. That is exactly the drift this test exists to catch,
    // happening inside the test itself. (An indented YAML comment starts with
    // `#` after optional whitespace; a blank line is empty.)
    if (stripped === "" || stripped.startsWith("#")) continue;
    const m = lines[i].match(/^\s{6}-\s+'([^']+)'\s*$/);
    if (!m) break;
    patterns.push(m[1]);
  }
  if (patterns.length === 0) {
    throw new Error(`Extracted zero path patterns from ${WORKFLOW} — the block is present but empty or the bullet-line regex no longer matches. Refusing to run every case against an empty list, which would pass all the "should NOT fire" cases for the wrong reason.`);
  }
  return patterns;
}

const PATTERNS = extractPushPaths(readFileSync(WORKFLOW, "utf8"));

// GitHub Actions' `paths:` rule: the workflow fires if ANY changed file
// matches ANY listed pattern (no negation patterns are in use here, so this
// is a plain OR — see the workflow's own comment for why one wasn't used to
// solve the temper-placer over-match instead of enumerating crates).
function fires(changedFiles) {
  return changedFiles.some((f) => PATTERNS.some((p) => matchesGlob(f, p)));
}

const CASES = [
  // Real file lists from actual commits in this repo's history
  // (`git log --name-only`), chosen because they DID change the wasm32
  // corpus and the filter must fire for them.
  {
    label: "9654edead — registered temper-pcl-ir (real corpus-affecting commit)",
    want: true,
    files: [
      "packages/temper-pcl-ir/Cargo.toml",
      "packages/temper-pcl-ir/src/lib.rs",
      "packages/temper-pcl-ir/src/wasm_test_registry.rs",
      "packages/temper-placer/temper-constraints/Cargo.lock",
      "packages/temper-placer/temper-constraints/src/ipc.rs",
      "packages/temper-wasm-test-runner/Cargo.lock",
      "packages/temper-wasm-test-runner/Cargo.toml",
      "packages/temper-wasm-test-runner/src/lib.rs",
      "scripts/gen_wasm_test_registry.py",
    ],
  },
  {
    label: "9a38fdfaf — geometry property campaign (+1510 registry entries)",
    want: true,
    files: [
      "packages/temper-geometry/src/lib.rs",
      "packages/temper-geometry/src/property_campaigns.rs",
      "packages/temper-geometry/src/wasm_test_registry.rs",
    ],
  },
  {
    label: "86c6a01f0 — deploy quality-oracle/io-types Workers (#963)",
    want: true,
    files: [
      "packages/temper-worker/families/constraint-compiler/index.js",
      "packages/temper-worker/families/quality-oracle/index.js",
      "packages/temper-worker/families/quality-oracle/wrangler.toml",
      "packages/temper-worker/src/index.js",
      "packages/temper-worker/src/worker_core.js",
      "tools/wasm/check_deployed_freshness.mjs",
      "tools/wasm/wasm_tier_topology.json",
    ],
  },
  {
    label: "this PR's own pcl-ir addition (job 2)",
    want: true,
    files: [
      "tools/wasm/wasm_tier_topology.json",
      "packages/temper-worker/families/pcl-ir/index.js",
      "packages/temper-worker/families/pcl-ir/wrangler.toml",
    ],
  },
  // Real commits that did NOT touch the corpus, plus targeted synthetic
  // cases — the filter must NOT fire for any of these.
  {
    label: "cbebb618a — docs-only plan edit (should NOT fire)",
    want: false,
    files: ["docs/plans/2026-08-07-002-feat-wasm-tier-phase2-4-plan.md"],
  },
  {
    label: "97d113ad6 — evidence doc only (should NOT fire)",
    want: false,
    files: ["docs/evidence/2026-08-11-issue-873-board-bridge-vacuity.md"],
  },
  {
    label: "synthetic — firmware-only change (should NOT fire)",
    want: false,
    files: ["firmware/main/transition_table.h", "firmware/config.yaml"],
  },
  {
    label: "synthetic — pcb board file only (should NOT fire)",
    want: false,
    files: ["pcb/temper.kicad_pcb"],
  },
  {
    label: "THE BUG THIS TEST CAUGHT — temper-placer Python source, not a wasm-tier crate (must NOT fire; an earlier draft's packages/*/src/** glob fired on this)",
    want: false,
    files: [
      "packages/temper-placer/src/temper_placer/placer/cp_sat/priority.py",
      "packages/temper-placer/tests/core/test_priority_pbt.py",
    ],
  },
  {
    label: "synthetic — temper-geometry Cargo.toml ONLY (feature-flag edit, no src/ touched; should fire — whole-directory watch, not just src/)",
    want: true,
    files: ["packages/temper-geometry/Cargo.toml"],
  },
  {
    label: "synthetic — temper-orchestration source (a wasm-tier crate since #989; must fire so a push to it triggers a redeploy)",
    want: true,
    files: ["packages/temper-orchestration/src/clearance.rs"],
  },
  {
    label: "synthetic — temper-constraints, the NESTED sub-crate (a wasm-tier crate since #989; must fire via the explicit nested path — a bare packages/temper-constraints/** glob would silently match nothing)",
    want: true,
    files: ["packages/temper-placer/temper-constraints/src/ipc.rs"],
  },
  {
    label: "synthetic — temper-rust-router source (a wasm-tier crate since #989; must fire)",
    want: true,
    files: ["packages/temper-rust-router/src/net_ordering.rs"],
  },
  {
    label: "DOCUMENTED DRIFT GAP — a hypothetical new tier registered in the topology but not yet added to this filter's paths: list (should NOT fire here; caught instead by the next `schedule` run, at most ~24h later — see the workflow's own 'DRIFT RISK' comment)",
    want: false,
    files: ["packages/temper-hypothetical-new-crate/src/wasm_test_registry.rs"],
  },
  {
    label: "synthetic — this very workflow file edited, no corpus path touched (should NOT fire; validated via dry_run on workflow_dispatch instead — see PR body)",
    want: false,
    files: [".github/workflows/wasm-tier-deploy.yml"],
  },
];

console.log(`workflow: ${WORKFLOW}`);
console.log(`extracted ${PATTERNS.length} paths: patterns:`);
for (const p of PATTERNS) console.log(`  - '${p}'`);
console.log("");

let failures = 0;
for (const c of CASES) {
  const got = fires(c.files);
  const ok = got === c.want;
  if (!ok) failures++;
  console.log(
    `  ${ok ? "PASS" : "FAIL"}  fires=${String(got).padEnd(5)} want=${String(c.want).padEnd(5)}  ${c.label}`,
  );
  if (!ok) {
    console.log(`        files: ${c.files.join(", ")}`);
  }
}

console.log(
  failures === 0
    ? "\nAll cases matched expectation: the filter fires on real and synthetic corpus-affecting pushes and does not fire on unrelated ones (including the temper-placer over-match this test caught during development)."
    : `\n${failures} case(s) FAILED.`,
);
process.exit(failures === 0 ? 0 : 1);
