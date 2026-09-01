<!-- provenance: commit=fa91792af084ae4b6faebc4e8999375d0065bb8c dirty=UNKNOWN -->
---
date: 2026-08-15
type: evidence
module: wasm-tier
tags: [wasm, deploy, staleness, registry-drift, r19]
---

# WASM tier redeploy prep — 2026-08-15 (build, verify, and what actually needed deploying)

## TL;DR

The premise — "the deployed WASM tier workers are stale after this session's many Rust
changes" — **does not hold on the deployed side**. The automatic push-triggered deploy
(`wasm-tier-deploy.yml`, live since #975) redeployed every Worker from the session's
merges the same day they landed; the last successful run (31921103703, commit
`a5da999cb`, 2026-08-16 02:15Z) verified *deployed == CI-built, sha256 match on every
tier*. HEAD (`6285d6889`, #1173) is a PCB/config-only change that touches no tier build
input, so the deployed corpus is current.

The real findings are two **silent drift holes the freshness machinery cannot see**, one
of them a live, merged-this-session gap:

1. **`temper-design-bundle`'s committed wasm registry has been stale since #1134** —
   `pad_occurrence.rs` (5 tests, ungated, wasm32-eligible) was added 2026-08-15 18:38
   and never registered. The deployed Worker, the CI builds, and the local build all
   carried 46 tests; the crate has 51. Every freshness check passes because both sides
   carry the same stale registry. **This is the drift gate doing its job where the
   freshness check structurally cannot** (`check_deployed_freshness.mjs` compares
   deployed vs built; both were built from the same stale registry).
2. **`tools/wasm/test_deploy_trigger_paths.mjs` was stale against the deploy filter**
   since #989 extended the filter to the last three tiers. Its extractor silently
   truncated at the comment inside the workflow's `paths:` block (reading 10 of 14
   patterns), and its expectations still asserted orchestration/constraints were "NOT
   wasm-tier crates". Pre-existing on `origin/main`; fixed here (stronger, not weaker —
   see below).

Everything else verified clean: 19 wasm32 modules built from HEAD, all tests pass
locally, shards partition the drc corpus exactly, and the R19 wasm-vs-native agreement
rate is **1.000000 across all 12 tiers**.

---

## Phase 1 — staleness analysis

Deployed `/health` census (queried 2026-08-16 ~02:45Z, all 19 Workers reachable):

| tier | Worker | deployed count | shard sum |
|---|---|---|---|
| temper-drc-rs | temper-wasm-tier | 3283 | drc 3064 + emc 15 + erc 12 + safety 25 + placement 18 + routing 18 + infra 131 = **3283** ✓ |
| temper-geometry | temper-wasm-geometry | 8343 | (single-shard, degenerate) |
| temper-thermal | temper-wasm-thermal | 2695 | |
| temper-design-bundle | temper-wasm-design-bundle | 46 | |
| temper-rust-router-core | temper-wasm-router-core | 3438 | |
| temper-constraint-compiler | temper-wasm-constraint-compiler | 1899 | |
| temper-quality-oracle | temper-wasm-quality-oracle | 2601 | |
| temper-io-types | temper-wasm-io-types | 6942 | |
| temper-pcl-ir | temper-wasm-pcl-ir | 2 | |
| temper-orchestration | temper-wasm-orchestration | 1011 | |
| temper-constraints | temper-wasm-constraints | 29 | |
| temper-rust-router | temper-wasm-rust-router | 20 | |

Total deployed: **30,309** executable tests.

The drc shards partition the full corpus exactly (sum == 3283). The topology file's
`_comment` prose still said "1719"/"4701" — stale prose, explicitly blessed as
"true when written" by the file's own header, refreshed to the measured numbers in this
change.

### Why the deployed side is current despite 84 commits since the last deploy run

The last successful deploy (run 31921103703, `a5da999cb`, 02:06Z) ran its own final
step — `check_deployed_freshness.mjs` — and printed `OK — every tier's deployed corpus
matches the commit under test` with **sha256 matches on every tier** (drc
19c7c9cc…, geometry fb6bfa2d…, …). Since then only `6285d6889` (#1173) landed; it
changes `pcb/`, `packages/temper-placer/configs/*.yaml` and
`power_pcb_dataset/drc_ceiling.json` only — no file the tier builds. The session's Rust
merges (#1218 SafetyValue, #1219 Table 17, #1220 PD3, #1222 net-filter, #1204 ampacity,
#1205 mains net, #1206 dormant recovery, #1210 Layer/Stackup) were each deployed by a
same-day push-triggered run.

### Local digests vs deployed digests — why they differ (toolchain, not staleness)

Local builds at HEAD produce different sha256s than the deployed Workers on every tier,
with identical counts. That is a **toolchain difference**: CI runs `ubuntu-latest`'s
stable rustc; local is rustc 1.97.1. The deployed-vs-built digest comparison is only
meaningful CI-to-CI (which the deploy run itself performs, and which matched). Local
rebuilds are deterministic (verified: recompiling `temper-rust-router` yields the same
sha256 twice), so local digests are self-consistent, but they must not be compared
against CI-built digests. Local staged digests for reference (gitignored artifacts):
`temper_wasm_test_runner.wasm` (drc full) dcc20083…, drc shards b560495e…/59b92b46…/
271067c3…/fa246496…/fb45728f…/50b4458d…/2f6929b7…, geometry 08f9cc5f…, thermal
12ed910c…, design-bundle **d8fd5880… (51 tests, after regen)**, router-core 303bd818…,
constraint-compiler af052c72…, quality-oracle 57857724…, io-types 3843437c…, pcl-ir
cbd5c4b7…, orchestration f4fe11fa…, constraints d74e51f0…, rust-router 350ec400….

## Phase 2 — build

`bash scripts/stage_wasm_families.sh` built all 19 modules from the topology at HEAD
(6285d6889), ~2 min with the warm shared cache, and staged each into
`packages/temper-worker/src/` with a sha256 sidecar (both gitignored — the deploy
workflow rebuilds them itself; the local staging exists for the local test cycle).

Note for future agents: in a worktree, `CARGO_TARGET_DIR` (from
`scripts/cargo_shared_env.sh`) points cargo at the shared `target-shared` while the
script's `WASM_DIR` is the *relative* `target-shared/…`. A worktree-local symlink
`target-shared -> <repo>/target-shared` makes the committed script work unchanged. In
CI there is no `CARGO_TARGET_DIR`, so `.cargo/config.toml`'s relative target-dir and
the script agree natively.

## Phase 3 — local execution and R19

`node tools/wasm/run_wasm_tests.mjs` for all 19 modules (12 full-corpus against their
per-crate expected-failure manifests + 7 drc family shards):

- **Full corpus**: 0 unexpected failures, 0 unexpected passes, 0 orphan exclusions in
  every tier. Expected-failures are the documented host-libm/dlsym classes only
  (drc 4, geometry 8, thermal 4).
- **Shard partition**: shard sum == full corpus == 3283 ✓; every shard's own tests pass
  (the drc shard runs exit 1 solely on expected orphan-exclusion noise from pointing a
  subset registry at the full-crate manifest — the deployed shard counts are the real
  gate, and they sum exactly).

Native `cargo test` per tier (topology `native_test_args`), then
`tools/wasm/r19_compare.py` per tier — **agreement rate 1.000000 on all 12 tiers**,
0 disagreements, 0 wasm32-only, 0 unexpected passes:

| tier | wasm32 | native | agree | native-only | wasm32-only |
|---|---|---|---|---|---|
| temper-drc-rs | 3279 pass + 4 exp | 3315 | 1.0 | 32 | 0 |
| temper-geometry | 8335 pass + 8 exp | 8454 | 1.0 | 111 | 0 |
| temper-thermal | 2691 pass + 4 exp | 2745 | 1.0 | 50 | 0 |
| temper-design-bundle | **51** pass | 55 | 1.0 | 4 | 0 |
| temper-rust-router-core | 3438 pass | 3471 | 1.0 | 33 | 0 |
| temper-constraint-compiler | 1899 pass | 1923 | 1.0 | 24 | 0 |
| temper-quality-oracle | 2601 pass | 2642 | 1.0 | 41 | 0 |
| temper-io-types | 6942 pass | 7001 | 1.0 | 59 | 0 |
| temper-pcl-ir | 2 pass | 2 | 1.0 | 0 | 0 |
| temper-orchestration | 1011 pass | 1061 (--lib) | 1.0 | 50 | 0 |
| temper-constraints | 29 pass | 42 | 1.0 | 13 (= 12 integration + 1 dlsym, exactly the topology's documented accounting) | 0 |
| temper-rust-router | 20 pass | 23 | 1.0 | 3 (= the proptests, documented) | 0 |

R19 JSON outputs per tier are at `/tmp/r19/<crate>.json` (this session's machine only).

## Finding 1 (live) — design-bundle registry drift: 5 tests silently out of the tier since #1134

`scripts/gen_wasm_test_registry.py --crate temper-design-bundle --check` fails on
`origin/main`: `pad_occurrence.rs` (added by #1134, `96db2ccde`, 2026-08-15 18:38 —
after the registry's last regeneration in #1031) carries 5 `#[test]` fns in an ungated
`#[cfg(test)] mod tests`, eligible for wasm32. The committed registry has 46;
regeneration yields 51.

Why nothing caught it: the freshness check compares *deployed vs built*; both sides were
built from the same stale registry, so count and digest both matched. The drift gate
(`gen_wasm_test_registry.py --check`) is the only control that compares the registry
against source, and it had not been acted on since #1134 landed. This is the same
failure class as `src/ipc.rs`'s 11-test gap of 2026-08-09 (documented in the generator's
own header): a *module* missing from the registry is invisible to drift, which only
compares the list against the registry — the `check_unregistered` arm catches it when
run, but nothing ran it against the post-#1134 tree.

**Fix (this PR)**: regenerated `temper-design-bundle`'s registry (46 → 51, +5
`pad_occurrence::tests` entries), rebuilt the module, re-ran: 51/51 pass on wasm32.
The 5 tests are pure pad-occurence geometry — none of the four divergence classes
applies, so `wasm_expected_failures_design_bundle.json` stays empty (verified: no
orphan, no unexpected pass).

## Finding 2 (pre-existing) — test_deploy_trigger_paths.mjs stale against the deploy filter

The anti-vacuity test for `wasm-tier-deploy.yml`'s `paths:` filter failed on
`origin/main` in 3 cases, for two reasons, both predating this session:

1. **Extractor truncation**: `extractPushPaths` stopped at the first non-bullet line;
   the workflow's paths block carries a prose comment immediately before the nested
   `packages/temper-placer/temper-constraints/**` entry, so extraction silently read 10
   of 14 patterns — the exact drift it exists to catch, inside the test itself.
2. **Stale expectations**: cases written for #975's filter asserted orchestration and
   temper-constraints "NOT a wasm-tier crate; should NOT fire" — false since #989
   deployed those tiers and extended the filter.

Fix (this PR, aligned not weakened): the extractor now skips comment/blank lines between
bullets (reading all 14 patterns), the two stale cases now assert the filter **must**
fire for orchestration and the nested constraints path, and a rust-router case was added.
15/15 cases pass; the test now verifies strictly more of the filter than it ever could
before. The topology `_comment`'s claim that the filter "does NOT yet name" the three
new crates was also factually stale (the filter does, since #989) and is corrected.

## Finding 3 (pre-existing, out of scope, documented not fixed) — `make regen-check` failures from the session's own merges

`make regen-check` at HEAD reports 3 problem groups, all from files the session merged,
none touched by this change:

- **2 hash-order NEW_SITE defects** (determinism defects, regen refuses by policy):
  `temper_placer/cli/repair_commands.py:193` (`_frozen_positions`) and
  `temper_placer/router_v6/trace_width_assignment.py:409` (`_worst_case_copper_area`) —
  a `set` iterated into an ordered artifact, carrying `PYTHONHASHSEED` order. From
  #1144 / #1204. Per `make regen`'s own doctrine these must be *fixed in the source*
  (sort/project the iteration), never ledgered. **Owner action needed.**
- **3 unmanifested scripts**: `check_duplicate_predicates.py`,
  `check_pyo3_duplicate_registration.py`, `duplicate_predicate_registry.py` — need
  `scripts/manifest.yaml` entries (CI `check_manifest_gate` fails otherwise).
- **4 unwired kernels** in `temper-geometry/src/layer_identity.rs`
  (`engine_supported_signal_layer_names`, `parse_stackup`, `parse_stackup_from_path`,
  `test_only_stackup`) — from #1210; the unwired-kernel gate fails until wired or
  justified.

All three groups fail identically on pristine `origin/main`; this PR neither causes nor
fixes them, but they will fail CI gates on merge and should be triaged separately
(after the safety-audit work the handoff ranks first — none is a WASM-tier issue).

## Deploy checklist (owner)

The `.wasm` files and sha256 sidecars are gitignored; the deploy workflow builds and
stages them itself. Nothing about the deploy needs the local staged copies.

1. **Merge this PR** (`chore/wasm-tier-redeploy-2026-08-15`). The push-triggered
   `wasm-tier-deploy.yml` fires automatically — the PR touches
   `packages/temper-design-bundle/**`, `packages/temper-drc-rs/Cargo.lock`,
   `packages/temper-wasm-test-runner/Cargo.lock`, `tools/wasm/wasm_tier_topology.json`
   and `scripts/gen_wasm_test_registry.py`-adjacent paths, all in the `paths:` filter.
   The gate job debounces against main's tip; the deploy job rebuilds all 19 modules
   and redeploys every Worker, then runs `check_deployed_freshness.mjs` itself.
2. **Verify the run**: `gh run list --workflow=wasm-tier-deploy.yml --limit 3` — expect
   a success whose last step prints `OK — every tier's deployed corpus matches…` with
   `temper-wasm-design-bundle=51` and sha256 match on every tier.
3. **Fallback** (only if the push trigger misbehaves): `gh workflow run
   wasm-tier-deploy.yml` (or the "WASM Tier Deploy (operator-triggered)" button). No
   `CF_TOKEN` input exists — the workflow reads `CF_API_TOKEN`/`CLOUDFLARE_API_TOKEN`
   from repo secrets; an operator with the token runs it. `dry_run=true` is available to
   validate the whole build+bundle path without a credential.
4. **Expected post-deploy counts**: design-bundle 46 → **51** (the only count change);
   every other tier's count is unchanged (3283/8343/2695/3438/1899/2601/6942/2/1011/29/20)
   but every Worker's content sha256 changes (all 12 crates recompiled from HEAD with
   the session's merged kernels).
5. **Nightly backstop**: `wasm-tier-nightly.yml`'s R5.1 freshness check runs ~04:40Z
   and will confirm the new digests from the CI side.

## Files changed in this PR

- `packages/temper-design-bundle/src/pad_occurrence.rs` — registry gate widening
  (generated).
- `packages/temper-design-bundle/src/wasm_test_registry.rs` — regenerated, 46 → 51.
- `packages/temper-drc-rs/Cargo.lock`, `packages/temper-wasm-test-runner/Cargo.lock` —
  lockfile refresh (the session's merges added the `regex` dependency and the
  `temper-data-model` crate; the committed lockfiles predated them and the build
  refreshed them).
- `tools/wasm/wasm_tier_topology.json` — `_comment` prose refreshed to measured
  deployed counts + paths-filter paragraph corrected.
- `tools/wasm/test_deploy_trigger_paths.mjs` — extractor comment-skip + three new-tier
  cases (Finding 2).
- `docs/evidence/2026-08-15-wasm-tier-redeploy-prep.md` — this document.

Local staged artifacts (gitignored, not committed): 19 `.wasm` + `.sha256.json` in
`packages/temper-worker/src/`, built and verified at HEAD. The deploy workflow rebuilds
these itself.
