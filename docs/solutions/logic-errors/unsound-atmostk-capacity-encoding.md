---
title: "Router V6 SAT solver produced unsound AtMostK capacity assignments"
date: "2026-06-28"
last_updated: "2026-08-12"
category: logic-errors/
module: temper-rust-router
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - "SAT solver allowed 6 nets to use a channel rated for 3 — capacity constraint was silently violated"
  - "Greedy round-robin solver had no CDCL, no backjumping, no clause learning"
  - "No post-solve validation of solver output against input constraints"
root_cause: logic_error
resolution_type: code_fix
tags:
  - sat-solver
  - atmostk-encoding
  - sequential-counter
  - cdcl
  - cadical
  - pyo3
  - pcb-router
  - constraint-audit
---

# Unsound AtMostK Capacity Encoding in Router V6 SAT Solver

## Problem

The Router V6 topology stage SAT solver used a broken AtMostK encoding that allowed more nets than a channel's rated capacity to be assigned silently. A channel rated for 3 nets could accept 6 without the solver detecting the violation. These violations surfaced downstream only as DRC failures or physically unroutable assignments in Stage 4 — there was no solver-level correctness enforcement.

## Symptoms

- For K=3 channels with N=10 candidate nets, up to 6 nets were assigned — the solver's single-clause encoding was necessary but not sufficient
- The greedy round-robin solver had no backjumping, no watched literals, no clause learning — acknowledged in the source as a placeholder
- No diagnostic tool existed to identify why a problem was unsatisfiable (no unsat-core extraction)

## What Didn't Work

**The original encoding (`sat_model.py:198-225`).** It added a single clause "at least one of the surplus N-K variables must be false." For K=3, N=10, this requires 1 of 7 surplus nets to be false — leaving 6 allowed. This is unsound for K > 1.

**Python fallback as graceful degradation.** When the Rust solver was first integrated behind `TEMPER_SAT_BACKEND`, the Python greedy solver was kept as fallback. But the Python solver cannot solve the sequential counter encoding — it returns UNSAT on SAT models because the greedy heuristic cannot propagate implications through auxiliary variables. Keeping it as fallback would silently produce wrong answers under the guise of "graceful degradation."

**Golden fixtures as a validation baseline.** The original plan generated Python golden fixtures for Stage 3 and validated the Rust solver against them. But golden fixtures validate against a buggy reference — if the Python solver has bugs in constraint model building or diff-pair encoding, the fixtures encode those bugs and the Rust solver faithfully reproduces them. This was a consistency check, not a correctness proof.

## Solution

Three-layer fix: correct the encoding mathematically, replace the solver with CDCL, and audit every output.

### Layer 1 — Correct AtMostK encoding

Replace the broken single-clause encoding with a Sinz (2005) sequential counter that encodes `sum(vars) ≤ K` in O(n·k) auxiliary variables and O(n·k) clauses. Implemented in Python (`sat_model.py:_encode_at_most_k`) and ported to Rust (`encoding.rs:encode_at_most_k`).

```rust
// Rust sequential counter — O(n·k) CNF encoding of AtMostK
fn encode_at_most_k(
    clauses: &mut Vec<Vec<i32>>,
    var_map: &mut Vec<SatVariable>,
    vars: &[usize],
    k: usize,
) {
    let n = vars.len();
    if k >= n { return; }
    // r[i][j]: at least j+1 of vars[0..i] are true
    let r_start = var_map.len();
    for i in 0..(n - 1) {
        for j in 0..k {
            var_map.push(SatVariable::new(format!("sc_r{i}_{j}"), ""));
        }
    }
    // Position 0 propagation + exclusion chain
    // (details elided — full implementation in encoding.rs)
}
```

### Layer 2 — CDCL solver (rustsat-cadical via PyO3)

Created `packages/temper-rust-router/` as a maturin-based PyO3 crate. rustsat-cadical 0.7.5 provides CDCL (migrated from splr 0.13, 2026-06-29) with clause learning, watched literals, and restarts. The sequential counter is encoded as CNF clauses (CaDiCaL lacks a native `add_atmostk` API).

```rust
// CaDiCaL via rustsat traits — trait-generic, solver-swappable
let result = std::panic::catch_unwind(
    std::panic::AssertUnwindSafe(|| solver.solve())
);
```

### Layer 3 — Constraint audit

An inline audit module validates every solver output against the input constraint model. Capacity, diff-pair, and layer constraints are checked after every solve. Violations raise `RuntimeError` — no silent wrong answers. As of 2026-08-12 this runs on **both** of `router_v6`'s production solve paths — see the 2026-08-12 erratum under Prevention below for why that wasn't always true, and for the real-board measurement of what it currently reports.

```python
# _pipeline_route.py:437-452 — audit runs after every Rust solve, monolithic path
from temper_rust_router import audit_result
audit_violations = list(audit_result(py_vars, py_cons, assignments, net_names))
if audit_violations:
    raise RuntimeError(f"Constraint violations: {audit_violations}")
```

### Validation

- **Exhaustive encoding proof**: All n ≤ 8, all k ≤ n-1, all 2^n primary assignments verified (3,286 SAT checks in 0.06s) via mini DPLL solver
- **Audit completeness**: Brute-force enumeration of all 16 assignments for n=4 with all 3 constraint types — audit agrees with brute-force on every assignment (0 false positives, 0 false negatives)
- **Cross-validation**: 100 random models via Hypothesis PBT tested against pysat (Glucose3 CDCL) — Rust and pysat agree on SAT/UNSAT for all cases
- **Inductive proof**: Documented in `encoding.rs` — Sinz (2005) sequential counter is correct by published proof; base cases exhaustively verified; correctness extends to arbitrary N by induction

## Why This Works

The sequential counter introduces auxiliary variables `s[i][j]` that form a transitive closure of partial sums, ensuring `sum(vars) ≤ K` by induction. The CDCL solver (CaDiCaL, migrated from splr) can propagate through these auxiliary variables — the Python greedy solver could not, which is why the Python solver was removed rather than kept as fallback.

The constraint audit is the backstop: even if the CDCL implementation regresses, violations cannot pass silently because every output is validated against the input model.

## Forward Reference

The ESL+BMC+PBT+audit verification pattern developed here was generalized in
the [PCL constraint system triple extension](docs/solutions/architecture-patterns/pcl-constraint-system-triple-extension-2026-07-01.md),
which applies the same correctness architecture to decoupling auto-detection,
semantic tag dispatch, and keepout zone constraints.

## Prevention

- Constraint audit (`audit.rs`, exposed to Python as `temper_rust_router.audit_result`) runs after every Rust solve that reaches a `"sat"` status, on **both** of `router_v6`'s production solve paths — violations raise `RuntimeError`, not a warning:
  - **Monolithic** (`RouteStage`): `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:437-452`.
  - **Net-batching** (`--net-batching`, the flag the production board recipe uses — `docs/evidence/2026-08-12-board-recipe-reproducibility.md`): `packages/temper-placer/src/temper_placer/router_v6/net_batching.py`'s `_solve_subset` computes `audit_violations` right after the solve (:504-513, while it still holds `cm.variables`/`cm.constraints` — the one place in the subprocess-per-batch design that does); `run_net_batched_stage3` raises `RuntimeError` on a non-empty result at its batch-level (:1136-1143) and singleton-retry (:1196-1203) `"sat"` handling, the two call sites a batch's result can reach production topology from.
  - **Self-verifying test**: `packages/temper-placer/tests/router_v6/test_net_batching_constraint_audit.py` asserts the audit is actually *invoked* by `_solve_subset` with the real solved model (not merely importable/callable directly, which `test_stage3_constraint_audit.py` already covered) and that `run_net_batched_stage3` raises when a batch reports a violation.
  - **Erratum (2026-06-28 – 2026-08-12).** This claim was false for the net-batching path for the six weeks between this doc's original publication and the fix above: `net_batching.py` never imported or called `audit_result` — zero call sites, confirmed by `rg audit_result packages/temper-placer/src/temper_placer/router_v6/net_batching.py` returning nothing before the fix — so a violation produced by a batched solve would have passed through to Stage 4 and the final board with no check at all. Only the monolithic path (used by non-batched routes) was ever audited. Found and closed by `docs/plans/2026-08-12-003-fix-sat-capacity-encoding-plan.md` (PR #1065, branch `spike/sat-capacity-vacuity`)'s R3/R4.
  - **What the audit actually reports on the real board, measured, not assumed.** A full `--net-batching` route of the committed `pcb/temper.kicad_pcb` (2026-08-12, `scripts/route_board.py --net-batching`, `TEMPER_BATCH_TRACE=1`) reached `"sat"` and was audited on **all 11 of 11 batches (110/110 nets)**, with **zero constraint violations** and no `RuntimeError` raised (`[batch-trace] done: 11 batches, 11 solved at batch level, 0 batch-level crashes` in the run's own trace output, no exception in the run log). This is consistent with — and does not yet contradict — the separate, still-open structural finding in the same plan that nothing in net-batching's Stage-3 model currently forces a `NetChannelVar` true in the first place, which would make a clean audit result on every batch the expected outcome rather than evidence the constraint is being meaningfully exercised. That question (whether `uses_channels` carries real data under net-batching at all) is out of scope for this erratum and is the separate, not-yet-executed U1/U2 measurement in the same plan.
- Hypothesis property-based tests cross-validate the Rust solver against pysat (Glucose3 CDCL) on random models — runs as `@pytest.mark.slow` in CI
- Exhaustive sequential counter verification (n ≤ 8) in Rust unit tests — any encoding change must pass all 3,286 checks
- Python AtMostK encoding also fixed (U1) for cases where the sequential counter is exercised without CDCL — validated via exhaustive search in `test_sat_model.py`
- `rustsat CaDiCaL` panic on repeated calls mitigated with `std::panic::catch_unwind` — solver returns `Unknown` status rather than crashing the Python process

### ESL + BMC verification infrastructure (2026-06-28)

The following additional verification layers were added to make the encoding correctness automatically provable rather than test-dependent:

- **ESL (Encoder Specification Language)** — `esl.py`: Predicate DSL with 6 primitives (`at_most_k`, `all_true`, `any_true`, `exactly_one_of`, `implies`, `iff`, `all_false`) plus `and_`/`or_` composition. `eval_esl(model, assignment)` provides executable ground truth — this is what the CNF encoding must agree with for every assignment.
- **BMC (Bounded Model Checking)** — `bmc.py`: Exhaustive enumeration of all 2^N primary-variable assignments (N ≤ 10), cross-checks ESL ground truth against CNF satisfiability via pysat. Returns counterexample diagnostics with copy-pasteable reproduction snippets.
- **`esl()` methods on constraint classes** — `CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint` each define their semantics declaratively in ESL, decoupling "what the constraint means" from "how it's encoded in CNF."
- **`skip_connectivity` parameter** — `populate_sat_from_constraints(sat, cm, net_names, skip_connectivity=True)` excludes per-net connectivity clauses so primary-variable count stays within the BMC bound (≤10 vars, 1024 assignments).
- **Property-based tests** — 91 tests in `test_bmc_property.py` + `test_bmc_encoding.py` + `test_bmc_diagnostics.py`: sequential counter exhaustive proof (n ≤ 8, matching the Rust `encoding.rs` base case), inductive extension (n → n+1), 200 random Hypothesis PBT models, and 82 exhaustive topology tests. Run automatically in CI (`tests/router_v6/ -m "not slow"`).
- **Pipeline ESL verify hook** — ESL predicates are verified at test time via BMC (bounded model checking), not at runtime.
- **`diagnose_submodel()`** — Implemented in Rust (`bmc.rs`) for UNSAT debugging but not yet exported to Python via `lib.rs`. Samples the most-constrained channels (capped at 10 vars) and runs BMC on the sub-model to verify whether the UNSAT is genuine (overconstrained) or a solver bug.
