<!-- provenance: commit=d0b96316ffacd06c96824c98336e827496c6eeea dirty=true (HEAD at time of writing is the merge of origin/main fa067a952 -- #1296, merged after this document was originally drafted -- into this branch's own commit d5d45a73a. Worktree /home/bennet/Desktop/temper/.claude/worktrees/agent-a7401e9e226726006, branch feat/wasm-tier-deploy-alerting-and-pr-coverage, PR #1297. pcb/temper.kicad_pcb untouched -- sha256 9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd, unchanged throughout, matches docs/HANDOFF-2026-08-17.md. `packages/temper-rust-router-core/src/direct_topology.rs` not edited by this task -- #1296 is a sibling agent's PR; this document's branch only merged the already-landed result. No deploy triggered by this task.) -->

# WASM tier CI/CD: fail loudly on deploy failure, a standalone staleness watchdog, and PR-path wasm32 execution coverage

**Date:** 2026-08-17

## 0. The incident this responds to

Timeline, 2026-08-17 (all times UTC):

| Time | Run | What happened |
|---|---|---|
| 02:54 | deploy `31989435749` (push, #1278) | Failed in `scripts/stage_wasm_families.sh`, exit 101 — a Rust wasm32 build failure. |
| 04:08 | deploy `31993444375` (scheduled) | Failed at "Census + smoke-run every staged full-corpus module" — `temper-rust-router-core`'s wasm32 registry panics at runtime: `std::time::Instant::now()` is not implemented on `wasm32-unknown-unknown`. Introduced by #1260's direct topology solver (`packages/temper-rust-router-core/src/direct_topology.rs:346`). |
| 05:20 | nightly `31997559157` | Went red on the *independent* R5.1 module-sha comparison: `temper-drc-rs` and `temper-geometry` module shas did not match the commit under test, and `temper-geometry` was serving 8343 tests against 8380 compiled (37 missing). |

Neither failed deploy ever reached its own "Deploy every Worker" step — both died earlier, in staging/census — so the deploy loop's own atomicity guard (`::error::Deployed X of Y Workers`) was never exercised and no partial deploy occurred. The previously-deployed bytes stayed live, silently, until the nightly's independent check caught the drift **~2.5 hours later**, and only because it happens to run on its own schedule regardless of what the deploy workflow did.

**The structural gap, restated:** a failed deploy leaves the previous bytes live and nothing fails loudly. Every tier verdict computed in that 2.5-hour window was green over a stale subset — the same shape as the 2026-08-07→10 (147-vs-1,708) and 2026-08-11 (PR #941 clock-bug, module sha caught what the count could not) incidents this repo has already lived through twice.

I verified all three run outcomes directly (`gh run view <id> --log-failed`) before designing anything below; the panic text and step names above are taken from the actual logs, not inferred.

## 1. What I evaluated, and what I did about each

### Candidate 1 — fail loudly on a failed deploy. **Implemented.**

Before this change, a red `wasm-tier-deploy.yml` or `wasm-tier-nightly.yml` run had **zero consumers**. `grep -c 'issues: write'` on both files was 0. A run going red produced a red X in the Actions tab and nothing else — the same failure mode `trunk-health.yml` was built to close for a different gate two weeks earlier ("main went red twice in one hour... neither was noticed for hours").

I added one new job to each workflow, mirroring `trunk-health.yml`'s own issue-filing pattern (dedupe against an open issue with the same label; comment rather than re-file on a repeat failure; a human closes it once the workflow is green again):

- `wasm-tier-deploy.yml` → `report-deploy-failure` (`needs: [gate, deploy]`, `if: needs.deploy.result == 'failure'`). Files/refreshes an issue labeled `wasm-tier-deploy-failure`, explicitly naming that the deployed tier may now be stale, and pointing at the redeploy command and at candidate 2's watchdog (below).
- `wasm-tier-nightly.yml` → `report-nightly-failure` (`needs: [local-sweep-r19, worker-dispatch-r19]`, `if: always() && (either failed)`). Files/refreshes an issue labeled `wasm-tier-nightly-failure`.

Both are **new, separate jobs**, not edits inside the existing `deploy`/`local-sweep-r19`/`worker-dispatch-r19` job bodies. Those jobs are long, heavily narrated, and already proven correct; a new downstream job with its own `permissions: issues: write` is a small, independently reviewable diff that cannot perturb the existing jobs' step ordering, `if:` conditions, or concurrency groups.

**Why this doesn't weaken anything:** it adds a consumer of an existing failure signal; it does not touch what causes success or failure. Nothing that passed before now fails, and nothing that failed before now passes.

### Candidate 2 — close the staleness window with a more-frequent standalone check. **Implemented.**

`wasm-tier-deploy.yml` already runs the R5.1 freshness check immediately after a *successful* deploy. That half of candidate 2 already existed. What did not exist: a check that runs regardless of whether a deploy was attempted at all — which is exactly what both 2026-08-17 failures needed, since neither deploy run got far enough to reach its own R5.1 step.

New workflow: `wasm-tier-staleness-watch.yml`, `schedule: '*/30 * * * *'` + `workflow_dispatch`. It runs *only* `tools/wasm/check_deployed_freshness.mjs` — the same tool `wasm-tier-deploy.yml` and `wasm-tier-nightly.yml` already run — against the last successful `wasm-tier-nightly.yml` run's built-count census (same baseline-resolution mechanism `wasm-tier-pr.yml` already uses for its own freshness check). No `cargo`, no wasm32 build, no deployed-Worker test sweep — one GitHub API call, one artifact download, and 19 `/health` GETs (the topology's Cloudflare script count). On failure it files/refreshes a `wasm-tier-stale` issue via the same pattern as candidate 1.

This closes the *detection* half of the window from "next nightly, up to ~24h" (or, as it happened, ~2.5h by luck of the schedule) down to **under an hour**, independent of whether any deploy was ever attempted. It composes with, and does not replace, the nightly's from-scratch rebuild — see the workflow's own header for the explicit scope limitation: its baseline is only as fresh as the last *successful* nightly, so if the nightly itself is failing for several days, this watchdog inherits that staleness rather than improving on it. What it adds is cadence, not a new source of truth.

I deliberately did **not** add a periodic deployed-Worker *test* sweep (`sweep_multi_worker.mjs`) at this cadence — that is a much larger per-test HTTP fan-out, and PR #971 already measured and fixed exactly this cost problem for `wasm-tier-pr.yml`. Running the full sweep every 30 minutes would reproduce the cost blowup #971 closed, for a question (do the tests pass) this task's incident was not actually about — the incident was about staleness, not test failures.

### Candidate 3 — deploy atomicity. **Evaluated; no change.**

Already correctly handled, and today's incident did not exercise the gap because it never reached the part of the pipeline that could produce it. Tracing `wasm-tier-deploy.yml`'s `deploy` job:

- Every step before "Deploy every Worker in the topology" has no `continue-on-error`, so a failure anywhere in staging/census stops the job before a single `wrangler deploy` runs — confirmed directly in both incident runs (`gh run view 31989435749` / `31993444375 --log-failed`): the job list shows "Deploy every Worker in the topology" and every step after it as never-run (`-`), not failed.
- The deploy loop itself already detects and fails loudly on a partial deploy: `if [ "${deployed}" != "${expected}" ]; then echo "::error::Deployed ${deployed} of ${expected} Workers — the tier is now in a MIXED state..."`.
- The post-deploy R5.1 verify step (`Verify the deployed corpus is what was just built`) is the second, independent check on the same property.

The one real gap — nothing verifies the *previously* deployed tier's atomicity when a deploy fails *before* the deploy loop starts — is exactly what candidate 2's watchdog now covers (a mixed or stale tier is a mixed or stale tier regardless of *why* it's mixed or stale). I did not add redundant machinery on top of an already-correct, already-tested mechanism.

### Candidate 4 — should the PR verdict become a required check? **Evaluated; explicitly not changed.**

`wasm-tier-pr.yml`'s own header states the prerequisite plainly: making a tier verdict a required PR context crosses R22/R23 (dead-letter, idempotency, reconciliation machinery), which is **unbuilt by design** under D10, and ties to D5.4. That machinery is out of scope for this task (I was told not to touch `direct_topology.rs`, not to deploy, and not to merge #1296 — all signals that this is a narrow, surgical task, not a phase-boundary decision).

More importantly: **today's incident was not a case where the PR verdict was misleadingly green on a PR that should have blocked.** The PR verdict is scoped to the *deployed* tier, which was correctly stale-flagged by its own freshness check the whole time (`wasm-tier-pr.yml`'s freshness step would have failed loudly on any PR opened during the stale window, same mechanism as candidate 2's watchdog). The mechanism that actually failed today was upstream of the PR path entirely: nothing on the PR path ever compiled or ran `temper-rust-router-core`'s wasm32 registry at all (see candidate 5). Flipping advisory→required would not have prevented this incident; closing the PR-path coverage gap (candidate 5) would have, and does.

I recommend revisiting D5.4 only once R22/R23 lands, or if a *third* incident specifically traces to the advisory verdict itself being ignored on a PR that should have blocked — neither is true of 2026-08-17.

### Candidate 5 — build-failure feedback speed. **Implemented, and it is the root-cause fix.**

This is where the actual incident lived. Two separate gaps stacked:

**Gap A — coverage.** `python-tests.yml`'s `rust-checks` job (a required check) already had a section literally named "WASM32 regression guard" — but it only ever built **two of the tier's twelve crates** (`temper-drc-rs`, `temper-geometry`), hardcoded. `temper-rust-router-core` — the crate that broke — was one of the ten crates with **zero PR-path wasm32 attention of any kind**.

**Gap B — depth.** Even for the two crates it did cover, the existing guard only ran `cargo build --release --target wasm32-unknown-unknown` (a link check) — never the `--features <tier>` build through `temper-wasm-test-runner`, and never an execution via `node tools/wasm/run_wasm_tests.mjs`. This matters mechanically: `cargo build` does not compile `#[cfg(test)]` code at all. The bug that broke deploy is a `#[test]` function calling `std::time::Instant::now()`, which panics only when the compiled wasm32 module is actually *executed*. **No build-only check, for any crate, could ever have caught this class of bug.**

**Fix:** a new step in `rust-checks`, "WASM32 build + EXECUTE every wasm-tier registry (topology-driven, all 12 tiers)", added *after* the existing two-crate step (which I left untouched). It loops over every tier in `tools/wasm/wasm_tier_topology.json` (via `tools/wasm/tier_topology.mjs`, the same loader every other consumer uses — a hardcoded list here would reproduce exactly the "two crates covered, ten silently not" defect this step exists to close), builds `temper-wasm-test-runner` with each tier's `--features`, and runs `node tools/wasm/run_wasm_tests.mjs` against the output — the identical build+execute pair `wasm-tier-nightly.yml`'s "Build + run every tier's wasm32 registry" step and `wasm-tier-deploy.yml`'s "Census + smoke-run" step already run, moved to the PR path.

**I proved this catches the actual bug**, locally, before committing:

```
$ cargo build --release --target wasm32-unknown-unknown --no-default-features \
    --features router-core-wasm-test-registry \
    --manifest-path packages/temper-wasm-test-runner/Cargo.toml
   Finished `release` profile [optimized] target(s) in 5.42s

$ node tools/wasm/run_wasm_tests.mjs /tmp/temper_wasm_test_runner_router_core.wasm \
    --expected-failures tools/wasm/wasm_expected_failures_router_core.json \
    --json /tmp/pr_wasm_local_router-core.json
=== results ===
  passed            3439
  failed            14
  ...
  [FAIL] #46 direct_topology::tests::two_pad_net_gets_nonempty_topology
      panicked at .../unsupported.rs:13:9:
      time not implemented on this platform
  ... (13 more, all direct_topology::tests::*)
EXIT CODE: 1
```

14 failing tests, exit 1 — the exact panic from the incident logs, reproduced by the exact step I added. I also validated the happy path (`temper-pcl-ir`, the smallest tier: build → copy → run, exit 0, 2/2 passed) to confirm the loop's plumbing is correct end-to-end, not just its failure path.

**A wiring bug I found and fixed during that validation:** the `rust-checks` job runs inside `ghcr.io/bennetleff/temper-ci:latest`, whose `Dockerfile` sets `ENV CARGO_TARGET_DIR=/_temper-target` unconditionally — overriding `.cargo/config.toml`'s relative `target-shared` path that every *other* wasm-tier workflow hardcodes (they run on bare `ubuntu-latest`, without this container, so the relative path is correct for them). My first draft copied the hardcoded `target-shared/...` path from `wasm-tier-nightly.yml` verbatim; it would have `cp`'d a nonexistent path on every tier and failed the whole guard for a reason having nothing to do with wasm32 — exactly the "looks right, silently never runs" class of bug this repo's operating rules call out explicitly. Fixed by resolving `TARGET_DIR="${CARGO_TARGET_DIR:-target-shared}"` at run time. This is why I insisted on a real local build rather than trusting the YAML by inspection.

**Update, confirmed live on GitHub's own CI (PR #1297, run `32049901403`), not just locally.** This step was written and first committed while PR #1296 (`fix/wasm-tier-router-core-instant-panic`, a sibling agent's PR, not touched by this task) was still open. I opened PR #1297 with this change on top of pre-#1296 `main`, and the new step ran for real on GitHub's runners and reproduced the incident exactly:

```
=== wasm32 build+run: temper-rust-router-core (--features router-core-wasm-test-registry) ===
    Finished `release` profile [optimized] target(s) in 6.60s
  [FAIL] #46 direct_topology::tests::two_pad_net_gets_nonempty_topology
      panicked at .../unsupported.rs:13:9: time not implemented on this platform
  ... (13 more FAILs, identical to the local reproduction in the previous section)
```

(job conclusion: `WASM32 build + EXECUTE every wasm-tier registry (topology-driven, all 12 tiers)` → `failure`.) `#1296` merged shortly after (commit `fa067a952`). I merged current `main` into this branch (no conflicts — `#1296` only touches `packages/temper-rust-router-core/`, which this branch never edits) and re-ran the same build+execute pair locally against the merged tree: `temper-rust-router-core` now reports **3453/3453 passed, 0 failed, exit 0**. The same check, unmodified, correctly reports both the broken and the fixed state — the strongest evidence available that it is wired to the real substrate and not to a fixture.

Two things worth being explicit about, since main was independently confirmed (by the coordinating agent, cross-checking against #1296's own CI) to be **broadly red for reasons entirely unrelated to the wasm tier** — 10 failing Core Tests, a pre-existing clippy `type_complexity` error at `temper-rust-router/src/lib.rs:351`, LOC caps, mypy drift, repo-hygiene gates, and a net-classification test, per `Trunk Health`'s own report ("main is RED. Every open pull request inherits these failures regardless of its own content."):

1. **I did not chase `Rust Checks` green on PR #1297**, and did not attempt to fix any of that inherited redness — none of it is this task's to fix, and doing so would be scope creep into other agents' work.
2. Softening the new step (excluding `temper-rust-router-core`, adding `continue-on-error`, or any other narrowing) to dodge the *wasm-tier-specific* part of that redness while it was still present would have been exactly the "make a check pass by weakening it" move this repo's operating rules forbid, and would have recreated the coverage gap for the one crate that just proved it real. I did not do that; I let it report exactly what was true, and it is now provably true that the same check reports success once the underlying bug is actually fixed.

## 2. Evidence each change is correctly wired

I did not trust any of this by reading the YAML. For each change:

| Change | How I proved it's live, not just present |
|---|---|
| PR-path wasm32 build+execute (all tiers) | Ran the exact build+execute pair locally for two real tiers (`temper-pcl-ir` happy path, exit 0; `temper-rust-router-core` failure path, exit 1, reproducing the incident's own panic text) before writing a single line of YAML around them. Fixed a `CARGO_TARGET_DIR` container-vs-bare-runner path bug the local run surfaced. **Then confirmed on GitHub's own infrastructure**: opened PR #1297, watched run `32049901403`'s `Rust Checks` job actually execute the new step and reproduce the identical 14-test `Instant::now()` failure live; merged `main` (post-#1296) into the branch and re-ran locally to confirm the same tier now passes 3453/3453. Both the failing and passing state are demonstrated, not assumed. |
| Shell portability | The `rust-checks` job's existing comment states its `run:` steps execute under `sh` (dash), not bash — `-o pipefail` is illegal there. I wrote the new loop in POSIX sh (`IFS=$(printf '\t') read -r ...`, no `$'\t'`, no `[[ ]]`) and verified the tab-splitting logic under `/bin/dash` directly (`dash /tmp/test_loop.sh`), not just under my own bash-based shell. |
| `needs['local-sweep-r19'].result` bracket syntax | Used bracket notation rather than dot notation for hyphenated job IDs to remove ambiguity, then validated with `actionlint` (see below) rather than assuming the expression parses. |
| YAML validity, all 4 files | `python3 -c "import yaml; yaml.safe_load(...)"` on each edited/new file — all parse. |
| Actions-specific correctness (contexts, expressions, `needs`, `if:`, permissions, shellcheck-class issues) | Downloaded `actionlint` v1.7.7 (the exact pinned version `lint-workflows.yml` itself downloads and runs) and ran it against all four changed files, then against the full `.github/workflows/*.yml` set: **zero findings**, matching the ignore-pattern `lint-workflows.yml` itself uses (`-ignore 'constant expression "false" in condition'`). |
| `required-checks.json` / trigger-path manifest agreement | Ran `scripts/check_workflow_pr_triggers.py` (32 files, all compliant — my new workflow has no `push` trigger so the check does not even require its `# no-pr-trigger:` comment, which I added anyway for documentation) and `check_required_checks.py`'s `validate_trigger_manifest` + `validate_job_conditions` against `python-tests.yml` (the file the `rust-checks` step lives in) — both pass, confirming I did not silently desync the required-checks manifest from the workflow it describes. |
| Job-failure wiring (`report-deploy-failure`, `report-nightly-failure`) | Traced `needs:`/`if:` by hand against GitHub's own semantics: `needs: [gate, deploy]` + `if: needs.deploy.result == 'failure'` fires only when `deploy` actually ran and failed (not when `gate` skipped it for a superseded push, which produces `deploy.result == 'skipped'`, not `'failure'`). `needs: [local-sweep-r19, worker-dispatch-r19]` + `if: always() && (...)` deliberately overrides the *default* "skip if a dependency failed" behavior, matching `worker-dispatch-r19`'s own existing `if: ${{ !cancelled() }}` reasoning (the two jobs check independent things and must not suppress each other's reporting). I did not push a deploy or trigger these workflows for real, per this task's constraints — the wiring is proven by direct reading of GitHub's `needs.<job>.result` semantics and by `actionlint`'s static check of the same expressions, not by observing a live run. |
| `pcb/temper.kicad_pcb` untouched | `sha256sum pcb/temper.kicad_pcb` → `9c1f4a37b0...6bc3f6`, matches `docs/HANDOFF-2026-08-17.md`'s recorded value both before and after this work. |
| No stray diff | `git status` after all edits shows exactly the four workflow files (three modified, one new) plus this document — an incidental `Cargo.lock` change produced by my local validation builds was reverted (`git checkout -- packages/temper-wasm-test-runner/Cargo.lock`) before committing. |

## 3. What I deliberately did not change, and why

- **`packages/temper-rust-router-core/src/direct_topology.rs`** — PR #1296's file. Not touched. My new PR-path check will correctly fail against it until #1296 lands; that is intended, not a bug to fix here.
- **`wasm-tier-deploy.yml`'s trigger, gate/deploy job structure, or concurrency groups** — untouched. The new `report-deploy-failure` job is purely additive.
- **`wasm-tier-nightly.yml`'s R19 rotation, staleness check, or sweep logic** — untouched. The new `report-nightly-failure` job is purely additive.
- **`wasm-tier-pr.yml`** — untouched entirely. Its "no cargo on the PR path" decision is explicitly about *not re-deriving R19 native/wasm32 equivalence* on every PR (a documented, deliberate cost tradeoff, PR #971); it is not the same question as "does the wasm32 substrate at least build and run without panicking," which `rust-checks` now answers. I considered and rejected adding a `cargo` step there — it would reverse a decision that file's own header says must be "re-argued in the open" before reversing, and `rust-checks` was already the more natural home (it already had a same-purpose, differently-scoped step).
- **`required-checks.json`** — untouched. The new PR-path wasm32 coverage lives inside the already-required `rust-checks` job, so no new required-context wiring was needed.
- **Candidate 4 (PR verdict advisory→required)** — evaluated and explicitly left advisory; see §1 above for the reasoning.
- **No caching added for the new PR-path wasm32 builds.** This is a known, named limitation, not a hidden one: `rust-checks` currently has no `actions/cache` for its Cargo build cache at all (every native crate check/clippy call in that job is already a cold build every run), and the wasm32 target adds a *second*, wholly separate compiled artifact set with no cache either. I measured individual tier builds locally as fast (3–6s) but that was against an already-warm shared `target-shared/` from earlier work in this session, not a cold CI runner. If this step proves too slow in practice (a real risk, not dismissed), the fix is `actions/cache` keyed on `Cargo.lock` + target triple, added as a follow-up once real timing data exists — adding speculative caching now, untested, would be exactly the kind of unverified "looks right" change this task's own rules warn against.

## 4. Summary of files changed

- `.github/workflows/wasm-tier-deploy.yml` — new `report-deploy-failure` job.
- `.github/workflows/wasm-tier-nightly.yml` — new `report-nightly-failure` job.
- `.github/workflows/wasm-tier-staleness-watch.yml` — new workflow, standalone R5.1 check every 30 minutes.
- `.github/workflows/python-tests.yml` (`rust-checks` job) — new topology-driven "WASM32 build + EXECUTE every wasm-tier registry" step, additive to the existing two-crate build+clippy step.
