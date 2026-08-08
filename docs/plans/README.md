# Plans

**Swept 2026-07-25, re-swept 2026-08-07.** Before the first sweep, 86 of 143
plans claimed `status: active` — more than any person can hold, which made
the directory compete with [`../STRATEGY.md`](../STRATEGY.md) rather than
serve it. The first sweep left every plan it couldn't classify as `stale`
rather than guessing (52 of them). The 2026-08-07 pass triaged every
remaining `stale` plan plus every plan the first sweep never reached (added
after 2026-07-25), evidenced against the current repo rather than against
what each plan claims about itself. See
[`PLAN_TRIAGE_2026-08-07.md`](./PLAN_TRIAGE_2026-08-07.md) for the handful of
legacy documents with no frontmatter schema to record a verdict in, the two
systematic blind spots the mechanical heuristic had (deletion/retirement
plans, and paths predating the `src/`-layout migration), and one live
unfixed safety debt (`2026-07-30-001-fix-handoff-actionables-plan.md`)
uncovered while re-checking a plan that reads as finished but is half-landed.

## Current status

<!-- BEGIN GENERATED: plan-status -- edits here are overwritten by scripts/gen_repo_state.py -->

*203 plan documents. Generated from frontmatter.*

| Status | Count | Meaning |
|---|---:|---|
| `active` | 35 | Live work. |
| `completed` | 128 | Deliverables landed. |
| `abandoned` | 23 | Named deliverables largely absent; work never landed. |
| `superseded` | 9 | Replaced by a later plan or by STRATEGY.md. |
| *(no frontmatter)* | 8 | Legacy documents predating the plan format. |

**Active plans (35):**

- [`2026-06-28-004-feat-mathematical-rigor-deferred-items-plan.md`](./2026-06-28-004-feat-mathematical-rigor-deferred-items-plan.md) — 2026-06-28-004-feat-mathematical-rigor-deferred-items-plan
- [`2026-07-25-002-refactor-baseline-burndown-plan.md`](./2026-07-25-002-refactor-baseline-burndown-plan.md) — refactor: Baseline Burn-Down
- [`2026-07-28-001-feat-provable-safety-place-and-route-plan.md`](./2026-07-28-001-feat-provable-safety-place-and-route-plan.md) — Provable-Safety Place and Route - Plan
- [`2026-07-29-001-fix-pour-derivation-rule-plan.md`](./2026-07-29-001-fix-pour-derivation-rule-plan.md) — Pour Derivation Rule - Plan
- [`2026-07-30-001-fix-handoff-actionables-plan.md`](./2026-07-30-001-fix-handoff-actionables-plan.md) — Handoff Actionables Integration - Plan
- [`2026-08-01-001-feat-wave4-full-migration-program-plan.md`](./2026-08-01-001-feat-wave4-full-migration-program-plan.md) — Wave 4 Python → Rust Full-Migration Program — Plan
- [`2026-08-02-001-feat-validation-portfolio-plan.md`](./2026-08-02-001-feat-validation-portfolio-plan.md) — Validation Portfolio - Plan
- [`2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`](./2026-08-02-001-feat-wave4-phase3-formats-io-plan.md) — Wave 4 Phase 3: Formats/IO Migration — Plan
- [`2026-08-02-003-feat-spice-estimator-oracle-plan.md`](./2026-08-02-003-feat-spice-estimator-oracle-plan.md) — SPICE Estimator Oracle - Plan
- [`2026-08-02-005-feat-bmc-all-constraint-encodings-plan.md`](./2026-08-02-005-feat-bmc-all-constraint-encodings-plan.md) — BMC-Exhaustive All Constraint Encodings - Plan
- [`2026-08-02-008-feat-full-board-drc-oracle-plan.md`](./2026-08-02-008-feat-full-board-drc-oracle-plan.md) — Full-board DRC Oracle Differential - Plan
- [`2026-08-02-010-feat-induction-proof-coverage-plan.md`](./2026-08-02-010-feat-induction-proof-coverage-plan.md) — Induction-proof Coverage for Compute Crates - Plan
- [`2026-08-02-011-feat-transform-algebra-exhaustiveness-plan.md`](./2026-08-02-011-feat-transform-algebra-exhaustiveness-plan.md) — Transform-algebra Exhaustiveness - Plan
- [`2026-08-02-012-feat-geometry-kernel-mutation-plan.md`](./2026-08-02-012-feat-geometry-kernel-mutation-plan.md) — Geometry-Kernel & Writer Mutation - Plan
- [`2026-08-02-014-feat-quality-vs-human-oracle-plan.md`](./2026-08-02-014-feat-quality-vs-human-oracle-plan.md) — Quality vs Human Oracle - Plan
- [`2026-08-02-016-feat-post-solve-audit-all-constraints-plan.md`](./2026-08-02-016-feat-post-solve-audit-all-constraints-plan.md) — Post-Solve Audit for All Constraints - Plan
- [`2026-08-02-017-feat-optimality-gap-certificate-plan.md`](./2026-08-02-017-feat-optimality-gap-certificate-plan.md) — Solve-Gap Oracle & Certificate - Plan
- [`2026-08-02-018-feat-solution-mutation-canaries-plan.md`](./2026-08-02-018-feat-solution-mutation-canaries-plan.md) — Solution Mutation Canaries - Plan
- [`2026-08-02-020-feat-fab-rule-oracle-plan.md`](./2026-08-02-020-feat-fab-rule-oracle-plan.md) — Fab-Rule Oracle - Plan
- [`2026-08-02-022-feat-formal-board-property-verification-plan.md`](./2026-08-02-022-feat-formal-board-property-verification-plan.md) — Formal Board-Property Verification - Plan
- [`2026-08-02-023-feat-drc-ceiling-monotone-contract-plan.md`](./2026-08-02-023-feat-drc-ceiling-monotone-contract-plan.md) — DRC Ceiling as Monotone Contract - Plan
- [`2026-08-02-026-feat-hil-oracle-plan.md`](./2026-08-02-026-feat-hil-oracle-plan.md) — Hardware-in-the-loop oracle - Plan
- [`2026-08-02-028-feat-state-machine-model-check-plan.md`](./2026-08-02-028-feat-state-machine-model-check-plan.md) — State-Machine Model Check & Invariant Proofs - Plan
- [`2026-08-02-031-feat-firmware-fault-injection-plan.md`](./2026-08-02-031-feat-firmware-fault-injection-plan.md) — Firmware fault injection - Plan
- [`2026-08-02-032-feat-incident-corpus-oracle-plan.md`](./2026-08-02-032-feat-incident-corpus-oracle-plan.md) — Incident Corpus & Gate Canary Contract - Plan
- [`2026-08-02-034-feat-trigger-path-closed-form-plan.md`](./2026-08-02-034-feat-trigger-path-closed-form-plan.md) — Closed-Form Trigger-Path Verification - Plan
- [`2026-08-02-035-feat-gate-mutation-testing-plan.md`](./2026-08-02-035-feat-gate-mutation-testing-plan.md) — Gate-Mutation Testing - Plan
- [`2026-08-02-036-feat-trigger-path-mutation-plan.md`](./2026-08-02-036-feat-trigger-path-mutation-plan.md) — Trigger-Path Mutation - Plan
- [`2026-08-02-037-feat-thermal-solver-oracle-differential-plan.md`](./2026-08-02-037-feat-thermal-solver-oracle-differential-plan.md) — Thermal Solver Oracle Differential - Plan
- [`2026-08-03-002-feat-wasm-verification-tier-plan.md`](./2026-08-03-002-feat-wasm-verification-tier-plan.md) — WASM Verification Tier - Plan
- [`2026-08-04-002-docs-temper-goal-set-plan.md`](./2026-08-04-002-docs-temper-goal-set-plan.md) — Temper Goal Set - Plan
- [`2026-08-04-003-feat-drc-count-ratchet-deletion-incentive-plan.md`](./2026-08-04-003-feat-drc-count-ratchet-deletion-incentive-plan.md) — The DRC Count Ratchet Rewards Deleting Components - Decision Plan
- [`2026-08-05-001-feat-wasm-tier-phase0-plan.md`](./2026-08-05-001-feat-wasm-tier-phase0-plan.md) — WASM Verification Tier — Phase 0 Implementation Plan
- [`2026-08-07-001-feat-router-encoding-pruning-plan.md`](./2026-08-07-001-feat-router-encoding-pruning-plan.md) — Router SAT Encoding Geographic Pruning — Plan
- [`2026-08-07-001-feat-wasm-tier-phase1-plan.md`](./2026-08-07-001-feat-wasm-tier-phase1-plan.md) — WASM Verification Tier — Phase 1 Implementation Plan

<!-- END GENERATED: plan-status -->

The forward plan of record is the build order in
[`../STRATEGY.md`](../STRATEGY.md). New plans are written against it, not
accumulated alongside it (`METHODOLOGY.md` §8: documents supersede, they do not
accumulate).

## Method

Files were **not moved**. 105 code and config references point into this
directory — including `Origin: U5 of docs/plans/...` provenance breadcrumbs in
`temper-drc-rs` and `scripts/` — and moving files would break traceability the
project deliberately maintains. Only frontmatter changed.

Each swept plan carries:

```yaml
swept: 2026-07-25
swept_basis: "<evidence for the classification>"
```

Classification, in precedence order:

1. **pinned** — referenced by a live `@req` annotation with a registry entry
   (`scripts/check_traceability.py` requires those plans be `active`) → `active`
2. **explicitly superseded** by STRATEGY v2.0 → `superseded`
3. already declared `completed`/`superseded` → unchanged
4. referenced in git history **and** ≥60% of named file paths exist, or ≥80%
   of paths exist regardless → `completed`
5. ≥3 named paths and ≤25% of them exist → `abandoned`
6. otherwise → `stale`

## Limits of this sweep

**The 2026-07-25 mechanical sweep's `stale` plans were honestly
unclassified, not quietly closed.** Automated intent classification could
not distinguish "done but never referenced" from "abandoned" for these.
Path-existence is a weak proxy: a plan whose work landed under different
filenames scores as abandoned, and a plan that merely *named* existing files
scores as completed. Two concrete failure modes surfaced during the
2026-08-07 re-sweep: (1) a plan whose entire point is deleting code (JAX
retirement, the Cython A\* twin cleanup) scores `abandoned` when its named
paths correctly stop existing — the heuristic reads success as failure; (2) a
repo-wide migration to a `src/` package layout broke path matching for
plans written before it, scoring genuinely-landed work as `abandoned`.

`status: stale` means *a human needs to look*. As of 2026-08-07, none remain
— every plan that carried `stale` (or no status at all) has a re-evidenced
verdict. `status: stale` is not a verdict and is not being retired as a
value; a future sweep may reintroduce it for plans that are genuinely
unresolvable.

Verified: the 2026-07-25 sweep introduced **zero** new
`check_traceability.py` violations (10 before, 10 after, all pre-existing).

## Known pre-existing issues

Found while sweeping, not introduced by it:

- **`scripts/check_traceability.py` runs nowhere.** It exits 1 on the current
  tree. `docs/plans/**` and `docs/traceability-registry.yaml` appear in
  `python-tests.yml` only as *path filters* deciding whether the workflow runs,
  never in a step that invokes the gate. A detector wired to nothing
  (`METHODOLOGY.md` §4, classes 3 and 6).
- **`APC1` is `completed` but 6 annotations require `active`** — the plan closed
  without its annotations being retired.
- **`@req(U9, R1)` references a plan-id absent from the registry.**
- **`N10` requirements `U1`–`U4` are annotated but not defined** in its plan.
- **The gate scans `.worktrees/`**, inflating violations from 10 to 194.

## Recovering a plan

`git log --follow <file>` retains the pre-sweep status, or:

```bash
git show <pre-sweep-sha>:docs/plans/<file>
```
