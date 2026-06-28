---
title: "feat: Gated experiment — optimize SAT encoding for Temper PCB scale"
type: feat
status: active
date: 2026-06-28
origin: docs/brainstorms/2026-06-28-sat-encoding-optimization-experiment-requirements.md
---

# SAT Encoding Optimization Experiment

## Summary

A gated, adaptive experiment that tests two encoding-optimization strategies against the 619K-clause baseline on the Temper PCB. Conditions are implemented in increasing-complexity order with early stopping. Measurements come from the Rust `CnfFormula` (the actual solver input), not the Python `SATModel`. The winning strategy is selected when it passes both the clause-count reduction gate and the solve-time budget.

---

## Problem Frame

The current sequential-counter encoding produces ~619K clauses for the Temper PCB. splr 0.13 cannot solve within a reasonable timeout. Two hypotheses: (1) most channels are unconstrained and AtMostK is wasted on them (pruning); (2) a tree-based totalizer is asymptotically better than the sequential counter (totalizer).

(see origin: `docs/brainstorms/2026-06-28-sat-encoding-optimization-experiment-requirements.md`)

---

## Requirements

- R1. Expose `num_vars` and `num_clauses` from Rust `CnfFormula` in `TopologyResult`
- R2. Implement bottleneck pruning — skip `encode_at_most_k` for channels where demand/capacity ≤ 1.0
- R3. Implement totalizer encoding — replace sequential counter with binary-tree totalizer
- R4. Experiment script runs the gated sequence with early stopping per the stop criteria
- R5. Constraint audit passes with zero violations for every condition
- R6. Constraint-completeness check: pruning must not drop constraints from constrained channels
- R7. JSON report at `metrics/sat_encoding_experiment.json`
- R8. Cleanup commit removes losing feature flags and dead encoding code

**Origin actors:** A1 (Developer), A2 (Constraint audit)
**Origin acceptance examples:** AE1 (pruning clean), AE2 (JSON report), AE3 (audit failure halts), AE4 (TopologyResult fields)

---

## Scope Boundaries

- Does not change the solver (splr 0.13 with `catch_unwind`)
- Does not benchmark against other SAT solvers

### Deferred to Follow-Up Work

- Solver-backend comparison (varisat, cadical-rs) if all encoding strategies fail
- Problem decomposition (route worst nets via SAT, easy nets via A*)

---

## Context & Research

### Relevant Code and Patterns

- `packages/temper-rust-router/src/encoding.rs` — `encode_at_most_k()`, the sequential counter to optimize or replace
- `packages/temper-rust-router/src/types.rs:348-355` — `TopologyResult` struct, needs `num_vars`/`num_clauses` fields
- `packages/temper-rust-router/src/lib.rs:39-50` — `solve_topology_rust()`, wires CnfFormula → solver → TopologyResult
- `packages/temper-rust-router/src/solver.rs` — `solve_with_splr()`, the solver being tested
- `packages/temper-rust-router/src/audit.rs` — constraint audit (already proven correct)

### Institutional Learnings

- The sequential counter encoding is exhaustively verified (n ≤ 8, 3,286 checks) and cross-validated against pysat (100 examples)
- The constraint audit is proven complete (brute-force for n=4 with all 3 constraint types)
- The Temper PCB produces 432,307 variables and 619,034 clauses with the baseline encoding — verified by benchmarking

---

## Key Technical Decisions

- **Gated sequence over parallel measurement.** Conditions are implemented one at a time. If pruning works, totalizer is never built. This is the experiment's cost-control mechanism.
- **Rust CnfFormula over Python SATModel for measurement.** The Rust `CnfFormula` is what splr actually receives. The Python `SATModel` is an independent encoding path that may differ from the Rust path — measuring from it would be blind to the change being tested.
- **splr seed for determinism.** A fixed random seed removes nondeterminism as a variable. One measured trial per condition is sufficient.
- **Constraint-completeness check for pruning.** Pruning removes constraints, and the audit only checks surviving constraints. The completeness check asserts that dropped constraints came from unconstrained channels.

---

## Implementation Units

### U1. Expose `num_vars` and `num_clauses` in Rust `TopologyResult`

**Goal:** Add clause and variable counts to the Rust→Python result so the experiment can measure them.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Modify: `packages/temper-rust-router/src/types.rs`
- Modify: `packages/temper-rust-router/src/lib.rs`

**Approach:**
- Add `num_vars: usize` and `num_clauses: usize` fields to `TopologyResult` in `types.rs`.
- In `lib.rs:solve_topology_rust()`, populate them from `cnf.num_vars` and `cnf.clauses.len()` after encoding.
- Export both fields in the Python result dict returned by `solve_topology_rust`.

**Test scenarios:**
- Happy path: Solver returns SAT — result dict contains `num_vars` and `num_clauses` with nonzero values
- Edge case: Empty model (no nets, no channels) — both fields are zero
- Edge case: Solver returns Unknown (splr panic) — fields are populated from the CnfFormula regardless of solver status

**Verification:**
- `python -c "from temper_rust_router import solve_topology_rust; r = solve_topology_rust(...); assert 'num_vars' in r and 'num_clauses' in r"` — passes

---

### U2. Implement bottleneck pruning in `encoding.rs`

**Goal:** Skip `encode_at_most_k` for channels where demand/capacity ≤ 1.0, reducing clause count for unconstrained channels.

**Requirements:** R2, R5, R6

**Dependencies:** None

**Files:**
- Modify: `packages/temper-rust-router/src/encoding.rs`

**Approach:**
- Add a `bottleneck_demand_map: HashMap<String, f64>` parameter to `encode_to_cnf()` — maps channel_id → demand/capacity ratio.
- In the capacity constraint encoding branch, before calling `encode_at_most_k`, check if `demand_ratio ≤ 1.0`. If so, skip the encoding — the channel can hold all candidate nets without a cardinality constraint.
- Behind a boolean parameter `prune_bottlenecks: bool` (default `false` for backward compat). When `false`, all channels get encoded (baseline behavior).
- The constraint-completeness check (R6) runs outside the encoding — the experiment script compares the constraint set size per condition.

**Test scenarios:**
- Happy path: Channel with demand=0.75 (ratio < 1.0), pruning enabled → zero aux vars, audit clean (Covers AE1)
- Happy path: Channel with demand=2.5 (ratio > 1.0), pruning enabled → AtMostK still encoded, audit clean
- Edge case: All channels unconstrained → auxiliary variable count drops to near zero
- Edge case: All channels constrained → identical to baseline encoding

**Verification:**
- `cargo test encoding` — new unit test: pruning skips constrained channels, encodes unconstrained ones

---

### U3. Implement totalizer encoding in `encoding.rs`

**Goal:** Replace the sequential counter with a binary-tree totalizer (Sinz 2005, §4) for O(n log k) encoding.

**Requirements:** R3, R5

**Dependencies:** None

**Files:**
- Modify: `packages/temper-rust-router/src/encoding.rs`

**Approach:**
- Add a `use_totalizer: bool` flag (default `false`). When `true`, replace `encode_at_most_k()` with a binary-tree totalizer implementation.
- The totalizer encodes AtMostK as a tree of pairwise `(a, b) → (sum, carry)` nodes. Each node introduces O(1) auxiliary variables per bit. Total: O(n log k).
- The output clauses encode the same constraint as the sequential counter — `sum(vars) ≤ k`.
- The existing `encode_at_most_k` function is preserved. The totalizer is a parallel implementation behind the flag — the experiment script decides which to call.

**Test scenarios:**
- Happy path: 4 nets, k=2 with totalizer — at most 2 true, audit clean
- Happy path: 10 nets, k=3 with totalizer — at most 3 true, audit clean
- Edge case: n=0, n=1, k=0, k≥n — trivial cases handled identically to sequential counter
- Regression: Totalizer + sequential counter produce identical SAT/UNSAT for random models (verified by existing pysat cross-validation)

**Verification:**
- `cargo test encoding` — new unit tests: totalizer passes same exhaustive checks as sequential counter

---

### U4. Create experiment script with gated sequence

**Goal:** A Python script that implements the adaptive experiment: run baseline, implement and test pruning, evaluate stop criteria, proceed to totalizer only if needed.

**Requirements:** R4, R5, R6, R7

**Dependencies:** U1, U2, U3

**Files:**
- Create: `scripts/experiment_sat_encoding.py`

**Approach:**
- The script takes `pcb_path` as argument.
- Stage 1 (baseline): Parse PCB, build constraint model, call `solve_topology_rust()` with current encoding, record `num_vars`, `num_clauses`, `solver_time_ms`, audit status.
- Stage 2 (pruning): Rebuild with `cargo build --features prune_bottlenecks`, then `maturin develop`. Re-run the solve. Record metrics. Check stop criteria (SC1 + SC2). If both pass, select pruning as winner, write JSON, exit.
- Stage 3 (totalizer): Only if stage 2 failed. Rebuild with `cargo build --features use_totalizer`, re-run. Check stop criteria. If pass, select totalizer as winner.
- Stage 4 (combined): Only if stages 2 and 3 each failed individually. Rebuild with both features, re-run.
- Each stage runs the constraint-completeness check: compare constraint set size against baseline. For pruning stages, assert dropped constraints came from ratio ≤ 1.0 channels.
- Write JSON report with per-stage metrics plus the selection decision.

**Test scenarios:**
- Happy path: Pruning passes SC1+SC2 → stops after stage 2 (Covers AE2)
- Happy path: Pruning fails, totalizer passes → stops after stage 3
- Edge case: Both fail individually, combined passes → stops after stage 4
- Edge case: All fail → JSON report with partial-improvement data, recommended follow-up
- Error path: Constraint audit returns violations → experiment halts, marked FAILED (Covers AE3)

**Verification:**
- `python scripts/experiment_sat_encoding.py pcb/temper_agent_optimized.kicad_pcb` — produces `metrics/sat_encoding_experiment.json` with correct gating logic

---

### U5. Run experiment, validate results, select winner

**Goal:** Execute the experiment on the Temper PCB, verify correctness, and commit the winning encoding configuration.

**Requirements:** SC1-SC4, R8

**Dependencies:** U4

**Files:**
- Modify: `packages/temper-rust-router/src/encoding.rs` (remove losing feature flags)
- Create: `metrics/sat_encoding_experiment.json`

**Approach:**
- Run the experiment script. Verify that the constraint audit passes (zero violations) and the constraint-completeness check passes (no constrained channels dropped).
- Verify reproducibility: run the winning condition twice, assert clause/variable counts within 1%.
- The winning encoding becomes the permanent code path. Remove the losing feature flags and dead encoding code.
- Keep the baseline encoding tests (sequential counter) since they validate correctness — they're not feature-flagged.

**Test scenarios:**
- Happy path: Experiment script produces valid JSON with a clear winner
- Reproducibility: Two runs of the winning condition produce clause counts within 1%
- Cleanup: After removing losing flags, `cargo build` succeeds without feature flags

**Verification:**
- `cat metrics/sat_encoding_experiment.json | python -m json.tool` — valid JSON
- `git grep "prune_bottlenecks\|use_totalizer" packages/temper-rust-router/src/` — no references remain (unless pruning was the winner — then `prune_bottlenecks` stays as the permanent code path)

---

## System-Wide Impact

- **Encoding.rs** gains two new encoding strategies behind flags. The winning strategy becomes permanent; the losing one is deleted.
- **TopologyResult** gains two fields — backward compatible (existing callers ignore new fields).
- **Experiment script** is self-contained — imports only constraint model types and the Rust crate, not the full pipeline. Does not require JAX.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Pruning drops a constrained channel (demand ratio miscomputed) | Constraint-completeness check catches this — asserts dropped channels are genuinely unconstrained |
| Totalizer encoding has a bug that passes the audit on test models but fails on real board | Exhaustive verification for n≤8 applies to totalizer too — same test suite |
| splr panics on repeated constraint shapes with new encoding | `catch_unwind` catches panics; experiment records `Unknown` status |
| Experiment script takes too long (multiple maturin rebuilds) | Each rebuild is <10s; total experiment time dominated by solver runs, not rebuilds |

---

## Sources & References

- **Origin document:** `docs/brainstorms/2026-06-28-sat-encoding-optimization-experiment-requirements.md`
- Sinz, C. (2005). "Towards an Optimal CNF Encoding of Boolean Cardinality Constraints." CP 2005.
- `packages/temper-rust-router/src/encoding.rs` — current sequential counter implementation
- `packages/temper-rust-router/src/types.rs` — TopologyResult struct
- `packages/temper-rust-router/src/audit.rs` — constraint audit module
