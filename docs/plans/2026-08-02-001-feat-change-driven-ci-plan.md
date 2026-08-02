---
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
date: 2026-08-02
plan_type: infrastructure
---

# Change-Driven CI — Plan

## Goal Capsule

**Objective:** Reduce the CI cost of unrelated changes. Every PR today runs
the full ~2.5 h Python suite even for docs-only and pure-Rust changes — the
cause of the multi-hour runner backlog and the rebase→re-run churn loop. Each
workflow job should run only when its trigger paths changed, with a
conservative catch-all, so cheap changes get cheap CI while the enforced
gates stay enforced.

**Product authority:** repo owner (adopts the path→job mapping).

**Open blockers:** none — `required-checks.yml` + `scripts/check_required_checks.py`
are the extension point (verified: `GitHubApi.pull_request_files()` already
exists and is called; `pull-requests: read` is granted; the checker and
manifest run from `base.sha`, so a PR cannot weaken its own filter).

## Product Contract

### Problem

The required "Required Python Tests" aggregate evaluates required contexts;
each PR pays the full suite regardless of what it touches. A docs-only plan
PR costs the same CI as a production-code PR. The review of this plan
(2026-08-02) verified the problem statement: `docs/plans/**` and
`docs/evidence/**` are workflow trigger paths today, so docs-only PRs
genuinely run all ~20 jobs.

### The mapping model (three categories — revised after review)

Every changed path resolves to exactly one category:

1. **Mapped to jobs** — the path is in one or more jobs' trigger sets; those
   jobs run.
2. **Mapped to nothing** — `docs/**` (plans, evidence, STRATEGY, BOM,
   traceability-registry, `**/TRACEABILITY`) deliberately triggers **no**
   path-conditional job. This is what makes docs-only PRs cheap.
3. **Catch-all** — `pyproject.toml`, `uv.lock`, `.github/workflows/**`,
   `scripts/**`, and any path not in category 1 or 2 → all path-conditional
   jobs run. Ambiguity defaults to running.

**The trigger-envelope fix (required for the catch-all to be real):** the
workflow-level `paths:` list and `required-checks.json` `trigger_paths`
(currently identical by the checker's `validate_trigger_manifest` cross-check)
must be extended with `uv.lock` and `.github/workflows/**`. Today a PR
touching only `uv.lock` or 23 of the 25 workflow files does not trigger
`python-tests.yml` at all — the aggregate goes green-with-nothing via the
checker's no-match pass. The catch-all cannot fire for paths outside the
envelope, so the envelope must be the catch-all's domain.

### Layered required contexts

| Class | Jobs | Trigger rule |
|---|---|---|
| Always-run (cheap) | Type Check, LOC Cap, Generated Repo State, Known-Failure Pins, Pipeline Closure | unconditional |
| Path-conditional (domain-scoped) | Core Tests, Extended (bundle/checks, cp-sat fast, cp-sat slow), Invariant (×4 + rest), Requirements Tests, Repo Hygiene, Cargo/Rustc Smoke, Rust Checks, Board & Netlist Gates, Cross-Source Consistency, Provenance & Anti-Vacuity | run when trigger paths changed |

Revision after review (F4): Cross-Source Consistency and Provenance &
Anti-Vacuity carry the full heavy setup (3× maturin + `uv sync --all-packages`
+ `make netlist`, ~4-8 min each) — they are NOT cheap. They are re-classified
as path-conditional on their enumerable input sets (`elec/**`, `pcb/**`,
`firmware/components/control/pll_control.h`, `docs/STRATEGY.md`,
`scripts/gen_domain_models.py` + templates, netclass-rules generator,
`packages/temper-drc-rs/src/board.rs`). Pipeline Closure is
`continue-on-error: true` today; it stays always-run but is advisory — its
real cost is the shared setup, which a docs-only PR now skips.

### The SKIPPED-as-pass contract (the crux)

`scripts/check_required_checks.py` currently treats any non-`success`
conclusion — including `skipped` — as failed (verified). The change:

- A `skipped` required context passes **only when the checker verifies the
  skip itself**: it reads the PR's changed-file list (existing
  `GitHubApi.pull_request_files()`, fetched once at start, from the
  `base.sha` checkout under `pull_request_target`) and confirms no changed
  file matches the job's declared trigger paths.
- Verification is inline in the same poll loop that gates the aggregate —
  there is no window where the aggregate goes green from an unverified skip.
- **Skip conditions are pure path predicates, and nothing else** (revised
  after review F5): per-job trigger sets live in the manifest
  (machine-readable), the workflow job conditions are generated from or
  mechanically cross-checked against the manifest (extend
  `validate_trigger_manifest` to per-job triggers), and patterns are
  restricted to the glob subset `path_matches` implements. This closes the
  "skip happened for the wrong reason" laundering surface.
- **Fail-closed on unmapped**: if verification cannot confirm a skip (API
  failure, unmappable path), the skip is treated as failed. The
  "run everything" default for category-3 paths is implemented by the
  *workflow conditions*; the checker's own rule for an unverified skip is
  always fail-closed.

### Scope (in)

- The three-category mapping, the layered split, and the per-job trigger sets
  in the manifest.
- The SKIPPED-as-pass contract with gate-verified skips (checker change).
- The trigger-envelope extension (`uv.lock`, `.github/workflows/**` in both
  identical lists).
- Job-level `if:` path conditions in the workflow (the only mechanism that
  produces `skipped` check runs; workflow-level `paths:` cannot express
  per-job skips, and per-job workflow files would produce *missing* contexts,
  which fail the checker).

### Scope (out)

- Merging jobs, caching, parallelization, timing budgets.
- The **enforcement-surface change** (promoting jobs into
  `required_contexts` — see Outstanding Questions OQ-D; the review found
  Requirements Tests, Board & Netlist Gates, Provenance & Anti-Vacuity, and
  Known-Failure Pins are NOT in required_contexts today, so their skips would
  be unverified — the plan's enforcement claim covers required contexts
  only).
- Fixing the currently-red gates (the K3 clearance gate).
- Job consolidation.

### Success criteria

- A docs-only PR runs **no** path-conditional job (always-run set only).
- A pure-Rust PR (one crate) runs only that crate's checks + the catch-all
  set.
- The required aggregate goes green from skips only when the checker's own
  changed-file verification confirms the skip; a filter bug is caught by the
  gate, not silently.
- **Per-PR wall time drops** for docs-only and pure-Rust PRs (directly
  caused). Queue-backlog clearing is an expected but unverified outcome
  (arrival-rate-dependent).

### Acceptance examples

- G1. A PR touching only `docs/plans/*` shows the path-conditional suites as
  `skipped` and the required aggregate green.
- G2. A PR touching `packages/temper-geometry/**` runs geometry's suites but
  skips, e.g., the thermal or bundle suites with disjoint trigger sets.
- G3. A PR touching `uv.lock` runs everything (envelope extended, catch-all
  fires).
- G4. A PR whose skip cannot be verified (API failure, unmappable path) →
  the skipped job is treated as failed (fail-closed).
- G5. A workflow job whose condition is NOT a pure path predicate fails the
  manifest cross-check (structural, not behavioral).

### Key decisions (settled)

- **Layered** (always-run + path-conditional), not all-conditional.
- **Gate verifies the skip** — independently, on the base checkout, inline in
  the poll loop (no unverified-green window).
- **Three-category mapping** with docs mapped to nothing (this is what makes
  the headline goal real) and a genuine catch-all whose envelope is extended.
- **Pure path predicates** with machine-readable manifest trigger sets and a
  structural cross-check; patterns restricted to the supported glob subset.
- **Fail-closed skips**: an unverified skip is failed, and "run everything"
  for category-3 paths is the workflow conditions' job.
- **Atomic landing**: the filters and the checker contract land in the same
  merge; the filters half must never merge alone (an old checker fails every
  skip → repo-wide red until the checker lands — fail-closed but blocking).

### Outstanding questions

- OQ-A. **Path→job granularity:** crate-group (recommended) vs per-crate.
- OQ-B. **Verification failure mode:** unmapped → run everything (workflow
  side) / unverifiable skip → fail closed (checker side) — both as stated in
  the settled decisions; confirm.
- OQ-C. **Rollout:** one atomic PR (recommended; the checker change alone is
  inert because no jobs skip yet).
- OQ-D. **Enforcement surface:** the review found the safety suite
  (Requirements Tests), Board & Netlist Gates, Provenance, and Known-Failure
  Pins are not in `required_contexts` — their skips would be unverified.
  Decision: (a) promote Requirements Tests + Provenance & Anti-Vacuity +
  Known-Failure Pins into required_contexts (making their skips verified;
  note: promoting Requirements Tests makes the currently-red K3 clearance
  gate genuinely blocking until #576 lands), or (b) leave the surface as-is
  and scope the verification claim to the 17 required contexts, with a
  structural drift check so non-required job conditions cannot silently rot.
  Recommendation: (b) — keep the enforcement surface unchanged in this plan;
  the promotion is a separate decision with real consequences (it makes the
  K3 breach blocking).
- OQ-E. **Consistency/Provenance re-classification** (path-conditional on
  their enumerable inputs, per F4) vs always-run with true cost stated.
  Recommendation: path-conditional — their inputs are enumerable and the
  always-run cost (~10-16 min of a docs-only budget) is unjustified for
  representations a docs PR cannot change.

## Sources / Research

- `.github/required-checks.json` — `trigger_paths` + `required_contexts`
  (verified: `uv.lock` and most workflow files are absent from the envelope;
  17 required contexts all map to real jobs).
- `scripts/check_required_checks.py` — `success` is the only pass branch
  (skipped fails); `GitHubApi.pull_request_files()` exists and is called;
  `validate_trigger_manifest` enforces workflow/`required-checks.json` list
  identity; `path_matches` is a hand-rolled glob subset.
- `.github/workflows/required-checks.yml` — pull_request_target, base.sha
  checkout, `pull-requests: read`.
- `.github/workflows/python-tests.yml` — ~20 jobs; consistency/provenance
  carry the heavy setup; 8 of 17 required contexts have
  `continue-on-error: true` on their gate step.
- Adversarial document review (2026-08-02) — the F1-F8 findings this revision
  incorporates.
