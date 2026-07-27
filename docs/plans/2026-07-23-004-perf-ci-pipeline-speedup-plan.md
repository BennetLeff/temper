---
plan_id: 2026-07-23-004
title: CI Pipeline Speedup — Eliminate Redundant Work in Python Tests
type: perf
status: stale
created: 2026-07-23
tags: [ci, github-actions, performance, python-tests]
swept: 2026-07-25
swept_basis: "insufficient evidence - needs human triage"
---

## Summary

The Python Tests workflow (`.github/workflows/python-tests.yml`) takes 13–22 min per
PR run due to three forms of redundant work: `uv sync --all-packages` runs 4 times,
Rust crate release builds and clippy run twice, and the closure test incurs 3.5 min
of setup overhead on a bare runner. This plan eliminates all three, targeting a
pipeline wall time of 6–9 min for the Python Tests workflow.

## Problem Frame

Data from three recent PR runs and two main-branch runs (2026-07-23):

| Bottleneck | Current waste | Recoverable |
|---|---|---|
| Quadruple `uv sync --all-packages` | 3 setup jobs × ~3.5 min each, plus closure's own sync | 6–8 min |
| Duplicate Rust builds + clippy | `test` and `checks` independently build 3 crates + run clippy on 6 crates | 3–4 min |
| Closure test setup on bare runner | `uv sync --all-packages` (3.5 min) + uv/python install on cold runner | 3–4 min |
| **Total** | | **12–16 min** |

The effective work (actual test execution) is ~4–5 min. The rest is infrastructure
duplication.

## Scope Boundaries

**In scope:**
- `.github/workflows/python-tests.yml` — jobs `test`, `checks`, `closure`, plus the
  `checks-setup`, `type-check-setup`, `loc-cap-setup` job stanzas
- `.github/workflows/_setup-python.yml` — only as needed to detach consumers

**Out of scope:**
- Other CI workflows (regression.yml, placer-regression.yml, cp-sat-benchmarks.yml, etc.)
- Changing the closure test algorithm or reducing its placement/router computation time
- Changing the actual test suite content or coverage
- Modifying the `temper-ci` Docker image (`ci.Dockerfile`)
- The `continue-on-error: true` / 2026-09-01 hard-fail deadline — those are separate

**Deferred to Follow-Up Work:**
- Apply the same `_setup-python.yml` elimination to other workflows that use it (none
  currently, but if added in the future)
- Evaluate whether `cargo check` and `clippy` can be collapsed by upgrading to a
  shared target dir pre-warmed in the Docker image (already partially done via
  `CARGO_TARGET_DIR=/_temper-target`)
- Parallel test suite flakiness (`continue-on-error: true` on the parallel step
  in `checks`) — separate issue from speed

## Key Technical Decisions

### KTD-1: Merge `checks` into `test` rather than extract shared artifacts

Extracting Rust builds into a separate job with artifact handoff (upload/download
target dirs and venv) adds 2 extra jobs and ~30 sec artifact transfer overhead.
Merging produces a single job that takes ~7 min wall time but eliminates all
duplication without new infrastructure.

The merged job stays below the 15 min timeout. The parallel test suites inside
the merged step (rust_integration, invariant, cp-sat, workflow, misc checks) already
run concurrently within a single `run:` block, so there is no parallelism loss for
the test suites themselves — only the outer job boundary is collapsed.

### KTD-2: Remove `_setup-python.yml` from python-tests.yml entirely

Each consumer already does its own checkout, venv cache, and `uv sync`. The setup
jobs add a separate checkout + `uv sync --all-packages` on a separate runner, then
the dependent job restores the venv and syncs again. The only value was warming the
venv cache — but `test` already does that faster (14 sec on cache hit).

The three consumers (`checks`, `type-check`, `loc-cap`) currently use
`cache/restore@v4` (restore-only) for the venv, relying on their setup job to write
the cache. After removal, each consumer switches to `cache@v4` (save+restore).

### KTD-3: Run closure on temper-ci image, not ubuntu-latest

The temper-ci image (`.github/docker/ci.Dockerfile`) provides Python 3.12, uv,
Rust toolchain, and KiCad 10.0 pre-installed. The closure test needs KiCad CLI
(for DRC) and the full Python dependency tree (JAX, temper-placer). Moving to
the temper-ci image eliminates the 45 sec container initialization overhead
(ubuntu-latest→temper-ci pull) and provides KiCad without `apt-get install`.

The venv cache key is identical across all jobs (`venv-${{ runner.os }}-...`).
The `test` job saves the venv to cache. Because `closure` currently starts before
`test` finishes, its cache read sees a cold cache. After the merge (KTD-1), the
combined job and closure start at roughly the same time — closure still reads a
cold cache on the first run after a lockfile change. On subsequent runs (same
`uv.lock`), closure's `uv sync` completes in ~14 sec via cache hit.

## Requirements

- **R1:** The Python Tests workflow must complete in ≤10 min on PRs for the
  common case (packages/** changes, warm caches).
- **R2:** No test coverage is removed. All test suites currently exercised by
  `test` and `checks` continue to run.
- **R3:** All gate checks (ruff, vulture, manifest, sunset, root hygiene, physics
  provenance, import boundary, trace invocations) continue to run.
- **R4:** The closure test continues to run with identical semantics.
- **R5:** Existing `concurrency` groups and `cancel-in-progress` behavior are preserved.
- **R6:** Existing `timeout-minutes` values are preserved or tightened.

## System-Wide Impact

- **Python Tests workflow** (`.github/workflows/python-tests.yml`): 3 job stanzas
  removed (checks-setup, type-check-setup, loc-cap-setup), 2 jobs merged (checks
  into test), 1 job modified (closure gets container and uses `cache@v4` instead
  of cold `uv sync`).
- **`_setup-python.yml`**: No longer referenced from `python-tests.yml`. If no
  other workflow references it, it can be removed in a follow-up cleanup.
- **Docker build workflow** (`docker-build.yml`): No change needed — the temper-ci
  image is already built and published.
- **Other workflows**: No impact. `regression.yml`, `placer-regression.yml`, etc.
  are unchanged.

## Implementation Units

### U1: Remove `_setup-python.yml` consumers from python-tests.yml

**What:** Delete the `checks-setup`, `type-check-setup`, and `loc-cap-setup` job
stanzas. Remove the `needs: checks-setup`, `needs: type-check-setup`, `needs:
loc-cap-setup` from the `checks`, `type-check`, and `loc-cap` jobs respectively.
In those three consumer jobs, change `actions/cache/restore@v4` for the venv to
`actions/cache@v4` (save+restore) so they self-populate the cache.

**Files:**
- `.github/workflows/python-tests.yml`: remove lines defining `checks-setup:`,
  `loc-cap-setup:`, `type-check-setup:` jobs and their `uses:` stanzas; update
  `needs:` in `checks:`, `type-check:`, `loc-cap:`; change `cache/restore@v4`
  to `cache@v4` for venv in those three jobs.

**Test Scenarios:**
- Run workflow on a branch changing `packages/` — verify `checks`, `type-check`,
  `loc-cap` start immediately (no setup dependency) and complete successfully.
- Verify cold-cache run: delete the venv cache, run workflow, confirm all three
  jobs populate the cache and succeed.
- Verify warm-cache run: re-run with same `uv.lock`, confirm `uv sync` steps
  complete in <30 sec each.
- Verify that removing `needs:` does not break the `closure` or `regression`
  jobs (they have no dependency on setup jobs).

### U2: Merge `checks` into `test`

**What:** Move all test suites and gate checks from the `checks` job into the
`test` job. The `test` job already builds all Rust crates, runs clippy, and runs
core placer tests. Append the checks-only steps: domain model codegen drift check,
design-bundle cargo test + Python load, parallel test suite block
(rust_integration, invariant, cp-sat, workflow, misc), netlist + schematic drift
check, config reference check, board identity gate, ruff, vulture, manifest,
sunset, root hygiene, physics provenance, import boundary, trace invocations.

Delete the `checks` job stanza. Remove unused `checks:` from the workflow.

**Files:**
- `.github/workflows/python-tests.yml`: merge `checks` job steps into `test` job;
  remove `checks:` job definition; if `checks-setup` already removed in U1, ensure
  no dangling references remain.

**Sequencing note:** Do U1 first so the `checks` job is free of its setup dependency
before being merged.

**Test Scenarios:**
- Run workflow on a branch changing `packages/` — verify the single merged job
  completes in <10 min and all test suites pass.
- Verify that a clippy warning in a non-PyO3 crate causes the merged job to fail
  (confirming clippy still runs).
- Verify that a ruff violation causes the merged job to fail (confirming ruff gate
  still runs with `continue-on-error` semantics preserved or intentionally changed).
- Verify that a coverage regression causes the merged job to fail (confirming
  coverage gate still runs).
- Verify that both `temper-rust-router`, `temper-drc-rs`, and `temper-constraints`
  are built exactly once (check step logs for single `maturin develop` invocation
  per crate).

### U3: Move closure test to temper-ci container

**What:** Add `container: ghcr.io/bennetleff/temper-ci:latest` to the `closure`
job. Remove the `uv python install` step (Python 3.12 is in the image). Keep the
venv cache step (replace plain `cache@v4` with save+restore if needed — it already
uses `cache@v4` which saves). The `uv sync --all-packages` step remains but will
hit the cache on warm runs.

**Files:**
- `.github/workflows/python-tests.yml`: add `container:` block to `closure:` job,
  matching the image and options used by `test` job.

**Test Scenarios:**
- Run workflow on a branch — verify closure test runs inside the temper-ci image
  and completes successfully.
- Verify closure test output (DRC errors, router completion pct) matches a
  baseline run on ubuntu-latest.
- Verify cold-cache (delete venv cache): `uv sync` completes successfully within
  the image.
- Verify warm-cache: `uv sync` completes in <30 sec.

## Verification

After all three units land, run the workflow twice on the same `packages/**` PR:
once cold (delete caches) and once warm. Verify:

1. Cold run: total pipeline time <14 min (down from 21+ min)
2. Warm run: total pipeline time <10 min (down from 13+ min)
3. All test suites pass with identical results to pre-change baseline
4. All gate checks pass (ruff, vulture, manifest, etc.)
5. Closure test DRC output matches baseline
6. No "skipped" jobs appear where they shouldn't
7. `git diff --exit-code` checks (config.h, transition table, schematics, domain
   models) all pass — confirming codegen drift gates still fire

Verify against the CI run data from `python-tests.yml` on main to confirm no
regression in test coverage or check thoroughness.
