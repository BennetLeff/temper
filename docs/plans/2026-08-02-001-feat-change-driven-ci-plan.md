---
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
date: 2026-08-02
plan_type: infrastructure
---

# Change-Driven CI — Plan

## Goal Capsule

**Objective:** Reduce the CI cost of unrelated changes. Today every PR runs
the full ~2.5 h Python suite (Core, Extended ×2, Invariant ×4, Requirements,
plus 20 jobs total) even for docs-only and pure-Rust changes — the cause of
the multi-hour runner backlog and the rebase→re-run churn loop this repo has
been stuck in. Change-driven CI makes each job run only when its declared
trigger paths changed, with a conservative catch-all, so cheap changes get
cheap CI while the enforced gates stay enforced.

**Product authority:** repo owner (adopts the path→job mapping).

**Open blockers:** none — the required-check architecture
(`required-checks.yml` + `scripts/check_required_checks.py`) already exists
and is the extension point; the SKIPPED-as-pass contract is a change to that
checker, scoped below.

## Product Contract

### Problem

The required "Required Python Tests" aggregate evaluates 17 required
contexts; each PR pays the full suite regardless of what it touches. The
resulting backlog (runs queued 2.5 h+) compounds with the rebase loop: every
rebase re-triggers the entire suite, and the suite re-runs on every main
movement. A docs-only plan PR (#551/#562/#563/#565) costs the same CI as a
production-code PR.

### Recommended path (settled)

**Layered required contexts**, split by cost and domain:

| Class | Jobs | Trigger rule |
|---|---|---|
| Always-run | Type Check, LOC Cap, Generated Repo State, Provenance & Anti-Vacuity, Cross-Source Consistency, Pipeline Closure, Known-Failure Pins | unconditional (cheap, cross-cutting) |
| Path-conditional | Core Tests, Extended (bundle/checks, cp-sat fast, cp-sat slow), Invariant (×4 groups + rest), Requirements Tests, Repo Hygiene, Cargo/Rustc Smoke, Rust Checks, Board & Netlist Gates | run only when their trigger paths changed |

**The SKIPPED-as-pass contract (the crux):** `scripts/check_required_checks.py`
currently treats any non-`success` conclusion — including `skipped` — as
failed (verified: `run.conclusion == "success"` is the only pass branch). The
change: a `skipped` required context passes **only when the gate verifies the
skip itself** — it reads the PR's changed-file list (via the API, on the base
checkout under `pull_request_target`, so a PR cannot weaken its own filter)
and confirms no changed file matches the job's declared trigger paths.
Unverifiable skips stay failed.

**Catch-all rule:** `pyproject.toml`, `uv.lock`, `.github/workflows/**`,
`scripts/**`, and any path not mapped to a job's trigger set → all
path-conditional jobs run. Ambiguity defaults to running.

### Scope (in)

- The layered required-context split above.
- Per-job trigger-path declarations (path→job mapping) and the conservative
  catch-all.
- The `check_required_checks.py` SKIPPED-as-pass contract with gate-verified
  skips.
- The workflow changes (`paths`/`if:` conditions or a changed-files action)
  that actually skip jobs.

### Scope (out)

- Merging/consolidating CI jobs, caching, or parallelization.
- Any reduction of the *enforced* check set (the 17 required contexts stay).
- Fixing the currently-red gates themselves (e.g. the K3 clearance gate) —
  this plan makes CI cheaper, not green.
- Job timing/budget reallocation.

### Success criteria

- A docs-only PR runs **no** path-conditional Python/Rust suite (CI wall time
  well under the current ~2.5 h; the cheap always-run jobs still run).
- A pure-Rust PR (one crate) runs only that crate's checks + the catch-all
  set.
- The required aggregate goes green from skips only when
  `check_required_checks.py`'s own changed-file verification confirms the
  skip — a filter bug is caught by the gate, not silently.
- The runner backlog (runs queued hours) clears.

### Acceptance examples

- G1. A PR touching only `docs/plans/*` shows the heavy suites as `skipped`
  and the required aggregate green.
- G2. A PR touching `packages/temper-geometry/**` runs geometry's suites but
  skips, e.g., the thermal or bundle suites that declare disjoint paths.
- G3. A PR touching `uv.lock` runs everything (catch-all fires).
- G4. A PR whose change list touches a path the skip-verification cannot map
  (or the verification API fails) → the skipped job is treated as failed, not
  passed (fail-closed).

### Key decisions (settled)

- **Layered** (always-run + path-conditional), not all-conditional or
  non-required-only (the expensive jobs are the required ones; the cheap ones
  stay unconditional so cross-cutting changes never skip their checks).
- **Gate verifies the skip** — `check_required_checks.py` independently
  confirms no changed file hits a skipped job's trigger paths, on the base
  checkout (a PR cannot weaken its own filter).
- **Conservative catch-all** — unmatched paths run everything; ambiguity
  defaults to running.

### Outstanding questions

- OQ-A. **Path→job mapping granularity:** one crate per job's trigger set
  (finer, more mapping) vs crate-group granularity (coarser, simpler). Default
  recommendation: crate-group (e.g. all `packages/temper-*/**` for the
  extension gates; `packages/temper-placer/**` for the placer suites), refined
  by the planner.
- OQ-B. **Verification failure mode:** when the changed-files API fails or a
  file is unmapped, treat as "run everything" (safe) vs "fail the skip"
  (stricter). Recommendation: unmapped → run everything; API failure → fail
  closed (treat the skip as failed).
- OQ-C. **Rollout:** land the checker contract + mapping in one PR (atomic)
  vs land the checker contract first (skips always fail until filters exist —
  neutral, since no jobs skip yet), then the filters. Recommendation: one
  atomic PR; the checker change alone is inert.

## Sources / Research

- `.github/required-checks.json` — the `trigger_paths` + `required_contexts`
  manifest (already gates evaluation; jobs themselves run unconditionally).
- `scripts/check_required_checks.py` — the manifest evaluator; the
  SKIPPED-as-pass contract lives here (verified: `success` is the only pass).
- `.github/workflows/required-checks.yml` — runs on `pull_request_target`
  against the base checkout (the security property the skip-verification
  inherits).
- `.github/workflows/python-tests.yml` — the ~20 jobs; job inventory used for
  the layered split.
- The 2026-08-01 CI backlog/churn observations (runs queued 2.5 h+; rebase →
  full-suite re-run loop).
