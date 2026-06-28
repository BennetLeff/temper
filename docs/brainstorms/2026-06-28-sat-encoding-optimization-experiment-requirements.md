---
date: 2026-06-28
topic: sat-encoding-optimization-experiment
---

# SAT Encoding Optimization — Scientific Experiment

## Summary

A gated, adaptive experiment to find the minimum-complexity encoding change that makes the Rust SAT solver tractable on the Temper PCB. Conditions are tested in increasing-complexity order with early stopping: if a simpler change works, more complex ones are never implemented. All measurements come from the Rust `CnfFormula` (the actual solver input), not the Python `SATModel`.

---

## Problem Frame

The current sequential-counter encoding produces ~619K clauses for the Temper PCB (23 nets, 2 signal layers, ~6,000 skeleton edges). splr 0.13 cannot solve this within a reasonable timeout. The encoding is correct but computationally explosive — O(n·k) auxiliary variables per capacity constraint, where many channels have dozens of candidate nets. Two hypotheses need testing: (1) most channels are unconstrained and AtMostK is wasted on them; (2) a tree-based totalizer is asymptotically better than the sequential counter.

---

## Actors

- A1. **Developer** — runs the experiment, evaluates each condition against the stop criteria
- A2. **Constraint audit** — the correctness gate: zero violations for every condition

---

## Experiment Design

### Gated sequence with early stopping

Conditions are implemented and tested in order. If a condition passes both success criteria, the experiment stops — no further conditions are implemented or tested. This guarantees the simplest viable encoding is selected.

| Step | Condition | Strategy | Implement only if |
|------|-----------|----------|-------------------|
| 1 | **Baseline** (A) | Sequential counter (current) | Always (establishes baseline) |
| 2 | **Pruning** (B) | Bottleneck-only encoding | Always after A |
| 3 | **Totalizer** (C) | Tree-based cardinality encoding | Only if B fails |
| 4 | **Combined** (D) | B + C together | Only if B and C each fail individually |

### Pruning mechanism (B)

Skip `encode_at_most_k` for any channel where `demand / capacity ≤ 1.0` — the channel can hold all candidate nets without a cardinality constraint. Stage 2's `BottleneckAnalysis` provides the demand/capacity ratio per channel.

### Totalizer mechanism (C)

Replace the Sinz sequential counter with a binary-tree totalizer (Sinz 2005, §4). Encodes `sum(vars) ≤ K` using `O(n log K)` auxiliary variables instead of `O(n·K)`. Exact implementation follows the published paper.

### Dependent variables

| Metric | Source | Notes |
|--------|--------|-------|
| Clause count | `TopologyResult.num_clauses` (exposed from Rust `CnfFormula`) | Primary metric |
| Variable count | `TopologyResult.num_vars` (exposed from Rust `CnfFormula`) | Secondary metric |
| Solver wall time | `TopologyResult.solver_time_ms` | Reported for every solve, not gated on a fixed timeout |
| Constraint audit | `audit_result()` | Zero violations required for every condition |
| Constraint completeness | Comparison of constraint set size per condition vs baseline | Pruning (B) must not drop constraints whose demand/capacity > 1.0 |

splr is given up to 120s; if it times out, the experiment records `solver_time_ms = None` and the condition is treated as "did not complete within budget." The splr decision counter is also recorded so near-miss timeouts (solver made progress but didn't finish) are distinguishable from immediate failures.

### Controls

- Same board: `pcb/temper_agent_optimized.kicad_pcb` for all conditions
- Same machine, same Python version, same rustc version
- Same splr random seed (set via `splr::Config` for deterministic solves)
- Warm-up solve before measurement (discard)
- One measured solve per condition (encoding is deterministic, solver is seeded)
- Constraint-completeness check: after pruning, assert no constraint was dropped from a channel with demand/capacity > 1.0
- splr 0.13 with `catch_unwind` — solver crash treated as `Unknown`

---

## Requirements

- R1. Expose `num_vars` and `num_clauses` from Rust `CnfFormula` in `TopologyResult`, exported to the Python result dict
- R2. Implement bottleneck pruning behind a compile-time flag in `encoding.rs` — skip `encode_at_most_k` for channels where demand/capacity ≤ 1.0
- R3. Implement totalizer encoding behind a compile-time flag in `encoding.rs` — replace the sequential counter with a binary-tree totalizer
- R4. The experiment script runs the gated sequence on `pcb/temper_agent_optimized.kicad_pcb`: measure A, implement B and measure, evaluate stop criteria, implement C only if B failed, etc.
- R5. The constraint audit passes with zero violations for every condition — correctness is non-negotiable
- R6. The constraint-completeness check asserts that pruning (B, D) only drops constraints from low-demand channels
- R7. The experiment script writes a JSON report to `metrics/sat_encoding_experiment.json` with per-condition metrics and the stopping decision
- R8. After the experiment concludes, losing feature flags and dead encoding code are removed in a cleanup commit

---

## Acceptance Examples

- AE1. **Covers R2, R5, R6.** Pruning (B) skips AtMostK for a channel where demand=3, capacity=4 (ratio=0.75) — audit clean, zero aux vars for that channel
- AE2. **Covers R4, R7.** Running the experiment produces a JSON report with entries for A and B (and C/D only if needed), each carrying clause count, variable count, solver time, audit status, and the stop decision
- AE3. **Covers R5.** Any condition that produces a non-empty `audit_result()` list or drops a constrained channel is marked as FAILED and the experiment halts
- AE4. **Covers R1.** After the experiment, `TopologyResult` carries `num_vars` and `num_clauses` populated from `CnfFormula`

---

## Success Criteria

- SC1. At least one condition (beyond baseline) reduces clause count by ≥ 50%
- SC2. At least one condition (beyond baseline) produces a SAT assignment within the 120s budget — if the solver made progress but timed out, report decisions/clauses alongside the timeout for analysis
- SC3. The constraint audit passes with zero violations for all conditions
- SC4. The experiment is reproducible — running it twice on the same hardware produces clause/variable counts within 1% (deterministic encoding + seeded solver)

### Stop criteria per step

After measuring condition B: if both SC1 and SC2 pass, select B as the winning encoding and stop. Otherwise, proceed to C. After measuring condition C: if SC1 and SC2 both pass, select C and stop. Otherwise, proceed to D. If D fails both criteria, the experiment concludes with partial-improvement data and a recommended follow-up (solver-backend comparison or problem decomposition).

### Selection logic

If multiple conditions pass both criteria (possible only in the combined D case where B and C individually failed), select D — it's the only condition that works. No tiebreaker is needed because the gated sequence guarantees at most one condition is selected.

---

## Scope Boundaries

- Does not change the solver (splr 0.13 with `catch_unwind`)
- Does not benchmark against other SAT solvers — this experiment compares encoding strategies
- The winning encoding is cleaned up (feature flags removed, dead code deleted) in a follow-up commit
- Does not require JAX — measurements are taken from the Rust CnfFormula, not the full pipeline

### Deferred for later

- Solver-backend comparison (varisat, cadical-rs) if all encoding strategies fail
- Problem decomposition (route worst nets via SAT, easy nets via A*) if encoding alone is insufficient

---

## Key Decisions

- **Gated sequence over parallel measurement.** Implementing all four conditions unconditionally wastes effort when a simpler approach may suffice. The gated sequence guarantees the simplest viable encoding wins.
- **Rust CnfFormula over Python SATModel for measurement.** The Rust `CnfFormula` is the actual solver input — measuring from it avoids the Python/Rust measurement gap.
- **Constraint audit + completeness over golden fixtures.** The audit proves each condition's assignments satisfy its constraints. The completeness check proves pruning didn't silently drop a real constraint.
- **Deterministic solver (seeded) over multiple trials.** With a fixed splr seed, 1 measured solve per condition is sufficient. The 1% reproducibility check validates determinism.

---

## Dependencies / Assumptions

- The constraint audit (`audit.rs`) is already proven correct (8 test cases, brute-force completeness verified)
- splr 0.13 accepts a seed via `Config` for deterministic solves — if not, the seed requirement is dropped and SC4 is adjusted
- Bottleneck demand/capacity ratios are available from Stage 2's `BottleneckAnalysis` — this data is already computed by the pipeline
- The experiment script imports only what it needs (constraint model types + Rust crate) — it does not import the full pipeline
