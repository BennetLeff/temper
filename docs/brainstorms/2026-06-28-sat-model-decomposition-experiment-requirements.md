---
date: 2026-06-28
topic: sat-model-decomposition-experiment
---

# SAT Model Decomposition — Scientific Experiment

## Summary

A gated experiment testing two strategies to reduce the SAT model from 130K variables to a size splr can solve. Strategy A: route only the hardest nets via SAT, route the rest via A\*. Strategy B: per-bottleneck-channel SAT, one model per congested channel. A is implemented and measured first (simplest change); B only if A fails.

---

## Problem Frame

The Temper PCB constraint model has ~130K variables and 5,903 constraints. Every channel with N candidate nets (N = number of nets that could route through the channel) adds O(N·K) auxiliary variables where K = channel capacity in nets — the exponential expansion. The only way to bound this is to reduce N: fewer candidate nets per SAT instance. Decomposition attacks N directly.

---

## Actors

- A1. **Developer** — runs the experiment, measures per-strategy model size and completion rate
- A2 is removed — the constraint audit is a control, not an actor

---

## Strategy A: Hardest-Nets-First SAT

### Mechanism

1. Score every net by routing difficulty: `score = pin_count + span_area_mm² + bottleneck_channels_touched`, equal weights. Higher = harder.
2. Sort nets by score descending.
3. **Baseline measurement first**: route all 23 nets via A\* only (no SAT). Record the A\*-only completion rate. This is the control — SAT must beat it.
4. Encode and solve SAT for only the top `M` nets (`M` starts at 3, increases by 3 each trial).
5. Commit SAT channel assignments for those nets to the occupancy grid.
6. Route remaining nets via A\* on the now-partially-occupied grid.
7. Run 3 independent trials per `M` value (splr is non-deterministic). Use the minimum completion rate across trials as the decision criterion. Use maximum solver time.
8. Measure: clause count, solver time, completion rate at each `M`.

### Experiment design (adaptive)

| Trial | M (SAT nets) | Stop if |
|-------|-------------|---------|
| 1 | 3 | N/A (baseline) |
| 2 | 6 | Completion ≥ 90% AND solver time < 120s |
| 3 | 9 | Completion ≥ 90% AND solver time < 120s |
| n+1 | M+3 | Stop at first M where both criteria pass, or M exceeds net count |

### Success criteria

- SC1. At least one trial produces completion rate ≥ 90% with solver under 120s. **Completion rate** = (nets with all channels legally assigned and zero constraint violations) / (total nets on the board), as a percentage.
- SC2. The winning M is the smallest M that passes SC1 — fewer SAT nets is simpler
- SC3. Constraint audit passes with zero violations for every SAT instance
- SC0. A\*-only baseline is measured and recorded before any SAT trial — all completion-rate improvements are measured relative to this baseline

---

## Strategy B: Per-Bottleneck-Channel SAT

### Mechanism

1. Stage 2's `BottleneckAnalysis` identifies channels where demand > capacity.
2. For each bottleneck channel, build a SAT model containing only the nets that could use that channel (typically 2-8 nets per channel).
3. Solve each model independently. Commit assignments incrementally.
4. Non-bottleneck channels: no SAT — all nets that fit are assigned without cardinality enforcement.
5. Route all nets via A\* using the committed channel assignments.

### Experiment design (adaptive)

Only implemented if strategy A fails to find a passing M. Measure:

| Metric | Measurement |
|--------|-------------|
| Bottleneck channel count | How many of ~6,000 channels are bottlenecked |
| Per-channel model size | Max/median clause count per bottleneck channel |
| Total encoding size | Sum of all per-channel clause counts vs 130K-variable baseline |
| Completion rate | Closure test on Temper PCB |
| Solver time | Sum of all per-channel solve times |

### Success criteria

- SC4. Total encoding size (sum of per-channel clauses) ≤ 50% of baseline
- SC5. Each per-channel model solves within 30s
- SC6. Overall completion rate ≥ 90%

---

## Controls

- Same board: `pcb/temper_agent_optimized.kicad_pcb` for all trials
- Same machine, same Python version, same rustc version
- Constraint audit runs after every SAT solve
- splr 0.13 with `catch_unwind`

---

## Scope Boundaries

- Does not swap the solver backend (splr 0.13 stays)
- Does not change A\* or Stage 2
- Layer-isolated SAT (strategy C) is rejected — multilayer routing requires cross-layer SAT for THT components
- The winning strategy is the simplest one that passes its criteria. If both fail, the experiment records negative evidence (constraints on SAT viability for 130K+ variable PCB models) and recommends solver-backend comparison as follow-up.

---

## Key Decisions

- **A first, B only if A fails.** Strategy A is a 20-line net-sorting change. Strategy B requires per-channel model construction. Run the simpler one first.
- **Completion rate is the regression gate.** A\* handles nets without SAT assignments — if completion is high, SAT is only needed for a few hard nets. This is the hypothesis A tests.
- **Constraint audit for every SAT instance.** No silent wrong answers, even in decomposed mode.

---

## Dependencies / Assumptions

- Stage 2's `BottleneckAnalysis` correctly identifies congested channels — this data is already computed
- The constraint audit (`audit.rs`) is proven correct (8 test cases, brute-force verified)
- The pipeline imports cleanly without JAX (verified on main)
