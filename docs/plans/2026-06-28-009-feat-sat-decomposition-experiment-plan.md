---
title: "feat: Gated experiment — SAT model decomposition for Temper PCB scale"
type: feat
status: active
date: 2026-06-28
origin: docs/brainstorms/2026-06-28-sat-model-decomposition-experiment-requirements.md
---

# SAT Model Decomposition Experiment

## Summary

A gated, adaptive experiment testing whether routing only the hardest N nets via SAT (and the rest via A\*) produces acceptable completion rates. Strategy A (hardest-nets-first) is implemented and measured first with increasing SAT-net counts. Strategy B (per-bottleneck-channel SAT) runs only if A fails to find a viable SAT-net count.

---

## Problem Frame

The Temper PCB constraint model has ~130K variables. Every channel with N candidate nets adds O(N·K) auxiliary variables. Decomposition reduces N by limiting how many nets enter SAT. The hypothesis: only a few hard nets (SPI lines, PWM traces, high-current paths) actually need SAT-constrained routing — the rest route fine via A\* alone.

(see origin: `docs/brainstorms/2026-06-28-sat-model-decomposition-experiment-requirements.md`)

---

## Requirements

- R1. A\*-only baseline: route all nets via A\* with no SAT, record completion rate
- R2. Net scoring: `score = pin_count + span_area_mm² + bottleneck_channels_touched`, equal weights
- R3. Selective SAT encoding: build SAT model for only the top M nets by score
- R4. Gated adaptive experiment: measure M=3,6,9,... up to net count, stopping at first M where completion ≥ 90% AND solver < 120s (minimum completion across 3 trials)
- R5. If no M passes, implement Strategy B: per-bottleneck-channel SAT models
- R6. Constraint audit passes with zero violations for every SAT instance
- R7. Both-fail outcome documented: record negative evidence, recommend solver-backend comparison

**Origin actors:** A1 (Developer)
**Origin acceptance examples:** defined in origin document

---

## Scope Boundaries

- Does not swap the solver backend (splr 0.13 stays)
- Does not change A\* or Stage 2 (unless A\* partial-occupancy verification requires minor modifications)
- Layer-isolated SAT rejected — multilayer routing requires cross-layer SAT

### Deferred to Follow-Up Work

- Solver-backend comparison (varisat, cadical-rs) if both strategies fail

---

## Context & Research

### Relevant Code and Patterns

- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — `_run_stage3` where SAT model is built and solved
- `packages/temper-rust-router/src/encoding.rs` — `encode_to_cnf_with()`, the encoding entry point
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` — `ModelBuilder` builds the constraint model from Stage 2 output
- `packages/temper-placer/src/temper_placer/router_v6/routing_demand.py` — per-channel demand/capacity ratios for bottleneck identification
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` — A\* pathfinding, must accept pre-populated occupancy grid

### Institutional Learnings

- splr 0.13 cannot solve the full 130K-variable Temper PCB model within any reasonable timeout (verified)
- Bottleneck pruning is already implemented — channels where demand ≤ capacity skip AtMostK entirely
- The constraint audit (`audit.rs`) is proven correct (8 test cases, brute-force verified)

---

## Key Technical Decisions

- **A\* baseline first.** Without measuring A\*-only completion, the experiment cannot attribute routing success to SAT. If A\* alone hits 90%, the SAT solver adds no value for this board.
- **Three trials with minimum completion deciding.** splr is non-deterministic. A single passing trial could be a lucky seed. Minimum completion across 3 trials prevents false conclusions.
- **Strategy B requires per-channel model construction — acknowledged as architecturally significant.** The plan treats this as a fallback, not a minor variant.

---

## Implementation Units

### U1. Run A\*-only baseline measurement

**Goal:** Measure completion rate with zero SAT — A\* handles all routing. This is the control.

**Requirements:** R1, SC0

**Dependencies:** None

**Files:**
- None (measurement only)

**Approach:**
- Route the Temper PCB with `RouterV6Pipeline(skip_stage3=True)` — this bypasses SAT entirely.
- Stage 4 falls back to direct A\* on every net (existing `skip_stage3` behavior).
- Record completion rate, DRC pass rate, and wall time.
- This establishes the baseline: SAT must improve upon this.

**Test scenarios:**
- Happy path: Pipeline completes with skip_stage3=True, returns completion metrics
- Integration: Same board, same machine as the SAT trials — ensures comparability

**Verification:**
- A\*-only completion rate recorded in `metrics/sat_decomposition_baseline.json`

---

### U2. Implement net scoring and selective SAT encoding limit

**Goal:** Score nets by routing difficulty and build SAT models for only the top M nets.

**Requirements:** R2, R3

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-rust-router/src/encoding.rs`
- Modify: `packages/temper-rust-router/src/lib.rs`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`

**Approach:**
- Add `max_sat_nets: Option<usize>` parameter to `solve_topology_rust`. When set, only the top M nets (by occurrence order in the constraint model) are encoded — the remaining nets' channel variables are skipped.
- Net scoring function: `score = pin_count + span_area_mm² + bottleneck_channels_touched`. Computed in Python before passing to Rust.
- Sort nets by score, truncate the constraint model to top M nets before calling `solve_topology_rust`.
- The Rust solver encodes only those nets. A\* handles the rest via the existing `skip_stage3` fallback path.

**Test scenarios:**
- Happy path: M=3 produces a SAT model with fewer variables than the full 130K model
- Happy path: M=23 (all nets) produces the same model as baseline
- Edge case: M=0 — no SAT, equivalent to skip_stage3
- Edge case: M exceeds net count — clamped to total net count

**Verification:**
- `solve_topology_rust(..., max_sat_nets=3)` returns `num_vars` significantly smaller than full model
- Constraint audit passes for the partial model

---

### U3. Implement gated adaptive experiment script

**Goal:** A script that runs the M=3,6,9,... sequence with 3 trials each, stopping at the first passing M.

**Requirements:** R4, R6

**Dependencies:** U1, U2

**Files:**
- Create: `scripts/experiment_sat_decomposition.py`

**Approach:**
- Takes `pcb_path` as argument.
- Runs A\*-only baseline (U1) first, records result.
- For M = 3, 6, 9, ..., up to total net count:
  1. Score and sort nets. Select top M.
  2. Run `solve_topology_rust` with `max_sat_nets=M`.
  3. Run Stage 4 with SAT + A\* fallback.
  4. Run constraint audit after SAT solve.
  5. Repeat 3 times — record minimum completion and maximum solver time across trials.
  6. If min completion ≥ 90% AND max solver < 120s: stop, M is the winner.
  7. If M exceeds net count without passing: proceed to U4 (Strategy B).
- Write JSON report to `metrics/sat_decomposition_experiment.json`.

**Test scenarios:**
- Happy path: A trial at M=6 passes both criteria → stops, writes JSON with M=6 winner
- Happy path: No trial passes → writes JSON with failure data, recommends next step
- Error path: Constraint audit violation → trial marked FAILED, affected M recorded

**Verification:**
- `python scripts/experiment_sat_decomposition.py pcb/temper_agent_optimized.kicad_pcb` — produces valid JSON

---

### U4. (Conditional) Implement Strategy B: per-bottleneck-channel SAT

**Goal:** Build independent SAT models per bottleneck channel if Strategy A fails.

**Requirements:** R5

**Dependencies:** U3 (only if U3 reports failure)

**Files:**
- Modify: `packages/temper-rust-router/src/encoding.rs`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`

**Approach:**
- Module Stub: Document the approach, create scaffolding, but do not implement the full per-channel solver unless U3 confirms A cannot find a passing M. This avoids building a significant architectural feature that may never be used.
- When implemented: for each bottleneck channel (demand/capacity > 1.0), build a SAT model containing only nets that could use that channel. Solve independently. Commit assignments incrementally. Process channels in descending order of congestion. If a later channel's model becomes unsatisfiable due to prior commitments, record the conflict and skip that channel (fallback to A\*).

**Test scenarios:**
- Stub test: `pytest -k "strategy_b_stub"` confirms the module exists but is flagged as conditional
- Full test: defined when Strategy B is activated

**Verification:**
- If Strategy B is not needed, the stub serves as documentation of the decision

---

### U5. Document experiment results and decision

**Goal:** Record the experiment outcome, clean up any feature flags, and commit the winning configuration (or document the negative result).

**Requirements:** R7

**Dependencies:** U3 (or U4 if Strategy B ran)

**Files:**
- Create: `metrics/sat_decomposition_experiment.json`
- Modify: `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` (add scale-limitation note)

**Approach:**
- If Strategy A found a winning M: commit the selective-encoding change as permanent. Remove the `max_sat_nets` flag — it becomes the default behavior with M as the winning value.
- If Strategy B succeeded: commit per-channel SAT as the permanent path.
- If both failed: update the compound doc with the scale limitation finding, add a deferred recommendation for solver-backend comparison.

**Test scenarios:**
- Test expectation: none — documentation only

**Verification:**
- Experiment JSON is committed and valid
- If a winner was found, the winning encoding is the default (no feature flag)

---

## System-Wide Impact

- **Pipeline.** `_run_stage3` gains a `max_sat_nets` parameter. When set, only the top M nets enter SAT. Stage 4's A\* fallback handles remaining nets.
- **Encoding.** Selective encoding is implemented as a net-count cap — nets beyond M are excluded from the SAT model.
- **No A\* changes** required if A\* already accepts a pre-populated occupancy grid. If not, minor A\* modifications are needed (verify in U1).

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| A\* cannot route through a partially-occupied grid | Verified in U1 — if A\* requires a clean grid, add pre-population support |
| Net scoring heuristic ranks nets incorrectly (hard nets scored low) | Manual inspection of top-5 nets for the Temper PCB before running the experiment |
| Strategy B shared-net conflicts across per-channel models | Process channels in congestion order; skip conflicting assignments, fall back to A\* |
| splr non-determinism produces false passing trials | 3 trials per M, minimum completion across trials decides |

---

## Sources & References

- **Origin document:** `docs/brainstorms/2026-06-28-sat-model-decomposition-experiment-requirements.md`
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — SAT model construction and Stage 4 fallback
- `packages/temper-rust-router/src/encoding.rs` — `encode_to_cnf_with()`
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` — A\* pathfinding
