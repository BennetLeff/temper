<!-- provenance: commit=cbebb618a5c39cde45baae9dbc05dd3516f5a689 dirty=false -->

# O3: splitting `rust-checks`' clippy from its `cargo test` steps does not free a job — negative result

**Date:** 2026-08-11
**Commit:** `cbebb618a5c39cde45baae9dbc05dd3516f5a689` (`origin/main`)
**Scope:** `.github/workflows/python-tests.yml`'s `rust-checks` job (lines
836–994 at this commit); `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md`
Open Question **O3**.

## Bottom line

**No, the split is not worth doing, and it was not done.** `rust-checks` was
not modified. Splitting `cargo clippy` from the two `cargo test` steps would
turn 1 push-contended job into 2, permanently, for a benefit that evaporates
under measurement: the account's ~24-job concurrency ceiling is the binding
constraint (documented in a dozen other workflow files, and directly
observed below — a throwaway 1-job probe queued **12 minutes 25 seconds**
before a runner picked it up, while two `Python Tests` runs sat queued
15–20+ minutes at the same time), and this repo's own history already paid
down the opposite mistake once: `python-tests.yml:1007-1012` documents
merging three jobs into one specifically to stop paying a shared ~225s
prologue three times. Splitting `rust-checks` reintroduces exactly that
cost, on a job that runs on every push.

R25 relief for `temper-orchestration` and `temper-geometry` stays what D5.1
already found it to be: **0 jobs, 2 steps**, and that is a structural fact
of this job now, not a temporary inconvenience a reorganization fixes.

## What `rust-checks` actually does (read end to end)

Steps below the setup barrier, in order, with all four `!cancelled()`-gated
gates carrying independent verdicts (`python-tests.yml:864-875`):

1. `cargo check` — `temper-constraint-compiler` only.
2. `cargo clippy -D warnings --all-features --all-targets` — looped over
   **13** manifests (`python-tests.yml:884-898`), including both
   `temper-orchestration` and `temper-geometry`.
3. `cargo test --manifest-path packages/temper-orchestration/Cargo.toml`.
4. `cargo test --manifest-path packages/temper-geometry/Cargo.toml --no-default-features`.
5. `rustup target add wasm32-unknown-unknown`.
6. `cargo build --release --target wasm32-unknown-unknown` + `cargo clippy
   --no-default-features` for `temper-drc-rs` and `temper-geometry` (the
   wasm32 regression guard, unrelated to O3).

**What it shares:** one container (`ghcr.io/bennetleff/temper-ci:latest`),
one checkout, one `uv` install, and — load-bearing for this question — **one
`target-shared` Cargo build directory**, because `.cargo/config.toml` sets
`build.target-dir = "target-shared"` as a path relative to the invoking
working directory (repo root for every step in this job), and every `cargo`
invocation in the job runs from that same root. Steps 2–4 therefore compile
into the *same* target directory in sequence: by the time step 3 runs,
step 2's clippy loop has already built `temper-orchestration`'s full
dependency graph (clippy compiles dependencies normally; only the crate
under lint skips full codegen), so `cargo test` for it is fast. Same for
step 4 and `temper-geometry`.

**What is explicitly NOT shared across jobs:** `python-tests.yml:829-831`
states it plainly — "the cargo target dir is cold in this job (the workflow
caches no Rust artifacts anywhere)". No `actions/cache` step exists for
`target-shared` anywhere in this workflow. A second job is a second
runner with none of this warmth.

## Measured cost split (4 recent `main` runs, `gh api`)

| run | container init | clippy (13 crates) | test-orchestration | test-geometry | wasm32 build+clippy | **job total** |
|---|---:|---:|---:|---:|---:|---:|
| 31451399030 | 50s | 174s | 16s | 15s | 38s | **314s** |
| 31449354082 | 62s | 145s | 14s | 13s | 30s | **282s** |
| 31448148226 | 50s | 176s | 16s | 16s | 39s | **314s** |
| 31431418446 | 58s | 141s | 10s | 13s | 40s | **278s** |
| **avg** | **55s** | **159s (53.6%)** | **14s** | **14.25s** | **36.75s** | **297s** |

The two `cargo test` steps together average **28.25s — 9.5% of the job**.
Clippy alone averages **53.6%**. Removing the two test steps shrinks the job
by under a tenth; clippy is what actually costs the runner-minutes, and
clippy is the one thing that structurally cannot leave (`cargo clippy` needs
`cargo`, not a wasm32 runtime — parent-plan scope boundary, unchanged).

## The empirical A/B: what a split-out test job actually costs

Rather than reason from the shared-cache argument alone, a throwaway probe
workflow (`tmp-o3-split-probe.yml`, pushed to a scratch branch
`o3-probe-tmp`, run `31453273845`, then deleted — not part of this PR) ran
*only* the two `cargo test` steps in isolation: same container image, fresh
checkout, no prior clippy step to warm `target-shared`.

```
queued:    2026-08-11T02:44:24Z
started:   2026-08-11T02:56:49Z   (12m25s queued — see "Queue cost" below)
completed: 2026-08-11T02:58:50Z   (121s wall once running)

Set up job                 5s
Initialize containers      71s
Run actions/checkout@v7    6s
Install uv                 3s
Test temper-orchestration  16s   (vs 14s avg warm — no meaningful delta)
Test temper-geometry       13s   (vs 14.25s avg warm — no meaningful delta)
Stop containers            4s
```

**Two findings, one expected and one not:**

1. **Expected — fixed overhead is real and additive.** Container init +
   checkout + uv alone cost **~85s**. That is pure duplication: the unified
   job already pays this once (avg 55s init + checkout/uv, folded into the
   297s total) and amortizes it across clippy, both test steps, and the
   wasm32 guard. A split job pays it again, on every push, forever. 85s of
   pure overhead is *more* than the 28.25s the two test steps currently
   cost inside the shared job.
2. **Not expected — the cold-compile penalty for these two crates
   specifically is negligible.** `temper-orchestration` and
   `temper-geometry --no-default-features` are lean pure-Rust dependency
   graphs; cold-compiling them from nothing took 16s and 13s, statistically
   indistinguishable from the 14s / 14.25s they cost warm inside
   `rust-checks` today. The 159s clippy average is dominated by the other
   11 crates in the loop (pyo3, `rustsat-cadical`, `faer`, KiCad-adjacent
   parsers), not by these two. So the "cold recompile could exceed the
   savings" risk named in the task brief does not materialize here — but
   the fixed per-job container/toolchain overhead does, and by a wider
   margin than the thing being saved.

Net new-job cost, once running: 85s overhead + 29s test compute ≈ 114s,
against a job that currently spends 28.25s on these steps for free (already
inside a job that has to exist for clippy). That is worse by construction,
before queuing is even considered.

## Queue cost — observed live, not modeled

The probe queued for **12 minutes 25 seconds** before a runner started it —
for a 1-job, single-step workflow with no dependencies to resolve beyond
`uv` and the shared container image. At the same moment, `gh run list`
showed two `Python Tests` runs (`31453106146` queued since 02:41:03Z,
`31452876728` queued since 02:36:23Z) still queued 15–20+ minutes later,
alongside several `in_progress` jobs. This is the ~24-concurrent-job
ceiling that `board-regeneration.yml:6-13`, `codeql.yml:20`,
`required-checks.yml:19`, `regression.yml:11,27,54`,
`wasm-tier-nightly.yml:5,10`, `python-tests.yml:44,965,1011,1787,2252`, and
five more workflow files independently cite, observed binding in real time
rather than assumed from those comments. A second push-contended job joins
that same queue on every PR and every push to `main` — it does not run
"for free" just because it is short.

## Why the split cannot free a job even after tests are removed later

This is the structural point, independent of the timing numbers above.
Compare the two paths to U4's eventual state (tests fully retired from
`rust-checks` once R19 agreement is sustained):

- **No split (today's shape):** `rust-checks` = 1 job. Delete the two test
  steps → `rust-checks` = 1 job, clippy only. **1 job → 1 job.**
- **Split now, remove later:** `rust-checks` (clippy) + `rust-checks-tests`
  (test) = 2 jobs, immediately, for every push between now and whenever
  removal happens. Delete the test-only job once its content is empty →
  back to 1 job. **1 job → 2 jobs → 1 job.**

The end state is identical either way. Splitting does not create a job that
removal can later free — it creates a temporary *second* job today, pays
for it every push in the interim, and returns to the same place removal
would have reached without it. The only thing splitting changes is how
R25's ledger *describes* the eventual removal — "a job removed" instead of
"two steps removed" — which is vocabulary, not reclaimed capacity. R25 asks
for relief "counted per job or step actually removed," and it does not
prefer one honestly-reported unit over the other; it only forbids inflating
either. Removing two steps from a job that survives, stated as exactly
that, already satisfies it.

## Conclusion — R25 relief for these two crates is permanently zero

D5.1's finding stands, now for a *structural* reason rather than a
snapshot-in-time one: `temper-orchestration` and `temper-geometry`'s
`cargo test` steps cannot be reorganized into a freeable job, because (a)
clippy is immovable and always needs a job, (b) splitting adds a second
push-contended job whose fixed overhead (≈85s, measured) exceeds what it
would save (28.25s, measured), before the currently-binding ~24-job queue
ceiling (12m25s observed wait, live) is even counted, and (c) the end-state
job count is identical whether or not the split happens. U4's decision for
these two crates is "step removal, honestly counted as steps, not a job" —
documentation of a real but small relief, not reclamation of a runner slot.
`python-tests.yml` was not changed.

## Also established: which native tests run on no GitHub machine at all

Six crates were named as having no `cargo test` step on the PR path.
Measured directly (`cargo test --manifest-path ... [--no-default-features]`,
this commit, local `cargo 1.97.1`) and cross-checked against
`.github/workflows/*.yml` and `tools/wasm/wasm_tier_topology.json`, the six
split into three different situations — conflating them overstates the
"runs nowhere" number:

| crate | total native tests | PR path (`python-tests.yml`) | nightly (`wasm-tier-nightly.yml`, advisory) | runs on no GitHub machine, ever |
|---|---:|---|---|---:|
| `temper-quality-oracle` | 166 | clippy only | not in topology | **166** |
| `temper-io-types` | 201 | clippy only | not in topology | **201** |
| `temper-thermal` | 198 (191 `--no-default-features` + 7 `solve::tests::*`, default-feature-only) | clippy only | 191, `--no-default-features` (`native_test_args`, per topology) | **7** |
| `temper-rust-router-core` | 165 (147 `--no-default-features` + 18 `sat`-gated) | clippy only | 147, `--no-default-features` | **18** |
| `temper-constraint-compiler` | 97 (default and `--no-default-features` identical — no hidden feature-gated tests) | `cargo check` + clippy only, no `cargo test` | 97, `--no-default-features` | 0 |
| `temper-drc-rs` | 1,751 | none (clippy + `maturin` only) | 1,751, `--no-default-features` | 0 |

**392 tests execute on no GitHub-hosted machine at all, under any current
workflow definition** — `temper-quality-oracle` (166) + `temper-io-types`
(201) + `temper-thermal`'s `solve::tests::*` (7) + `temper-rust-router-core`'s
`sat`-gated `bmc`/`equivalence`/`solver` tests (18). The last two are
feature-gated: `wasm-tier-nightly.yml`'s `native_test_args` always passes
`--no-default-features` (per-tier, from the topology), and the PR path
never `cargo test`s either crate at all, so nothing anywhere ever builds
`temper-thermal` with `python` or `temper-rust-router-core` with `sat`.
`temper-quality-oracle` and `temper-io-types` are absent from
`wasm_tier_topology.json` entirely — clippy is their only CI exposure at
any cadence, confirmed by grep across every `.github/workflows/*.yml`
(only `python-tests.yml`'s clippy loop references either crate).

For the other four (`temper-drc-rs`, and the `--no-default-features`
portion of `temper-thermal` and `temper-rust-router-core`, plus
`temper-constraint-compiler`), the tests do run — nightly, natively, as the
comparison arm for R19 — via `wasm-tier-nightly.yml`'s topology-driven loop
(`tools/wasm/wasm_tier_topology.json`, all six tiers). Their `native_only`
counts (tests with no wasm32 counterpart, still executed nightly, not
"unexecuted") from the most recent completed nightly run's R19 comparison
(`31450493511`, `wasm-tier-nightly.yml`, commit `04d3d275`):

```
temper-drc-rs:   32 native-only, 0 wasm32-only  (1,751 native, 1,719 wasm32)
temper-geometry: 89 native-only, 0 wasm32-only  (already on the PR path — not "unexecuted anywhere")
temper-thermal:  48 native-only, 0 wasm32-only  (191 native, 143 wasm32)
```

matching the figures given in the task brief exactly.

**Caveat, measured rather than assumed:** `temper-design-bundle`,
`temper-rust-router-core`, and `temper-constraint-compiler` were added to
`wasm_tier_topology.json` and to the nightly's generic per-tier loop in
`ba4bfd73` (2026-08-10T20:28:41-06:00). Every nightly run in `gh run list`
as of this measurement predates that commit — **no nightly run has yet
executed the native `cargo test` arm for these three crates under the
current topology-driven workflow.** Their nightly coverage is declared, not
yet observed; the `native_only` figures for `temper-rust-router-core`
above (147 native vs 111 wasm32 tier size, per `wasm_tier_topology.json`'s
own comments) are therefore derived from the topology file's committed
analysis, not from a live R19 comparison artifact, and should be
re-confirmed against the next completed nightly run.

## What was and was not touched

- `.github/workflows/python-tests.yml` — **not modified.** No split
  performed; the negative answer above is the deliverable.
- `.github/workflows/wasm-tier-*.yml` — not touched, per constraint.
- `.github/required-checks.json` — not touched, per constraint.
- No crate under `packages/` was modified.
- The probe workflow (`tmp-o3-split-probe.yml`) and its branch
  (`o3-probe-tmp`) were pushed only to obtain the A/B timing above and were
  deleted before this PR was opened; run `31453273845` remains visible in
  Actions history as its record.

## Sources

- `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md` — O3, D5.1, R25,
  U4.
- `.github/workflows/python-tests.yml:836-994` (`rust-checks`),
  `:829-831` (no cross-job Rust artifact cache), `:1007-1012` (the
  three-jobs-into-one merge this split would reverse).
- `.cargo/config.toml` — `target-shared` build-dir sharing mechanism and its
  worktree caveats.
- `tools/wasm/wasm_tier_topology.json` — six-tier topology, `native_test_args`
  per tier, the feature-gated native_only analysis for
  `temper-rust-router-core` and `temper-constraint-compiler`.
- GitHub Actions runs: `31451399030`, `31449354082`, `31448148226`,
  `31431418446` (`rust-checks` timing sample), `31453273845` (A/B probe,
  deleted workflow), `31450493511` (most recent completed
  `wasm-tier-nightly.yml` run, R19 `native_only` figures).
