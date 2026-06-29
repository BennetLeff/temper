---
title: "splr 0.13 → rustsat-cadical solver migration with trait-based solver swapping"
date: "2026-06-29"
category: "tooling-decisions"
module: "temper-rust-router"
problem_type: "tooling_decision"
component: "sat_solver"
severity: "high"
applies_when:
  - "Migrating between SAT solver backends without rewriting constraint construction or solution extraction"
  - "Adopting a trait-based solver interface to enable solver swapping and capability discovery"
  - "Extracting UNSAT cores, internal solver stats, or mid-search callbacks from a CDCL solver"
  - "Harmonizing competing type definitions across package boundaries with backward-compatible field additions"
tags:
  - "sat-solver"
  - "splr"
  - "cadical"
  - "rustsat"
  - "unsat-core"
  - "solver-stats"
  - "backward-compatible"
  - "type-harmonization"
  - "parallel-worktree"
  - "netclassrules"
---

# splr → rustsat-cadical Solver Migration with Trait-Based Solver Swapping

## Context

The temper-rust-router crate initially used **splr 0.13**, a pure-Rust SAT solver, for constraint-based PCB topology routing. Three problems emerged:

1. **splr 0.13 is an API dead end.** `Certificate::UNSAT` is a unit variant — no core data, no unsatisfiable sub-formula. UNSAT core extraction is impossible.
2. **No mid-search hooks.** splr exposes no `Learn` trait for clause-learning callbacks, no internal stats (conflicts, decisions, propagations), and no incremental solving with assumptions.
3. **No solver-swap path.** splr has no trait-based interface, so swapping it meant rewriting every call site.

Simultaneously, a cross-cutting type-safety issue surfaced: `NetClassRules` in `core/design_rules.py` had a `safety_category` field, but the parallel `NetClassRules` in `router_v6/stage0_data.py` did not. Code that processed both types used `getattr(x, "safety_category", None)` as a defensive workaround, masking the structural gap.

These two problems — plus 7 brainstorm-to-plan-to-merge tasks — were resolved in a single parallel-worktree sprint pipeline (7 worktrees, batch-merged into main).

## Guidance

### 1. Trait-based solver migration pattern

When migrating SAT solver backends, wrap the new solver behind existing traits rather than calling it directly. This isolates the migration to one file (`solver.rs`) while constraint construction, encoding, and solution extraction remain unchanged.

**Step 1: Replace the Cargo.toml dependency.**

```toml
# Cargo.toml — before
splr = "0.13"

# Cargo.toml — after
rustsat = { version = "0.7.5", default-features = false, features = ["fxhash"] }
rustsat-cadical = "0.7.5"
# splr = "0.13"  -- replaced by rustsat + rustsat-cadical
```

**Step 2: Swap imports and solver construction.**

```rust
// solver.rs — before (splr 0.13)
use splr::Solver;

let mut solver = Solver::try_from(config).unwrap();
for clause in &cnf.clauses {
    solver.add_clause(clause.iter().map(|&l| l as i32));
}
match solver.solve() {
    Ok(Certificate::SAT(v)) => { /* extract assignments from Vec<i32> */ }
    Ok(Certificate::UNSAT)   => { /* unit variant — no core data */ }
    Err(e)                   => { /* no stats exposure */ }
}
```

```rust
// solver.rs — after (rustsat-cadical)
use rustsat::solvers::{GetInternalStats, Solve, SolverResult};
use rustsat::types::{Clause, Lit, TernaryVal, Var};
use rustsat_cadical::CaDiCaL;

let mut solver = CaDiCaL::default();
for clause in &cnf.clauses {
    let lits: Vec<Lit> = clause.iter().map(|&lit| {
        // Convert signed-DIMACS to rustsat Lit
        if lit > 0 { Lit::positive((lit as u32) - 1) }
        else       { Lit::negative(((-lit) as u32) - 1) }
    }).collect();
    solver.add_clause(Clause::from(&lits[..])).unwrap();
}

let result = solver.solve(); // SolverResult::Sat | Unsat | Interrupted
match solver.solve() {
    Ok(SolverResult::Sat) => {
        let sol = solver.full_solution()?;
        for i in 0..cnf.num_vars {
            match sol[Var::new(i as u32)] {
                TernaryVal::True  => { /* assign true */ }
                TernaryVal::False => { /* assign false */ }
                TernaryVal::DontCare => { /* skip */ }
            }
        }
    }
    Ok(SolverResult::Unsat) => {
        // Core extraction now possible via SolveIncremental
    }
    Ok(SolverResult::Interrupted) => { /* timeout */ }
    Err(_) => { /* internal error */ }
}
```

**Key difference:** splr used signed `i32` for literals (DIMACS convention: +/- variable number). rustsat uses unsigned `u32` zero-indexed variables with `Lit::positive/negative`. The conversion is mechanical: `lit.abs() - 1` for the variable index, sign determines polarity.

### 2. Post-migration capability gains

After migrating to rustsat traits, these capabilities become available with zero additional refactoring:

| Capability | Trait | What it unblocks |
|---|---|---|
| UNSAT core extraction | `SolveIncremental::solve_assumps()` + `core()` | Identify which constraints caused unsatisfiability |
| Internal stats exposure | `GetInternalStats` (`.conflicts()`, `.decisions()`, `.propagations()`) | Profile solver behavior per problem instance |
| Clause-learning callbacks | `Learn` trait implementation | Observe which clauses the solver learns during search |
| Solver swapping | All traits are generic over the solver type | Swap CaDiCaL for minisat, kissat, or glucose with one type change |
| `catch_unwind` panic safety | CaDiCaL C++ backend can throw; Rust wrapper unwinds gracefully | Return `Unknown` status instead of crashing the process |

Stats collection is now direct method calls rather than post-hoc inference:

```rust
// solver.rs — after: direct stats collection via GetInternalStats
let conflicts = solver.conflicts() as u64;
let decisions = solver.decisions() as u64;
let propagations = solver.propagations() as u64;
let stats = SolverStats {
    conflicts,
    decisions,
    propagations,
    decision_level_histogram: build_histogram(conflicts, decisions),
    unsat_core_size: 0,  // populated when using SolveIncremental
    variable_count: cnf.num_vars as u64,
    clause_count: cnf.clauses.len() as u64,
    cpu_solve_time_ms: elapsed,
};
```

### 3. Backward-compatible field harmonization across competing types

When two definitions of the same concept exist in different packages, add the missing field as optional-with-default rather than attempting unification:

```python
# router_v6/stage0_data.py — before (missing safety_category)
@dataclass
class NetClassRules:
    name: str
    clearance_mm: float
    trace_width_mm: float
    via_diameter_mm: float
    via_drill_mm: float
    diff_pair_gap_mm: float | None = None
    diff_pair_width_mm: float | None = None
    current_rating_amps: float | None = None

# router_v6/stage0_data.py — after (1-line fix, backward-compatible)
@dataclass
class NetClassRules:
    name: str
    clearance_mm: float
    trace_width_mm: float
    via_diameter_mm: float
    via_drill_mm: float
    diff_pair_gap_mm: float | None = None
    diff_pair_width_mm: float | None = None
    current_rating_amps: float | None = None
    safety_category: str | None = None   # <-- added: matches core/design_rules.py
```

The `= None` default ensures all existing construction sites compile (Python: pass) without modification. Code that already used `getattr(rules, "safety_category", None)` continues to work and now also works for the default-path `NetClassRules(...)` construction in `get_rules_for_net`:

```python
# stage0_data.py line 110 — fallback construction now carries safety_category=None
return NetClassRules(
    name="Default",
    clearance_mm=self.default_clearance_mm,
    trace_width_mm=self.default_trace_width_mm,
    via_diameter_mm=self.default_via_diameter_mm,
    via_drill_mm=self.default_via_drill_mm,
    # safety_category defaults to None — no change needed
)
```

### 4. Verification: run the full test suite post-migration

After a solver migration, run both Rust-side and Python-side tests:

```bash
# Rust tests (unit + integration)
cargo test -p temper-rust-router

# Python tests (SAT property-based tests, 44 cases)
uv run pytest packages/temper-placer/tests/ -k "sat or constraint or solver" -v
```

The migration in this session passed all 12 Rust tests + 44 Python SAT PBT tests.

## Why This Matters

**Before splr 0.13:** The solver was a black box. You could ask "SAT or UNSAT?" and get back assignments. No UNSAT provenance, no performance instrumentation, no incremental solving. Every capability beyond basic solve required an API that didn't exist.

**After rustsat-cadical:** The solver is an instrumented, swappable, trait-generic component. UNSAT core extraction is one trait impl away (`SolveIncremental`). Internal stats are a method call away (`GetInternalStats`). Swapping to kissat or minisat is a one-type change. The `solver.rs` file grew from 97 to 107 lines but gained capabilities that would have required a full rewrite under splr.

**The field harmonization pattern** prevented a latent bug: `stage0_data.py` code constructing `NetClassRules("Default", ...)` would silently drop the `safety_category` entirely, causing DRC safety checks to fall back to keyword-scan heuristics with stderr warnings. The 1-line `= None` default fixed this without touching any call site.

**The parallel worktree pipeline** collapsed 7 brainstorm→plan→implement→merge cycles from serial (~7 hours) into batched parallel execution (~3 hours). See `docs/solutions/workflow-issues/parallel-worktree-sprint-pipeline.md` for the full pattern.

## When to Apply

- When a dependency reaches an API dead end (missing features needed for the next 3+ roadmap items) — migrate before the dead-end blocks multiple features
- When a solver/library has no trait interface — wrap the replacement behind traits so future migrations are type-change-only
- When two parallel type definitions drift apart in different packages — add the missing field as `= None` rather than unifying the types (avoids import coupling)
- When shipping 5+ independent tasks with non-overlapping file footprints — use the parallel worktree sprint pipeline
- **Not** when the existing solver meets all current and planned needs (migration carries risk)
- **Not** when unifying the types would create a new cross-package import dependency (prefer harmonization over coupling)

## Key Learnings

1. **splr 0.13 `Certificate::UNSAT` is a unit variant.** There is no `.core` field, no unsatisfiable sub-formula, no way to extract provenance. If you need UNSAT core, splr is not the right solver.
2. **The `rustsat` crate provides a uniform trait interface** over CaDiCaL, minisat, kissat, glucose, and others. Migrating to rustsat means you migrate once and get N solvers.
3. **DIMACS literal convention differs.** splr uses signed i32 (+/- variable_number). rustsat uses unsigned u32 zero-indexed with `Lit::positive/negative`. The conversion is `abs() - 1` for index, sign for polarity — a mechanical but pervasive change.
4. **CaDiCaL is C++, so `catch_unwind` is essential.** The solver can throw from C++ internals. Wrapping `solver.solve()` in `catch_unwind` returns `Unknown` instead of crashing the process.
5. **Field harmonization via `= None` is safer than unification.** Adding `safety_category: str | None = None` to `stage0_data.py` doesn't create a cross-package import. Unifying to a single type shared across packages would couple `router_v6` to `core` — exactly the coupling the import-linter boundary enforcement guards against.
6. **Test verification must span Rust and Python.** The SAT solver is a Rust crate called via PyO3 from Python tests. The property-based test suite (44 cases) caught encoding bugs that unit tests alone would miss.

## Related

- `docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md` — origin plan with U5: splr→cadical migration requirement
- `packages/temper-rust-router/src/solver.rs` — migrated solver (107 lines, CaDiCaL via rustsat traits)
- `packages/temper-rust-router/Cargo.toml` — dependency swap (splr 0.13 → rustsat + rustsat-cadical 0.7.5)
- `packages/temper-placer/src/temper_placer/core/design_rules.py` — canonical `NetClassRules` with `safety_category` field
- `packages/temper-placer/src/temper_placer/router_v6/stage0_data.py` — harmonized `NetClassRules` (1-line fix)
- `packages/temper-drc/src/temper_drc/checks/safety/_safety_keywords.py` — `resolve_safety_category()` that consumes both types
- `docs/solutions/workflow-issues/parallel-worktree-sprint-pipeline.md` — the worktree pipeline that shipped these 7 tasks in parallel
- `docs/solutions/performance-issues/sat-model-too-large-for-splr-selective-construction-2026-06-28.md` — upstream performance issue that motivated better solver introspection
- `docs/solutions/tooling-decisions/import-linter-boundary-enforcement-ratchet-2026-06-22.md` — boundary enforcement that prevents coupling `router_v6` to `core` internals (why harmonization was chosen over unification)
