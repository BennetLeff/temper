---
title: "SAT Solver API Vetting and Parallel Worktree Multi-Feature Sprint Architecture"
date: 2026-06-29
last_updated: 2026-07-01
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: development_workflow
severity: high
applies_when:
  - "Designing a constraint-solver architecture with multiple interdependent features"
  - "Selecting a solver or library before committing to a feature design"
  - "Implementing multiple cross-cutting features that share a common dependency"
  - "Catching API capability gaps early in a multi-feature sprint"
  - "Running parallel worktrees for independent but coordinated feature branches"
symptoms:
  - "splr SAT solver lacked UNSAT core extraction, mid-search hooks, and solver statistics"
  - "NetClassRules safety_category was independently duplicated across brainstorm documents"
  - "81 issues surfaced across 7 brainstorm docs during structured doc review"
root_cause: wrong_api
resolution_type: dependency_update
tags:
  - sat-solver
  - solver-migration
  - cadical
  - parallel-worktrees
  - multi-feature-sprint
  - constraint-encoding
  - pcb-placer
  - doc-review-pipeline
---

# SAT Solver API Vetting and Parallel Worktree Multi-Feature Sprint

## Context

The temper-placer PCB autorouter's routing SAT stage had outgrown its solver backend. Seven
features were ideated in a single session, all requiring capabilities the current solver (splr 0.13)
didn't expose: UNSAT core extraction, solver statistics, incremental clause addition, and
mid-search hooks. The solver was the linchpin — without upgrading it, all seven features were
blocked.

Simultaneously, a cross-cutting type-safety gap emerged: `NetClassRules` in two packages had
diverged, with `safety_category` present in one but absent in the other. Multiple brainstorm docs
referenced the missing field, creating conflicting assumptions.

The session produced a reproducible pattern: single-solver migration → 7 brainstorm docs
→ structured doc review (81 fixes) → 7 implementation plans → 7 parallel worktrees →
batch implementation → sequential merge. Time from ideation to merged PR: under 3 hours
(agent-speed execution, not human-time estimation).

## Guidance

### 1. Vet the solver API before committing to features

Before writing a single requirements doc for a constraint-solver feature, enumerate the
capabilities the solver must provide and check whether the current backend supports them.
In this session, three gaps blocked all seven features:

| Required capability | Needed by | splr 0.13 support |
|---|---|---|
| UNSAT core extraction | Lowering compiler, UNSAT provenance, Bidirectional PCL IR, Routability gradient | `Certificate::UNSAT` is a unit variant — no data |
| Between-solve clause addition | Net bundling lazy grounding, Combinator library | Not supported (incremental feature untested) |
| Internal solver statistics | Routability gradient | No public API (`State.stats` is private) |

The fix: migrate to rustsat-cadical, which exposes `SolveIncremental::solve_assumps()` +
`core()` for UNSAT cores, `GetInternalStats` for conflicts/decisions/propagations, and a
trait-generic `Solve` interface that makes the solver swappable post-migration. The solver module grew from ~97 lines (original) to a clean trait-generic implementation.

**Pattern**: check solver capabilities against your feature road map BEFORE committing to
implementations. A one-hour solver migration unblocked seven features. Discovering the gap
mid-implementation would have blocked each feature independently.

### 2. Use the ideation → brainstorm → doc-review → plan → worktree → implement → merge pipeline

This session established a reproducible end-to-end pipeline for multi-feature sprints:

1. **ce-ideate** → 47 raw ideas across 6 frames, deduped to 7 survivors
2. **ce-brainstorm** × 7 parallel → 7 requirements docs, each codebase-verified
3. **ce-doc-review** × 7 parallel → 81 issues found and applied across all 7 docs
4. Cross-cutting blocker resolution: splr migration + NetClassRules harmonization
5. **ce-plan** × 7 parallel → 7 implementation plans with U-IDs, test scenarios, verification criteria
6. `git worktree add` × 7 → 7 isolated branches in `.worktrees/`
7. **ce-work** × 7 parallel agents → implemented in isolation (no file conflicts between branches)
8. Sequential merge → 1 conflict per branch (resolved via `--theirs` for add/add, manual for content)
9. Open PR → merge

**Key decision: parallel at every stage except merge.** Ideation, brainstorming, doc review,
planning, and implementation all ran concurrently. Only the merge was sequential (each branch
depended on the cumulative main state).

### 3. Backward-compatible field harmonization over type unification

When two `NetClassRules` definitions diverge across packages (one has `safety_category`,
one doesn't), add the missing field as optional-with-default rather than trying to unify the types:

```python
# router_v6/stage0_data.py — 1-line fix, zero call-site changes
safety_category: str | None = None
```

This avoids creating a cross-package import dependency between `router_v6` and `core` —
exactly the coupling the import-linter boundary enforcement guards against. Unifying to a
single shared type would couple `router_v6` to `core` internals.

> **Note:** the `safety_category` field was added to `core/design_rules.py` (Pydantic)
> but not yet added to the dataclass in `router_v6/stage0_data.py`. Code defensively
> uses `getattr(rules, "safety_category", None)`.

### 4. The `--theirs` merge strategy for parallel worktree conflicts

When 7 branches create or modify overlapping files, sequential merging produces cascading
conflicts. The session used this strategy:

- **add/add conflicts** (both branches created the same file): `git checkout --theirs` — the
  merged branch's version is authoritative for its own feature files
- **content conflicts** (both branches modified the same region): resolve manually keeping
  both sides' additions
- **Rust enum variants**: add missing variants (`ChannelSeparation`, `BundleClass`) and
  match arms (`encoding.rs`, `audit.rs`, `types_py_bridge.rs`, `esl.rs`) after merge

Post-merge verification: `cargo test` (25 Rust tests) + `pytest test_sat_solve_pbt.py` (44 Python
SAT PBT tests) must pass before pushing.

## Why This Matters

**Before splr:** The solver was a black box. SAT or UNSAT — that's all you got. Seven features
were conceptually blocked.

**After rustsat-cadical:** UNSAT core extraction (`core()` returns failed assumption literals),
solver statistics (`conflicts()`, `decisions()`, `propagations()`), and incremental clause addition
all work. The solver is swappable via traits (swap `CaDiCaL` for `Minisat` by changing one type).

**The pipeline pattern** collapses a multi-feature sprint from serial execution (~hours of
context-switching) into batched parallel execution. Worktree isolation eliminates file conflicts
during implementation — each agent works in its own checkout. The 7 branches had zero
overlapping file modifications during implementation (conflicts only surfaced at merge).

**The field harmonization** prevents a latent bug: constructing `NetClassRules("Default", ...)`
in the fallback path silently drops `safety_category`, causing DRC safety checks to fall back
to keyword-scan heuristics. The 1-line fix makes every construction site carry the field.

## When to Apply

- When a dependency reaches an API dead end that blocks multiple planned features — migrate before the dead end blocks each feature independently
- When shipping 5+ independent features with non-overlapping file footprints — use the parallel worktree pipeline
- When two parallel type definitions drift apart — add the missing field as `= None` rather than unifying types across package boundaries
- When a multi-feature sprint benefits from agent-speed parallel execution — batched ideation + docs + plans + worktrees + implementation

## Examples

**Solver migration:** See `docs/solutions/tooling-decisions/splr-to-rustsat-cadical-solver-migration-2026-06-29.md` for the full before/after code diff.

**NetClassRules harmonization (1 line):**

```python
# Before: stage0_data.py NetClassRules — no safety_category
@dataclass
class NetClassRules:
    name: str
    clearance_mm: float
    # ... 5 more fields
    current_rating_amps: float | None = None

# After: 1 line added, backward-compatible
@dataclass
class NetClassRules:
    name: str
    clearance_mm: float
    # ... 5 more fields
    current_rating_amps: float | None = None
    safety_category: str | None = None  # matches core/design_rules.py
```

**Post-merge Rust fix pattern (ChannelSeparation):**

After merging branches that add new `InternalConstraint` variants, verify every match block
is exhaustive. Three files need arms: `encoding.rs`, `audit.rs` (both loops), `types_py_bridge.rs`
(Python parsing). The fourth file `esl.rs` also needs coverage if ESL evaluation is enabled.
Run `cargo test` — Rust's exhaustiveness checking catches every missed arm at compile time.

## Forward Reference

CaDiCaL's UNSAT core extraction capability enables the UNSAT provenance pattern
in the [PCL constraint system](docs/solutions/architecture-patterns/pcl-constraint-system-triple-extension-2026-07-01.md),
which builds a constraint type system with bidirectional placement↔routing constraint flow.

## Related

- `docs/solutions/tooling-decisions/splr-to-rustsat-cadical-solver-migration-2026-06-29.md` — solver migration before/after code diff
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — the splr-era encoding bug that the BMC feature now catches at CI time
- `docs/solutions/performance-issues/sat-model-too-large-for-splr-selective-construction-2026-06-28.md` — selective construction (superseded by net bundling)
- `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md` — pipeline safety pattern
- `docs/ideation/2026-06-28-sat-constraint-type-system-ideation.md` — the ideation artifact (47 ideas → 7 survivors)
- `docs/plans/2026-06-28-001-feat-constraint-lowering-compiler-plan.md` through `docs/plans/2026-06-28-007-feat-routability-gradient-signal-plan.md` — all 7 implementation plans
- PR #93: the merged PR containing all 7 features
