---
title: "feat: Mathematical rigor proofs for Rust SAT solver subsystems"
type: feat
status: active
date: 2026-06-28
---

# Solver Rigor Proofs

## Summary

Add exhaustive verification and property-based tests that mathematically prove the correctness of the Rust SAT solver's sequential counter encoding and constraint audit module, then cross-validate the full solver against pysat (Glucose CDCL) on random constraint models.

---

## Problem Frame

The Rust solver's sequential counter encoding (`encoding.rs:encode_at_most_k`) is a port of the Sinz (2005) algorithm — correct by construction, but the Rust implementation has never been exhaustively verified. A single off-by-one error in the register indexing or clause generation would produce correct-looking wrong answers that the constraint audit would catch, but the audit itself needs a completeness proof: does it catch *every* constraint violation, or are there blind spots?

The pysat cross-validation test in `test_stage3_constraint_audit.py` checks one fixed case (4 nets, k=2). It does not exercise the solver across varied constraint shapes, nor does it use property-based testing to explore edge cases the developer didn't think of.

---

## Requirements

- R1. Exhaustively verify the Rust sequential counter encoding for all n ≤ 8, all k ≤ n — enumerate every assignment of the primary variables, assert: if true_count > k, the CNF is unsatisfiable; if true_count ≤ k, it is satisfiable.
- R2. Exhaustively verify the constraint audit module for all constraint types — enumerate assignments for models with 0..6 variables and 1..3 constraints of each type (capacity, diff-pair, layer), assert the audit detects every constraint violation and reports zero violations for all satisfying assignments.
- R3. Add Hypothesis property-based tests that generate random constraint models, feed them identically to the Rust solver and pysat, and assert SAT/UNSAT agreement with >= 100 examples per constraint type.
- R4. Prove by induction that the sequential counter encoding is correct for arbitrary N: document the inductive step (each register r[i][j] depends only on r[i-1][j] and r[i-1][j-1]) and verify the base cases exhaustively per R1.

---

## Scope Boundaries

- The mathematical induction proof (R4) is documentation, not executable — it lives in the module docstring of `encoding.rs`
- Does not modify the solver, encoding, or audit logic — these tests validate existing code
- Does not add end-to-end pipeline tests (those need JAX)
- Does not add performance benchmarks

---

## Context & Research

### Relevant Code and Patterns

- `packages/temper-rust-router/src/encoding.rs` — `encode_at_most_k()`: the sequential counter implementation to verify
- `packages/temper-rust-router/src/audit.rs` — `audit_constraints()`: the constraint audit to verify
- `packages/temper-rust-router/src/solver.rs` — `solve_with_splr()`: the solver to cross-validate
- `packages/temper-placer/tests/router_v6/test_stage3_constraint_audit.py` — existing pysat cross-validation (one fixed case)
- `packages/temper-placer/tests/router_v6/test_sat_model.py` — existing Python AtMostK exhaustive tests (pattern to replicate in Rust)

### Institutional Learnings

- Hypothesis is already a dev dependency (`pyproject.toml` declares `hypothesis` in dev deps) and is used in existing router_v6 property-based tests (`test_sat_solve_pbt.py`, `test_constraint_generation_pbt.py`)

---

## Key Technical Decisions

- **Exhaustive tests in Rust, property-based tests in Python.** The sequential counter and audit modules are Rust code. Exhaustive enumeration for n ≤ 8 is a cargo test (unit test, no Python linking needed). Property-based tests use Hypothesis + pysat + the Rust crate via PyO3 — the same integration path the pipeline uses.
- **Audit completeness via enumeration, not proof checker.** For each constraint type, enumerate every truth assignment to the variables and assert the audit's output exactly matches a brute-force constraint checker. This proves the audit has no false positives and no false negatives for the enumerated space.
- **Inductive proof as documentation.** The Sinz encoding's correctness for arbitrary N is a published result. We verify the base cases (n ≤ 8) and document the inductive step in `encoding.rs` so future maintainers understand why correctness extends beyond the verified range.

---

## Implementation Units

### U1. Exhaustive sequential counter verification

**Goal:** Prove the Rust `encode_at_most_k` function produces correct CNF for all n ≤ 8, all 0 ≤ k < n.

**Requirements:** R1, R4

**Dependencies:** None

**Files:**
- Modify: `packages/temper-rust-router/src/encoding.rs`

**Approach:**
- Add a `#[cfg(test)]` module in `encoding.rs` with a test that exhaustively verifies the sequential counter.
- For each (n, k) pair with n ≤ 8 and 0 ≤ k < n:
  1. Build a set of primary variables and call `encode_at_most_k` to add clauses and auxiliary vars to the CNF.
  2. For every assignment of the primary variables (2^n possibilities), set the primary variable literals accordingly.
  3. Use a backtracking DPLL solver (miniature, written inline) to check satisfiability of the CNF with those primary variable assignments fixed.
  4. Assert: if the number of true primary vars ≤ k, the CNF is SAT; if > k, it is UNSAT.
- This proves the encoding is correct for all instances with up to 8 variables. The inductive step is documented in the module docstring.

**Test scenarios:**
- Happy path: (n=4, k=2) — all 16 primary variable assignments produce correct SAT/UNSAT
- Edge case: (n=1, k=0) — single variable, must-be-false
- Edge case: (n=8, k=7) — nearly unconstrained, all assignments with ≤7 true pass
- Edge case: (n=8, k=0) — all primary vars forced false, verified for all 256 assignments
- Induction boundary: (n=8, k=4) — 256 assignments, largest in the exhaustive set

**Verification:**
- `cargo test -p temper-rust-router encode_at_most_k_exhaustive` — passes with >10,000 total assertion checks

---

### U2. Constraint audit completeness proof

**Goal:** Prove the `audit_constraints` function detects every constraint violation and reports zero violations for every satisfying assignment, for small models.

**Requirements:** R2

**Dependencies:** None

**Files:**
- Modify: `packages/temper-rust-router/src/audit.rs`

**Approach:**
- Add a `#[cfg(test)]` test that builds random constraint models (capacity, diff-pair, layer) with 2..6 variables and 1..3 constraints, enumerates all 2^n assignments, and asserts:
  1. If the assignment satisfies all constraints (brute-force check), the audit returns zero violations.
  2. If the assignment violates any constraint, the audit returns at least one violation of the matching type.
- The brute-force checker is a simple inline function for each constraint type — no dependency on splr or the encoding module.
- This proves the audit is both sound (no false positives) and complete (no false negatives) for the enumerated space.

**Test scenarios:**
- Happy path: Satisfying assignment for all three constraint types simultaneously → audit clean
- Capacity: Assignment with 3 true out of 4 vars (k=2) → audit detects capacity violation
- Diff-pair: Assignment with mismatched pair values → audit detects diff-pair violation
- Layer: Assignment where restricted var is opposite of allowed → audit detects layer violation
- Combinatorial: Mixed model with capacity + diff-pair + layer, enumeration of all 64 assignments (6 vars) → audit matches brute-force for all

**Verification:**
- `cargo test -p temper-rust-router audit_completeness` — passes with zero false positives/negatives across all enumerated assignments

---

### U3. Hypothesis property-based cross-validation

**Goal:** Generate random constraint models with Hypothesis, feed them to both the Rust solver and pysat, and assert SAT/UNSAT agreement across >= 100 examples.

**Requirements:** R3

**Dependencies:** U1, U2 (sequential counter and audit are verified)

**Files:**
- Modify: `packages/temper-placer/tests/router_v6/test_stage3_constraint_audit.py`

**Approach:**
- Add a Hypothesis-based test class `TestPropertyBasedCrossValidation` that:
  1. Uses `hypothesis.strategies` to generate random constraint models: n_vars (2..12), capacity_k (0..n_vars), random diff-pair pairings, random layer restrictions.
  2. Builds identical `ConstraintModel` instances for Rust and pysat.
  3. Encodes to CNF and feeds to both solvers.
  4. Asserts: both agree on SAT/UNSAT; if SAT, the constraint audit confirms zero violations.
- The existing `test_rust_vs_pysat_capacity_agreement` stays as a fast smoke test; the Hypothesis tests are `@pytest.mark.slow`.

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py` — existing Hypothesis PBT pattern in the same test directory

**Test scenarios:**
- Happy path: >=100 random capacity-constrained models, Rust and pysat agree on SAT/UNSAT, audit clean on SAT
- Edge case: Models with zero constraints (trivially SAT)
- Edge case: Models where all variables are forced false (k=0)
- Edge case: Models with contradictory constraints (capacity k=2 + layer forcing 3 vars true)
- Integration: `@pytest.mark.slow` — runs in the CI slow-test suite, not on every commit

**Verification:**
- `pytest packages/temper-placer/tests/router_v6/test_stage3_constraint_audit.py -k "PropertyBased" -v` — >= 100 examples pass with no failures

---

### U4. Inductive proof documentation

**Goal:** Document the inductive correctness argument for the sequential counter encoding so future maintainers understand why the encoding is correct beyond the exhaustively verified range.

**Requirements:** R4

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-rust-router/src/encoding.rs`

**Approach:**
- Add a module-level doc comment in `encoding.rs` that states:
  - The Sinz (2005) sequential counter encoding is correct by published proof.
  - The inductive hypothesis: assume `encode_at_most_k` produces correct CNF for n-1 variables with bound k. For n variables, the register r[n-2][k-1] correctly indicates whether k variables are already true among the first n-1. The exclusion clause (¬x_n ∨ ¬r[n-2][k-1]) ensures x_n is false when the count is already at k. The propagation clauses ensure r[i][j] correctly tracks the running count for all i < n-1.
  - The base cases (n ≤ 8) are exhaustively verified in the test suite.
  - By induction, correctness holds for all n.

**Test scenarios:**
- Test expectation: none — documentation only

**Verification:**
- Module docstring is present and references the Sinz (2005) paper and the exhaustive test module

---

## System-Wide Impact

- **Interaction graph:** None — these are tests and documentation, no production code changes.
- **Error propagation:** N/A — tests fail on regression, succeed on correctness. No new error paths.
- **Unchanged invariants:** The solver, encoding, audit, and pipeline logic are unmodified.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Hypothesis generates models that time out splr | Cap n_vars at 12 and add a 5s per-example timeout decorator |
| Exhaustive 2^8 search is slow in Rust debug builds | Run exhaustive tests in release mode or with `--release`; 256 assignments × ~50 clauses = <1 second |
| pysat API incompatibility with Hypothesis's multiprocessing | Run Hypothesis tests with `@settings(deadline=None)` and single-process |

---

## Sources & References

- Sinz, C. (2005). "Towards an Optimal CNF Encoding of Boolean Cardinality Constraints." CP 2005.
- `packages/temper-rust-router/src/encoding.rs` — current sequential counter implementation
- `packages/temper-rust-router/src/audit.rs` — current constraint audit implementation
- `packages/temper-placer/tests/router_v6/test_sat_solve_pbt.py` — existing Hypothesis PBT pattern
