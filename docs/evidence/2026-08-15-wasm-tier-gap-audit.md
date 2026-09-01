<!-- provenance: commit=593d9ab24a9da0d03b51733f07da9ae4c15511bf (persistent main commit for PR #1275 carrying this evidence; original audit worktree ref was not retained) dirty=false -->

# WASM tier gap audit — orchestration eligibility, tier gaps, CI wiring, post-session freshness

**Date:** 2026-08-15/16
**Snapshot commit (this document, worktree HEAD):** `6285d6889b30644feb546912fdaebd50832d1166` (`origin/main`)
**Deployed-corpus commit:** `a5da999cb1a3438d01dfe472333e6d8dba2e0b01` (last successful deploy, run 31921103703)
**Deliverable of:** session task "wasm tier gap audit" (Part 1 orchestration worker, Part 2 tier gap audit, Part 3 CI wiring, Part 4 freshness).

## Bottom line

1. **The task premise is stale: `temper-orchestration` already has a deployed Cloudflare Worker.** It was deployed 2026-08-11 in PR #989 (`269eb08b9`, "deploy Workers for temper-orchestration, temper-constraints, temper-rust-router"), has a full topology entry (`tools/wasm/wasm_tier_topology.json` tier `temper-orchestration`, Worker `temper-wasm-orchestration`, `packages/temper-worker/families/orchestration/`), is live (`/health` HTTP 200 verified 2026-08-16), and carries **1,011 executable tests, all passing**, content-hash-verified at the last deploy. `scripts/gen_wasm_test_registry.py`'s `CRATES` dict and the topology `tiers` array are exactly the same 12 crates — there is **no registered crate without a Worker**. No scaffolding is needed. See §1.
2. **`temper-orchestration` builds cleanly for wasm32 at current main** (`cargo check --target wasm32-unknown-unknown --no-default-features` passes, 7.8 s). Its pyo3 surface remains `#[cfg(feature = "python")]`-gated exactly as the 2026-08-12 spike documented; nothing about its deployability changed. See §1.
3. **One real tier gap was found and FIXED: `temper-design-bundle`'s committed registry was stale** — 46 tests registered while the source had 51. `pad_occurrence.rs::tests` (5 portable tests, added by #1134) was never registered, so the deployed design-bundle Worker carries 46 tests and the crate's own `gen_wasm_test_registry.py --check` fails. **CI was already red on this on main** (Fast Gates step "WASM test registry matches committed"). Regenerated: 51 registered, and the rebuilt wasm32 module executes 51/51 passing (verified with the actual tier build + `run_wasm_tests.mjs`). The worker now needs a redeploy (auto-triggered by this PR's push, per the deploy workflow's push trigger). See §2.1.
4. **Second real gap found and FIXED: `tools/wasm/test_family_map.json` was badly drifted** — it mapped 1,719 tests while the live registry had 3,283 (1,564 tests — the entire property-campaign corpus plus later additions — were unclassified/unmapped), and `manufacturing.rs::tests` (8 tests, added by #964) had **no family classification at all**, which is an exit-1 failure of the "WASM test family map matches the registry" Fast Gates step. Classified `manufacturing` as `types` (it is a fabrication-tolerance data type, not a rule kernel — same family as `pyfmt`/`pymath`/`board`) and regenerated: 3,283 mapped, check green and idempotent. See §2.2.
5. **The 2026-08-11 native-only classification still holds post-#1206, with the same two exceptions the earlier document already reported as found-but-unfixed, now verified fixed:** `temper-rust-router-core`'s `encoding::tests` portable-but-missing pair is **fixed on main** (commit `58d869ae3`, #977, gated the `proptests` submodule; both tests now register). No new `portable-but-missing` tests were found in this audit (orchestration's 49 native-only tests are all `proptest-dev-dependency`; design-bundle's 8 are all `integration-test-target`/`doctest`). #1206's extension-module drop does **not** change wasm32 eligibility: it fixes a *native* link failure (`cargo test --features python` on x86_64), and pyo3 remains uncompilable for `wasm32-unknown-unknown` either way — the wasm tier's `--no-default-features` build is untouched by it. See §2.3.
6. **CI wiring verdict: the tier gates nothing.** `wasm-tier-pr.yml` is advisory by design (D5.4 — its own header says "MUST NOT BE ADDED TO" `required-checks.json`); the nightly fails on disagreement but is scheduled, not per-PR; and `required-checks.json` contains **zero** wasm-tier contexts. This is intentional per the Phase 5 plan (D5.4: R22/R23 durability machinery is unbuilt by design), not an oversight — but it means a PR that breaks a deployed Worker goes green on the PR path, and the nightly's R19 rotation means any given crate's native-vs-wasm agreement is only re-derived once every **12** nights (rotation comment still says "9 tiers" — stale prose). The `cargo test --doc` step (#1217) is native-only (in the required `rust-checks` context); doctests are structurally outside the tier registry mechanism. See §3.
7. **Freshness after the session's changes: deployed workers are CURRENT, not stale.** The last deploy (`a5da999cb`, 2026-08-16T02:06Z) is an ancestor of every session change this task named (#1218 SafetyValue, #1219 Table 17, #1222 router net-filtering, #1223 constraints k-value, #1243 thermal, #1210 Layer/Stackup, #1206 extension-module), and the post-deploy R5.1 check content-hash-verified every tier. HEAD differs from the deployed commit only by a `pcb/` commit. **The only stale artifact is design-bundle's *committed registry* (46 vs 51), which this PR fixes** — the deployed Worker will be brought current by this PR's push-triggered auto-deploy. See §4.

## 1. Part 1 — orchestration worker: already deployed, wasm32-eligible

The task premise ("temper-orchestration is the sole crate with no deployed Cloudflare Worker") is **false as of main**. Evidence, each independently verified:

- **Topology entry**: `tools/wasm/wasm_tier_topology.json` has a `temper-orchestration` tier (crate, cargo feature `orchestration-wasm-test-registry`, staged module `temper_wasm_test_runner_orchestration.wasm`, Worker `temper-wasm-orchestration`, `wrangler_dir packages/temper-worker/families/orchestration`, `native_test_args` with `--lib`).
- **Worker source exists**: `packages/temper-worker/families/orchestration/{index.js,wrangler.toml}` both present; `index.js`'s own header documents the 91-registered/83-executable split at deploy time (now 1,019 registered / 1,011 executable).
- **Deployed**: `gh run list --workflow=wasm-tier-deploy.yml` shows the orchestration tier deployed since PR #989; the last deploy's `freshness_postdeploy.json` records `temper-orchestration built 1011 deployed 1011 content_hash_checked true`.
- **Live**: `curl https://temper-wasm-orchestration.bennetleff.workers.dev/health` → HTTP 200 (2026-08-16).
- **Census at last deploy**: `staged_census_temper-orchestration.json` → registered 1011, executed 1011, passed 1011, failed 0, orphanExclusions [].
- **Builds for wasm32 at current main**: `cargo check --target wasm32-unknown-unknown --no-default-features --manifest-path packages/temper-orchestration/Cargo.toml` → Finished in 7.82 s, no errors.
- **Registry up to date**: `gen_wasm_test_registry.py --check --crate temper-orchestration` → "up to date: 1019 tests across 18 modules" (1019 = 1011 executable + 1 `host_libm` cfg-excluded + 7 per-test `#[cfg(feature = "python")]`, the exact two-class stack the topology header documents).

The 2026-08-12 spike's verdict is unchanged and remains the correct description of *why* the full loop bodies can't run on wasm32 (the `Py<PyAny>` BoardState data model, O-C3, ~40–53 d) — but that is a "can the *loop* run" question, not a "does the crate have a Worker" question. The crate's pure kernels are already on the tier, and the spike's own §1 documented that ("The tier is already live … 83 executable tests, all passing" — grown to 1,011 since).

**What this task's scaffolding instructions would have added already exists.** No changes made.

## 2. Part 2 — tier gap audit

### 2.1 FIXED: design-bundle registry stale (46 vs 51) — CI was red on main

`gen_wasm_test_registry.py --check --crate temper-design-bundle` failed at HEAD:

```
wasm test registry is stale; run scripts/gen_wasm_test_registry.py --crate temper-design-bundle
  packages/temper-design-bundle/src/pad_occurrence.rs
  packages/temper-design-bundle/src/wasm_test_registry.rs
```

Cause: `packages/temper-design-bundle/src/pad_occurrence.rs` (with its 5-test `mod tests`) was **created by commit `96db2ccde` (#1134, 2026-08-15, board resync / pad-identity work)** and never added to the registry's `ALL` array. The committed registry (last touched by `eeacec857` #1218) lists 8 modules / 46 tests; the source has 9 / 51. The 5 tests are plain portable Rust (`PadOccurrence` equality/hash/accessor tests, no pyo3, no proptest, no host-only symbol) — nothing about them is wasm32-ineligible; they were simply never registered.

**Why nothing caught it until now:** the deploy pipeline (`wasm-tier-deploy.yml`) verifies `deployed == built` (R5.1) — and the deploy at `a5da999cb` *did* build 46 and deploy 46, content-hash verified. The build uses the **committed** registry, so a stale registry is invisible to R5.1: the deployed Worker is internally consistent and wrong about the source. The registry-vs-source comparison is the Fast Gates step "WASM test registry matches committed", which is exactly the step that was **red on main** at audit time (verified in run 31921103719's job log: 4 failing steps in Fast Gates, including this one). #1134 merged 2026-08-15 with this gate red — the merge was not blocked, because Fast Gates' red status... was reported (it is a required context, so the PR *should* have been blocked; the run listed here is a main push run, and the branch-protection state of main's own pushes is not the question — the gate is red on main *right now*, and this PR fixes it).

**Fix applied (this PR):** `python3 scripts/gen_wasm_test_registry.py --crate temper-design-bundle` (write mode). Result: 51 tests across 9 modules; `--check` green. The rebuilt tier module (`cargo build --release --target wasm32-unknown-unknown --no-default-features --features design-bundle-wasm-test-registry`, then `run_wasm_tests.mjs`) executes **51/51, all passing, 0 failed**. The 5 pad_occurrence tests are now on the tier, not merely registered.

Native side is consistent: `cargo test --no-default-features --lib` = 51 passed; the 8 native-only tests are 2 `tests/temper_bundle.rs` integration tests + 2 doctests (one a `compile_fail` on `PadOccurrence`'s private-field construction) + the integration binary's 2, all structural classes.

### 2.2 FIXED: family map drifted (1,719 → 3,283) and `manufacturing` unclassified

`tools/wasm/gen_test_family_map.py --check` failed at HEAD with:

```
no family classification for 1 registered module(s) -- add an entry to MODULE_FAMILY:
    ("manufacturing", "tests"): "<family>",
```

Two distinct defects, both fixed in this PR:

1. **`manufacturing.rs::tests` (8 tests) was never classified.** The module (`FabricationEnvelope`, portable fabrication-tolerance shape) was added by #964 (`b0b764187`) with a registry entry under the `infra` shard but no `MODULE_FAMILY` entry. Classified as `("manufacturing", "tests"): "types"` — it is a data type, not a rule kernel, so it sits with `pyfmt::tests`/`pymath::tests`/`board::tests` under `types`. `check_feature_agreement` has no opinion (module is not under `rules/`, so the coarse shard split maps it to `infra`).
2. **The committed map was 1,719 tests; the live registry is 3,283.** The map had not been regenerated since before the property campaigns landed (~1,564 tests — `rules::drc::property_campaigns`'s 1,504 seeded tests and everything after). The gate's `--check` compares against a fresh generation, so this *was* failing on main independently of the manufacturing entry — the Fast Gates run 31921103719 shows "WASM test family map matches the registry" as a separate failure. Regenerated: 3,283 mapped; family counts `{drc: 3078, emc: 31, erc: 12, safety: 38, placement: 28, routing: 31, dfm: 38, types: 24, integration: 3}`; `--check` green and idempotent (re-run clean).

The map is what `tools/wasm/coverage_report.py` uses to bucket tier results into per-family non-vacuity reports; a 1,719-entry map against a 3,283-test corpus meant every report built since the property campaigns mis-described ~47% of the corpus as `unmapped`.

### 2.3 Classification post-#1206 — holds, and the prior portable-but-missing finding is fixed on main

The 2026-08-11 native-only classification doc's two `portable-but-missing` tests (`encoding::tests::exhaustive_at_most_k_n1_to_n8`, `encode_to_cnf_empty_model`) are **fixed on main** by `58d869ae3` (#977): `encoding.rs`'s `proptests` submodule now carries its own `#[cfg(test)]` gate, so `encoding::tests` registers its own 2 tests and `proptests` (6) is separately excluded as `proptest-dev-dependency`. Verified: `--census` shows `encoding.rs::tests 2` registered, `encoding.rs::proptests 6 [proptest-dev-dependency]`.

**#1206 (extension-module drop) does not make anything wasm32-eligible.** The fix removes `extension-module` from the Cargo `python` feature so that a native `cargo test --features python` binary links (previously: `rust-lld: undefined symbol: PyImport_ImportModule`, because `extension-module` omits libpython linkage — a real Python-loaded `.so` resolves those at dlopen time, a standalone test binary never does). That is a native-linkage repair. pyo3 itself remains uncompilable for `wasm32-unknown-unknown` — the wasm tier builds `--no-default-features` (python off) and is untouched by the change. The 474 formerly-dormant tests are *native* tests; the classification doc's zero `python-gated` among the 325 native-only remains exactly correct ("absent from both sides equally").

**Native-only re-measured for this audit's two focal crates (r19_compare.py's own parser):**

| crate | native (lib) | registered | native-only | classes |
|---|---:|---:|---:|---|
| temper-orchestration | 1,061 (with `--lib`) | 1,019 | 49 | 49× `proptest-dev-dependency`, 0 portable-but-missing |
| temper-design-bundle | 51 lib (+2 integration +2 doctest) | 51 | 8 | integration-test-target 2, doctest 2 (the +2/+2 counted twice across binaries), 0 portable-but-missing |

All 12 crates' `--check` gates are green after this PR's fixes (§2.1, §2.2). No third `portable-but-missing` instance found by this audit — the two known mechanisms (module absent from `ELIGIBLE`, nested-ungated-proptest poisoning) are both covered now (`check_unregistered()` clean on all 12; the encoding.rs shape fixed by #977).

## 3. Part 3 — CI wiring verdict

### 3.1 `wasm-tier-pr.yml` — advisory by design (D5.4); not a gate

The workflow is literally named "WASM Tier PR Verdict **(advisory)**", and its own header says:

> "This workflow is NOT in .github/required-checks.json and MUST NOT BE ADDED TO IT. Making a tier verdict a required PR context crosses R22/R23 — the dead-letter, idempotency and reconciliation machinery that is unbuilt BY DESIGN under D10 — and the plan's Scope Boundaries put that out of scope for the whole of Phase 5."

It still *fails* (exit 1) on any real wasm32 failure in the swept tiers (freshness check, sweep, verdict step all fail-loud, no `continue-on-error`), and it has an anti-vacuity injection path — but a red X here does not block merge, by design. Its residual-risk section states the sharp consequence honestly: "A PR that breaks wasm32/native equivalence … produces a MISLEADING-BUT-PASSING tier verdict here" (the PR-path arm has no native side to compare against). It also sweeps **only the tiers the PR's diff touches** (scoped per #971 cost containment) and, critically, sweeps the **deployed** Workers — so a PR whose code changed a crate but was never redeployed is answered for by the *old* corpus (drift is reported, not fatal). That is a deliberate, documented trade (deploys are push/schedule-triggered, so a fresh deploy usually precedes a PR's verdict baseline).

### 3.2 `wasm-tier-nightly.yml` — fails on disagreement; reports agreement; rotation is 12 nights, not 9

- Runs nightly (04:40 UTC) plus manual. Two jobs: `local-sweep-r19` (builds wasm32 locally from the commit, compares against the same commit's native `cargo test`, `--fail-on-disagree` — a disagreement fails the run) and `worker-dispatch-r19` (preflights all Workers, R5.1 staleness check against the local built counts, sweeps all deployed Workers, compares the rotated tier's deployed verdicts against native, `--fail-on-disagree`).
- **R19 native-arm rotation**: only ONE tier per night gets the full native `cargo test` + R19 comparison; the other 11 get wasm32 census + deployed sweep only (pass/fail on wasm32) with no native re-derivation. Cycle = `dayOfYear % len(tiers)` → **12 nights per tier with the current topology**. The rotation step reads `tiers.length` dynamically (correct), but the header comment still says "9 tiers today (under 1.5 weeks)" — stale prose that should be updated (minor, not a functional defect; flagged for the owner).
- Agreement rates are reported in job summaries and artifacts (`r19_local_*.json`, `r19_worker_*.json`).
- **It catches regressions nightly in the weak sense** (every tier's wasm32 pass/fail + freshness, every night) **but the strong claim** ("deployed tier agrees with native") **is only re-derived for the rotated tier each night** — an equivalence break in a non-rotated tier can stand for up to 12 nights. This is the documented cost fix (2026-08-11 rotation); the trade is explicit in the header, not hidden.

### 3.3 `required-checks.json` — zero wasm-tier contexts; intentional (D5.4), with a documented precondition for changing it

`required_contexts` contains 12 contexts; none is any wasm-tier job. `context_triggers` has no wasm entries. This is **intentional**, not a gap: the PR workflow's header says making the tier required crosses R22/R23 (durability machinery unbuilt by design under D10), and states the threshold — "It stops being acceptable at exactly the moment a tier verdict is proposed as a required context … which means the native arm comes back (or the deploy becomes per-commit) in the same change that makes it required." D13's suite-by-suite transition is not "advisory forever": the plan sequences suite removal (U4) after the durability machinery, and the machinery is the owner's call. **Recommendation:** leave advisory until R22/R23 exist; when the decision to require is made, the same PR must add the native arm or per-commit deploy, or the required check will be green over code it never ran.

### 3.4 `cargo test --doc` (#1217) — native-only, in a required context; doctests structurally outside the tier

The step "Doctests (cargo test --doc, --no-default-features)" (added by #1217, `9898dc813`) lives in the **`rust-checks` job** of python-tests.yml — the job whose context **is** required ("Rust Checks (cargo check + clippy)"). So it is gated, natively. It is **not** and cannot be on the wasm tier: a doctest compiles as its own tiny binary per doctest (the classification doc's `doctest` class — 1 in geometry at the 2026-08-11 snapshot), structurally unreachable from the registry mechanism. #1217's own header says the same ("the wasm tier's native arm runs plain cargo test for exactly one rotated crate per night … never on the PR path"). This is a native-only gate by construction, and the right answer — a doctest's `compile_fail` property (the Layer/Stackup identity guarantee) cannot run on wasm32.

## 4. Part 4 — freshness after session changes: deployed workers are CURRENT

The task premise ("All [six crates] have deployed workers that are now stale") is **false**, verified three independent ways:

1. **Ancestry**: the last successful deploy ran at commit `a5da999cb` (run 31921103703, 2026-08-16T02:06:18Z). Every session change named in the task is an ancestor of `a5da999cb` (all verified `git merge-base --is-ancestor` = yes): `eeacec857` #1218 (SafetyValue), `8ac926af4` #1219 (Table 17), `7f6a6bd5c` #1222 (router net-filtering), `991295c8d` #1223 (constraints k-value), `1213c3e50` #1243 (thermal), `c70dde923` #1210 (Layer/Stackup), `89dd341d2` #1206 (extension-module), `bb3d99d11` #1174, `96db2ccde` #1134.
2. **Deploy census**: `freshness_postdeploy.json` from run 31921103703 records every tier `content_hash_checked: true` — the deployed Workers byte-match the wasm32 modules built from `a5da999cb`.
3. **HEAD vs deployed**: HEAD `6285d6889` differs from `a5da999cb` by exactly one commit, `6285d6889` (#1173, courtyard-collision fixes) — which touches `pcb/temper.kicad_pcb` only (verified `git show --stat`). No `packages/` change sits between the deployed corpus and HEAD.

Deployed-vs-registry table (deployed = run 31921103703 census; registry = `--check` at HEAD):

| crate | deployed | registry@HEAD | delta | meaning |
|---|---:|---:|---|---|
| temper-drc-rs | 3,283 | 3,283 | 0 | current |
| temper-geometry | 8,343 | 8,345 | 2 | cfg-excluded host-libm guards, not compiled — current |
| temper-thermal | 2,695 | 2,697 | 2 | cfg-excluded — current |
| temper-design-bundle | **46** | **51** | **5** | **STALE registry — FIXED in this PR; needs redeploy** |
| temper-rust-router-core | 3,438 | 3,438 | 0 | current |
| temper-constraint-compiler | 1,899 | 1,900 | 1 | cfg-excluded — current |
| temper-quality-oracle | 2,601 | 2,602 | 1 | cfg-excluded — current |
| temper-io-types | 6,942 | 6,942 | 0 | current |
| temper-pcl-ir | 2 | 2 | 0 | current |
| temper-orchestration | 1,011 | 1,019 | 8 | cfg-excluded (1 host-libm + 7 python-gated) — current |
| temper-constraints | 29 | 30 | 1 | cfg-excluded — current |
| temper-rust-router | 20 | 20 | 0 | current |

**The only stale artifact is design-bundle's committed registry**, which §2.1 fixes. The deployed design-bundle Worker still carries 46; because wasm-tier-deploy.yml auto-deploys on push (the `paths:` filter includes `packages/temper-design-bundle/**`), **this PR's merge triggers the redeploy** — the same-PR discipline the tier already relies on for the nightly baseline.

**Why the earlier staleness window did not recur:** wasm-tier-deploy.yml gained automatic push + schedule triggers (2026-08-11, #993 added the three late tiers to the paths filter; the push arm debounces via the `gate` job). Session changes landed 2026-08-15T22:56Z–2026-08-16T02:06Z, and each push-triggered deploy run in that window succeeded — the deploy cadence closed the gap the 2026-08-07→08-10 window exposed, for these crates, on the same day the changes landed.

**Outstanding for the owner (not part of this PR):**
- The nightly's R19 rotation header still says "9 tiers"; the cycle is now 12 nights per crate. Prose fix, no logic change.
- The topology `_comment` (wasm_tier_topology.json) still describes wasm-tier-deploy.yml as `workflow_dispatch`-only and its `paths:` filter as missing orchestration/constraints/rust-router — both false since #993/#1001 (verified against the current workflow file: the paths filter includes all three, and the triggers are push + schedule + dispatch). Prose fix.
- `ci/unsilence-checks-batch-1` (branch) carries the CI wiring for #1206's 474 dormant native tests (`d60796d6e`); it is **not on main**. #1206 fixed the Cargo features; the tests still do not run in CI. Land that branch or wire the dormant tests another way.
- Fast Gates was red on main at audit time for 4 steps. Two are fixed by this PR (registry, family map). The other two — **LOC cap gate** (4 files over cap: `cli/__init__.py` 1049>1000 unallowlisted, `gates.py`/`battery_run.py`/`_ground_plane.py` allowlist-grew) and **type-check gate** (19 violations, 4 stale allowlist entries, baseline 285→257) — are unrelated to the wasm tier and were NOT touched here; they need their owning agents' attention and are outside this task's scope.

## 5. What this PR changes

- `packages/temper-design-bundle/src/wasm_test_registry.rs` — regenerated: 46 → 51 tests, adds `pad_occurrence::tests::WASM_TESTS` to `ALL`.
- `packages/temper-design-bundle/src/pad_occurrence.rs` — generator-applied `#[cfg(any(test, feature = "wasm-registry"))]` + `WASM_TESTS` block (mechanical, same shape as every other registered module).
- `tools/wasm/gen_test_family_map.py` — adds `("manufacturing", "tests"): "types"` with a comment explaining the classification.
- `tools/wasm/test_family_map.json` — regenerated: 1,719 → 3,283 mapped tests, manufacturing → types.
- `docs/evidence/2026-08-15-wasm-tier-gap-audit.md` — this document.

## 6. Verification performed

- `python3 scripts/gen_wasm_test_registry.py --check --crate <X>` for all 12 crates → green (design-bundle was red before this PR's fix, now green).
- `python3 tools/wasm/gen_test_family_map.py --check` → green, idempotent.
- `cargo check --target wasm32-unknown-unknown --no-default-features` on temper-orchestration → passes (7.82 s).
- Full tier build for design-bundle (`cargo build --release --target wasm32-unknown-unknown --no-default-features --features design-bundle-wasm-test-registry --manifest-path packages/temper-wasm-test-runner/Cargo.toml`) + `node tools/wasm/run_wasm_tests.mjs` → 51 registered, 51 executed, 51 passed, 0 failed.
- Native `cargo test --no-default-features` on design-bundle (lib 51/51; integration 2/2; doctests 2/2 incl. the compile_fail) and orchestration (lib 1,061, r19-parser-normalised).
- `curl /health` on temper-wasm-orchestration and temper-wasm-geometry → 200.
- Deploy census + ancestry checks as described in §4.

## 7. Things this document does not claim

- Does not claim the full orchestration loop bodies run on wasm32 — they still cannot (pyo3 `Py<PyAny>` data model, spike O-C3). The crate's Worker runs its pure kernels; that is what the 1,011 tests cover.
- Does not claim the tier is a merge gate — it is advisory by design, and §3 states the required-check precondition honestly.
- Does not claim the deployed Workers are current for the two non-wasm Fast Gates failures (LOC cap, type-check) — those are unrelated to the tier and remain the owning agents' work.
