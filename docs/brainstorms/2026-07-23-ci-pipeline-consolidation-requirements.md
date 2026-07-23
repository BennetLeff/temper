---
date: 2026-07-23
topic: ci-pipeline-consolidation
---

# CI Pipeline Consolidation: Reusable Workflows and Hard-Fail Gate Migration

## Summary

Consolidate 22 GitHub Actions workflow files by extracting common boilerplate (checkout, setup-uv, cache-venv, uv-sync, Rust build) into reusable workflows. Migrate remaining `continue-on-error: true` soft-launch gates to hard-fail where the prerequisite conditions have been met. Reduce the `python-tests.yml` monolith (7 jobs with duplicated setup) into a single job matrix or decomposed workflow with a shared setup job. Target: 22 workflows reduced to ~15 with ~200 fewer lines of duplicated YAML.

---

## Problem Frame

The `.github/workflows/` directory has 22 workflow files with significant duplication and inconsistent patterns:

**Boilerplate duplication (appears in ~15 workflows):**
```yaml
- uses: actions/checkout@v4
- uses: astral-sh/setup-uv@v4
- name: Set up Python
  run: uv python install 3.12
- name: Cache virtualenv
  uses: actions/cache@v4
  with:
    path: .venv
    key: venv-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('uv.lock') }}
- name: Install dependencies
  run: uv sync --all-packages
```
This 15-line block is copy-pasted into ~15 files. Changing the Python version, cache key, or install command requires editing 15 files.

**`python-tests.yml` monolith:**
The `test` job runs 7 sub-jobs (`test`, `checks`, `closure`, `regression`, `loc-cap`, `type-check`, `astar-nightly`) with repeated virtualenv caching and Rust build steps. The Rust compilation step (building `temper-drc-rs` and `temper-rust-router` via PyO3/maturin) is duplicated in at least 3 jobs.

**`continue-on-error: true` saturation:**
A substantial number of CI steps run with `continue-on-error: true`. Current count: **40 steps across 11 workflow files** (measured 2026-07-23). These represent soft-launch gates whose prerequisite conditions may now be met (e.g., the import-linter soft-launch period ended 2026-07-06 per AGENTS.md). Soft-launch gates that have passed their cutover dates but still run warn-only create a false sense of safety -- CI is green but violations are present and unaddressed.

**Inconsistent invocation patterns:**
- `uv run python scripts/<name>.py` (primary)
- `uv run python3 scripts/<name>.py` (used in some places)
- `python3 scripts/<name>.py` (without `uv run`, used in Makefile)
- `uv run python -m temper_placer.regression.cli` (package invocation)

**Missing test target in Makefile:**
The root `Makefile` has targets for `build`, `netlist`, `schematics`, `route`, `drc`, `regression`, and `perf-regression` -- but no `test` target. Developers must read AGENTS.md or CI workflow YAML to know how to run tests locally.

---

## Requirements

### Reusable Workflows

- **R1.** Extract a `_setup-python.yml` reusable workflow that encapsulates checkout, uv setup, Python installation, virtualenv caching, and dependency installation. All workflows that currently duplicate this block call the reusable workflow instead.
- **R2.** Create a `_build-rust/action.yml` composite action that encapsulates Rust toolchain setup and `maturin develop` for `temper-drc-rs` and `temper-rust-router`. The composite action runs within the same job as the Python tests, preserving the virtualenv.
- **R3.** The reusable workflows accept parameters for Python version (default `3.12`), Rust toolchain (default `stable`), and whether to install all packages or a subset. This prevents parameter lock-in while eliminating duplication.

### Python Tests Monolith Decomposition

- **R4.** Decompose `python-tests.yml`'s 7 jobs into a strategy matrix where jobs share setup. Jobs that don't need Rust compilation (linting, type checking, dead-code scanning) skip the Rust build step via a matrix parameter.
- **R5.** Alternative to R4: split `python-tests.yml` into separate workflow files (`lint.yml`, `type-check.yml`, `closure-test.yml`, `regression.yml`) that each call the reusable setup workflows. This makes CI failure attribution clearer (a lint failure doesn't show as "python-tests / test (checks)").

### Hard-Fail Migration

- **R6.** Audit all `continue-on-error: true` steps for cutover dates. Steps whose soft-launch period has expired are migrated to `continue-on-error: false` (the default) or have the flag removed. This includes:
  - Import-linter boundary enforcement (soft-launch ended 2026-07-06 per AGENTS.md)
  - Coverage gate (warn-only pending Phase 1 paydown prerequisite)
  - Any step tagged `temper-xxx` where the ticket has been resolved
- **R7.** Steps that remain warn-only after audit must have an explicit `# TODO: temper-NNN -- hard-fail after YYYY-MM-DD` comment with a valid ticket reference and date. No anonymous `continue-on-error: true` without justification. The TODO comment format is validated by a regex lint: `TODO: temper-\d+ -- hard-fail after \d{4}-\d{2}-\d{2}`.
- **R7a.** Add a `lint-workflows` CI job step (or extend the existing workflow linting) that greps for `continue-on-error:\s*true` lines not followed by a `# TODO: temper-\d+` comment and fails CI with a message listing the unannotated steps. This enforces the convention as an ongoing invariant, not a one-time cleanup.

### Makefile Test Target

- **R8.** Add a `test` target to the root `Makefile` that runs both Python and firmware test suites via a wrapper script that captures individual exit codes, reports which target(s) failed, and exits with the OR of all exit codes. Use `set +e` to continue after first failure. The firmware test subtarget (`test-firmware`) detects missing ESP-IDF tooling and fails with a clear message. The top-level `test` target skips firmware tests with a warning if ESP-IDF is absent, running only Python tests. Full CI runs always include firmware tests via the container image.
- **R9.** Add `test-placer` and `test-firmware` subtargets for selective testing.

### Script Invocation Consistency

- **R10.** Standardize all CI workflow script invocations on `uv run python scripts/<name>.py`. Eliminate bare `python3` invocations (which may use a system Python without the project's virtualenv). The root `Makefile` `test` target (R8) must also use `uv run` invocations consistently, not bare `python3`.
- **R11.** The `_build-rust/action.yml` composite action includes a `actions/cache@v4` step keyed on `hashFiles('**/Cargo.lock')` for the `target/` directory, in addition to the virtualenv cache.

---

## Acceptance Examples

- **AE1. Covers R1.** Given `_setup-python.yml` exists as a reusable workflow, when a new CI workflow is added, it contains `uses: ./.github/workflows/_setup-python.yml` with 3 lines of parameters instead of 15 lines of duplicated steps.
- **AE2. Covers R6.** Given the import-linter cutover date (2026-07-06) has passed, when a PR introduces a new import boundary violation, CI fails (does not warn). The `continue-on-error: true` flag is removed from the import-linter step.
- **AE3. Covers R8.** Given `make test` runs from the repo root, it executes all Python and firmware tests and exits 0 on success, non-zero on any failure.
- **AE4. Covers R7.** When `rg 'continue-on-error:\s*true' .github/workflows/ --include '*.yml'` runs, every matching line is immediately followed by a `# TODO: temper-NNN -- hard-fail after YYYY-MM-DD` comment on the same line or the line above.
- **AE5. Covers R10.** When `rg 'python3 ' .github/workflows/ --include '*.yml'` runs (excluding actionlint), it returns zero hits.

---

## Success Criteria

- `python-tests.yml` has <=3 jobs (down from 7) or is split into focused workflow files
- Zero `continue-on-error: true` steps without an explicit `# TODO: temper-NNN -- hard-fail after YYYY-MM-DD` comment
- All CI workflows use `uv run python scripts/<name>.py` consistently (no bare `python3`)
- `make test` runs the full test suite and exits with the correct code
- Total CI workflow YAML lines reduced by >=200 (baseline: **2,797 lines** measured 2026-07-23 via `wc -l .github/workflows/*.yml | tail -1`, excluding `.github/workflows/actionlint.yaml`) Measured as `wc -l .github/workflows/*.yml | tail -1` excluding `.github/workflows/actionlint.yaml`.

---

## Scope Boundaries

- **In scope:** GitHub Actions workflow consolidation, reusable workflow extraction, hard-fail migration of expired soft-launch gates, Makefile `test` target, script invocation standardization.
- **Out of scope:** Changing what any CI gate checks. Gate logic is unchanged. However, expired soft-launch gates now block instead of warn, which changes merge-blocking behaviour for PRs with violations. Existing soft-launch gates that have not met their hard-fail prerequisites retain their current behaviour.
- **Out of scope:** Migration to a different CI system (e.g., Buildkite, CircleCI). GitHub Actions remains the CI platform.
- **Out of scope:** Docker image maintenance (`ghcr.io/bennetleff/temper-ci`), though the reusable workflows may reduce the number of places the image is referenced.
- **Out of scope:** Script consolidation into `_lib/` (covered by separate brainstorm).

---

## Key Decisions

- **Composite action for Rust build over reusable workflow.** `maturin develop` writes to the current virtualenv; a separate `workflow_call` job would lose this artifact. The Rust build runs as a composite action step within the same job. Reusable workflows (`_setup-python.yml`) are used for the Python-only setup.
- **Split `python-tests.yml` over matrix decomposition.** Splitting the monolith into focused workflow files (`lint.yml`, `type-check.yml`, `closure-test.yml`) makes CI failure attribution clearer and allows independent workflow triggers (e.g., lints on every push, closure test only on PR to main). A strategy matrix is simpler but obscures which check failed.
- **Hard-fail migration is ratcheting.** Once a gate flips from warn-only to hard-fail, it cannot revert. This prevents oscillation where a gate is hardened, causes pain, and is softened again.

---

## Dependencies / Assumptions

- **Methodology.** All implementation follows TDD (Red-Green-Refactor per AGENTS.md). Reusable workflows are validated via property-based tests (Hypothesis) for invariants: given any valid input parameter combination, the workflow completes without error. Base cases are proven correct via unit tests; generalization follows by construction (inductive reasoning over workflow parameter space). No reusable workflow ships without at least one PBT invariant proving it composes correctly with downstream consumers.
- **Assumption:** GitHub Actions supports `workflow_call` with `secrets: inherit` for the reusable workflows. Verified against GitHub Actions documentation as of July 2026.
- **Assumption:** The Rust build (`maturin develop`) runs as a composite action within the same job as Python tests, preserving the virtualenv. The virtualenv cache key includes `hashFiles('uv.lock')`; the Rust build cache must key on `Cargo.lock` separately (see R11).
- **Dependency:** The import-linter gate's cutover date (2026-07-06) has passed. If there are remaining soft-launch violations, a separate PR must resolve them before the hard-fail migration.

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R6][User decision]** Which `continue-on-error: true` gates should migrate to hard-fail vs. remain warn-only? The import-linter gate (cutover past) and coverage gate (Phase 1 prerequisite status unclear) need explicit decisions. The coverage gate's AGENTS.md note says "warn-only until Phase 1 paydown prerequisite is met" -- is that prerequisite met?

### Deferred to Planning

- **[Affects R2][Technical]** What is the exact set of jobs that need Rust compilation? `closure-test`, `regression`, and `astar-nightly` certainly need it. Do `lint` and `type-check` ever import Rust-backed modules during static analysis?
- **[Affects R3][Technical]** Should the reusable setup workflow accept a `packages` parameter to select which extras to install (`--all-packages` vs `--package temper-placer`), or is `--all-packages` always correct for CI?
