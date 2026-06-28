---
title: "Router V6 SAT solver produced unsound AtMostK capacity assignments"
date: "2026-06-28"
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
  - splr
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

### Layer 2 — CDCL solver (splr via PyO3)

Created `packages/temper-rust-router/` as a maturin-based PyO3 crate. splr 0.13 provides CDCL with clause learning, watched literals, and restarts. The sequential counter is encoded as CNF clauses (splr 0.13 lacks a native `add_atmostk` API).

```rust
// splr integration with catch_unwind (splr panics on repeated instantiation)
let result = std::panic::catch_unwind(
    std::panic::AssertUnwindSafe(|| solver.solve())
);
```

### Layer 3 — Constraint audit

An inline audit module validates every solver output against the input constraint model. Capacity, diff-pair, and layer constraints are checked after every solve. Violations raise `RuntimeError` — no silent wrong answers.

```python
# pipeline.py — audit runs after every Rust solve
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

The sequential counter introduces auxiliary variables `s[i][j]` that form a transitive closure of partial sums, ensuring `sum(vars) ≤ K` by induction. The CDCL solver (splr) can propagate through these auxiliary variables — the Python greedy solver could not, which is why the Python solver was removed rather than kept as fallback.

The constraint audit is the backstop: even if the CDCL implementation regresses, violations cannot pass silently because every output is validated against the input model.

## Prevention

- Constraint audit (`audit.rs`) runs unconditionally after every Rust solve — violations raise `RuntimeError`, not a warning
- Hypothesis property-based tests cross-validate the Rust solver against pysat (Glucose3 CDCL) on random models — runs as `@pytest.mark.slow` in CI
- Exhaustive sequential counter verification (n ≤ 8) in Rust unit tests — any encoding change must pass all 3,286 checks
- Python AtMostK encoding also fixed (U1) for cases where the sequential counter is exercised without CDCL — validated via exhaustive search in `test_sat_model.py`
- `splr::Solver` panic on repeated calls mitigated with `std::panic::catch_unwind` — solver returns `Unknown` status rather than crashing the Python process
