# Plans

**Swept 2026-07-25.** Before the sweep, 86 of 143 plans claimed `status: active`
— more than any person can hold, which made the directory compete with
[`../STRATEGY.md`](../STRATEGY.md) rather than serve it.

## Current status

<!-- BEGIN GENERATED: plan-status -- edits here are overwritten by scripts/gen_repo_state.py -->

*153 plan documents. Generated from frontmatter.*

| Status | Count | Meaning |
|---|---:|---|
| `active` | 7 | Live work. |
| `completed` | 61 | Deliverables landed. |
| `stale` | 52 | Insufficient evidence -- needs human triage. |
| `abandoned` | 17 | Named deliverables largely absent; work never landed. |
| `superseded` | 5 | Replaced by a later plan or by STRATEGY.md. |
| `research-only, no elec/src or pcb/ changes made -- this is a` | 1 | -- |
| *(no frontmatter)* | 10 | Legacy documents predating the plan format. |

**Active plans (7):**

- [`2026-06-28-004-feat-mathematical-rigor-deferred-items-plan.md`](./2026-06-28-004-feat-mathematical-rigor-deferred-items-plan.md) — 2026-06-28-004-feat-mathematical-rigor-deferred-items-plan
- [`2026-07-25-001-fix-test-skip-accounting-plan.md`](./2026-07-25-001-fix-test-skip-accounting-plan.md) — fix: Test Skip Accounting
- [`2026-07-25-002-refactor-baseline-burndown-plan.md`](./2026-07-25-002-refactor-baseline-burndown-plan.md) — refactor: Baseline Burn-Down
- [`2026-07-25-003-refactor-package-consolidation-plan.md`](./2026-07-25-003-refactor-package-consolidation-plan.md) — refactor: Package Consolidation
- [`2026-07-28-001-feat-provable-safety-place-and-route-plan.md`](./2026-07-28-001-feat-provable-safety-place-and-route-plan.md) — Provable-Safety Place and Route - Plan
- [`2026-07-28-002-fix-pad-geometry-model-plan.md`](./2026-07-28-002-fix-pad-geometry-model-plan.md) — Correct the Pad Geometry Model - Plan
- [`2026-07-30-002-resolve-current-board-clearance-debt-plan.md`](./2026-07-30-002-resolve-current-board-clearance-debt-plan.md) — Resolve Current Board Clearance Debt - Plan

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

**The 52 `stale` plans are honestly unclassified, not quietly closed.**
Automated intent classification could not distinguish "done but never
referenced" from "abandoned" for these. Path-existence is a weak proxy: a plan
whose work landed under different filenames scores as abandoned, and a plan
that merely *named* existing files scores as completed.

`status: stale` means *a human needs to look*. It is not a verdict.

Verified: the sweep introduced **zero** new `check_traceability.py` violations
(10 before, 10 after, all pre-existing).

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
