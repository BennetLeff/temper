# Requirements: Routability Gradient Signal for Differentiable Placement↔SAT Co-Optimization

**Date:** 2026-06-28
**Status:** Draft
**Owner:** TBD
**Plan ID:** TBD

## 1. Overview

### 1.1 Problem Statement

The placement optimizer (JAX gradient descent) and the routing SAT solver (splr CDCL, accessed via `temper-rust-router`) communicate at most once per iteration through a binary "did it route?" signal (`SolverStatus::SATISFIABLE` / `UNSATISFIABLE`). When the SAT solver returns UNSAT, the placement optimizer receives zero gradient information about _why_ the topology is unsolvable or _which_ nets are the bottleneck. The entire outer-loop iteration is wasted—placement restarts from a perturbed initial guess with no directional guidance.

The creepage lesson (`docs/solutions/performance-issues/2026-06-23-pcb-autorouter-completion-rate-47x-speedup.md`) demonstrated that un-routable placements waste entire optimization cycles: gaps smaller than 6 mm HV creepage caused 10 of 24 nets to be structurally unroutable, yet the placer had no signal to move components apart.

### 1.2 Proposed Solution

Extract solver-internal CDCL statistics (backtrack count per net-type, clause-learning activity per constraint family, decision-level distribution, UNSAT core size) as a continuous _routability signal_. Feed this back to JAX placement as a differentiable penalty term using a straight-through estimator (STE). The placement optimizer learns to produce layouts the SAT solver finds easy—not just layouts with short wirelengths.

### 1.3 Scope

| In Scope | Out of Scope |
|---|---|
| Expose solver statistics from splr (`solver.rs`) | Modifying the core CDCL algorithm in splr |
| Aggregate per-net routability scores from solver statistics | Per-pin routability signal (net-level aggregation is the first step) |
| Implement a JAX-compatible `RoutabilityGradientLoss` using STE | Replacing the existing `RoutingFeedbackLoss` (maze-router congestion) |
| Integrate into the refinement loop (`orchestrator.py:_run_refinement`) | Real-time solver statistics streaming (batch-per-iteration is sufficient) |
| UNSAT fallback: extract UNSAT core and produce a penalty gradient | Multi-solver backends (only splr CDCL is targeted) |
| Convergence guard: decay routability weight as routing success improves | Full PathFinder-style negotiation (the SAT solver is called once per iteration) |

## 2. Functional Requirements

### FR1: Solver Statistics Exposure (Rust Side)

**FR1.1 — Backtrack Count by Net-Type.**
The `TopologyResult` struct (`types.rs:348`) shall be extended with, if available from splr's public API:
- `backtrack_count: u64` — total number of conflict-driven backtracks during CDCL solving.
- `backtrack_by_net_type: HashMap<NetType, u64>` where `NetType` is an enum (`HV`, `Power`, `Signal`, `LV`) derived from the constraint model variable classification.

This requires exposing internal CDCL counters that splr already maintains internally. If splr 0.13's public API does not expose these, the `solve_with_splr` function shall be restructured to use splr's `Solver` struct directly (the `SatSolverIF` trait or lower-level API) rather than the black-box `solve()` call.

**FR1.2 — Clause-Learning Activity by Constraint Family.**
The result shall include, if available from splr's public API, `clause_activity: HashMap<ConstraintFamily, f64>` where `ConstraintFamily` is one of:
- `Capacity` — AtMostK cardinality constraints on channel capacity.
- `DiffPair` — equality constraints for differential pairs.
- `LayerRestriction` — unit clauses fixing net layer assignments.
- `Other` — any clauses not in the above families.

Activity is the VSIDS (Variable State Independent Decaying Sum) or similar learnt-clause activity score, summed per constraint family. This identifies which constraint type is driving the most conflict.

**FR1.3 — Decision-Level Distribution.**
The result shall include, if available from splr's public API, `decision_level_histogram: [u64; 10]` — a 10-bin histogram of the maximum decision level reached during each conflict. Bins are quantiles (0–10%, 10–20%, ..., 90–100%) of the total variable count. High decision-level conflicts indicate deep contradictions (hard problems).

**FR1.4 — UNSAT Core Size.**
When the solver returns `SolverStatus::Unsatisfiable`, the `unsat_core` field (already declared as `Vec<usize>` in `TopologyResult`) shall be populated with the indices of clauses in the UNSAT core, if available from splr's public API. The size of this core shall be separately reported as `unsat_core_size: usize`.

**FR1.5 — Statistics Passthrough to Python.**
The `solve_topology_rust` PyO3 function (`lib.rs:26`) shall be updated to include the new statistics fields in the returned Python dict under a `"solver_stats"` sub-dict. The `TopologicalSolution` Python dataclass (`topology_solver.py:25`) shall be extended with an optional `solver_stats: dict | None` field.

**FR1.6 — Statistics When SAT.**
When the solver returns SAT, statistics are still collected and returned. SAT statistics represent the _difficulty_ of solving—higher backtrack counts for a SAT instance mean the solver had to work harder, which correlates with a placement that is _marginally_ routable (close to the UNSAT boundary).

**FR1.7 — Coarse Statistics Fallback.**
When fine-grained CDCL statistics (FR1.1-FR1.4) are not available from the solver, the routability signal SHALL fall back to:
- `solver_time_ms` — higher solve time indicates a less routable placement.
- `variable_count * clause_count / solver_time_ms` — a throughput proxy (lower throughput = harder instance).
- `clause_count / variable_count` — clause-to-variable ratio (higher ratio typically correlates with harder instances).

The coarse signal is computed even on SAT results (where solve time reflects difficulty of finding a satisfying assignment).

### FR2: Per-Net Routability Score Aggregation

**FR2.1 — Net-Type Classification.**
Each SAT variable (from `InternalVariable` in `types.rs:265`) shall be classified by net type using the net name to `NetClass` lookup. The `InternalConstraintModel` or the encoder shall annotate each variable with its associated net index. The `CnfFormula` struct (`encoding.rs:9`) shall be extended with a `var_to_net: Vec<usize>` mapping.

**FR2.2 — Per-Net Score Formula.**
For each net $n$, the routability score $r_n \in [0, 1]$ (0 = easy, 1 = impossible) is computed as:

$$r_n = \text{clamp}\left( w_b \cdot \frac{b_n}{B_{\max}} + w_a \cdot \frac{a_n}{A_{\max}} + w_d \cdot \frac{d_n}{D_{\max}} + w_c \cdot \frac{c_n}{C_{\max}}, \ 0, \ 1 \right)$$

Where:
- $b_n$ = backtrack count attributed to clauses involving net $n$'s variables.
- $a_n$ = clause activity sum for constraints involving net $n$.
- $d_n$ = average decision level at which net $n$'s variables were assigned.
- $c_n$ = number of UNSAT core clauses involving net $n$ (SAT case: 0).
- $B_{\max}, A_{\max}, D_{\max}, C_{\max}$ = per-iteration normalization constants (max across all nets).
- $w_b, w_a, w_d, w_c$ = configurable weights (defaults: $w_b=0.3, w_a=0.2, w_d=0.2, w_c=0.3$).

**FR2.3 — UNSAT Case Scoring.**
When the solver returns UNSAT, only the UNSAT core contributes ($w_c=1.0$, all others $0.0$), because CDCL statistics during UNSAT resolution reflect the proof search, not routability difficulty. The UNSAT core directly identifies the irreducible unsatisfiable subset of constraints.

**FR2.4 — Score Aggregation to Placement Signal.**
The per-net routability scores $\{r_n\}$ are mapped back to components: each component $i$ receives a penalty $p_i = \max_{n \in \text{nets}(i)} r_n$ (the worst routability score among nets connected to component $i$). This produces a $(N,)$ vector of per-component penalties.

### FR3: JAX Loss Function with Straight-Through Estimator

**FR3.1 — New Loss Class.**
A new abstract base class `StatefulLossFunction` shall be defined in `losses/base.py`, extending `LossFunction` with two additional abstract methods:
- `blend(state: dict) -> None` — called once per outer refinement iteration before the JAX inner loop, to blend aggregated feedback state (e.g., EWMA congestion or routability scores).
- `compute_loss(positions: Array, rotations: Array, context: LossContext) -> LossResult` — called during JAX optimization, with the blended state baked in.

A new class `RoutabilityGradientLoss(StatefulLossFunction)` shall be created in `losses/routability_gradient.py`, following the existing patterns from `RoutingFeedbackLoss` (`feedback.py:31`) and `SpatialFeedbackLoss` (`spatial_feedback.py:23`). The orchestrator's refinement loop SHALL call `blend()` before each placer invocation.

**FR3.2 — Input Requirements.**
The loss function accepts:
- `positions: (N, 2)` — component positions (differentiable input).
- `routability_scores: (N,)` — per-component penalty vector from FR2.4 (non-differentiable, computed externally by the SAT solver).
- `routability_scores` is passed via the `LossContext` or as a constructor argument to the loss function instance.

**FR3.3 — Straight-Through Estimator.**
The `routability_scores` vector is produced by a non-differentiable process (SAT solving). To backpropagate through this, use the straight-through estimator pattern already established in the codebase:

```python
# Pattern from core/state.py:269 and geometry/transform.py:452
# soft + jax.lax.stop_gradient(hard - soft)

# For routability: the "hard" signal is the actual solver score.
# The "soft" proxy is the wirelength approximation, which is differentiable.
soft_proxy = compute_net_wirelengths(positions, context)  # differentiable
ste_signal = soft_proxy + jax.lax.stop_gradient(routability_scores - soft_proxy)
```

See FR3.5 for `compute_net_wirelengths`.

**FR3.4 — Loss Value Computation.**
The loss value is computed as:

$$L_{\text{rout}} = \sum_{i=1}^{N} \text{ste\_signal}_i \cdot d_i(\text{positions})$$

Where $d_i$ is the _distance moved from anchor_ for component $i$ (anchor = position at start of refinement iteration). This penalizes components with high routability scores but _only_ if they move—components can stay put at zero cost. A component with $r_i=0$ (easy to route) incurs no penalty regardless of movement.

**FR3.5 — Soft Proxy Function.**
The differentiable proxy `compute_net_wirelengths(positions, context)` computes, for each component, the sum of HPWL (half-perimeter wirelength) for all nets incident to that component, normalized to $[0, 1]$ per iteration. This is already computable using `WirelengthLoss` internals (e.g., `_compute_hpwl`). The proxy must be JAX-differentiable, which HPWL is (via `jnp.max` / `jnp.min`).

**FR3.6 — Loss Result.**
Returns `LossResult(value=scalar, breakdown={...})` with breakdown keys:
- `routability_gradient_total`: total loss value.
- `routability_gradient_max`: maximum per-component penalty.
- `routability_gradient_mean`: mean per-component penalty.
- `routability_active_components`: count of components with $r_i > 0$.

### FR4: Integration with Existing Feedback Loop

**FR4.1 — Refinement Loop Entry Point.**
Integration shall occur in `PipelineOrchestrator._run_refinement` (`orchestrator.py:500`), which already composes a `CompositeLoss` with `RoutingFeedbackLoss` (maze congestion) inside `update_fn`. The `RoutabilityGradientLoss` shall be added as an additional weighted term in the `CompositeLoss`:

```python
loss_fn = CompositeLoss([
    WeightedLoss(WirelengthLoss(), weight=1.0),
    WeightedLoss(OverlapLoss(), weight=50.0),
    WeightedLoss(ChannelCapacityLoss(), weight=20.0),
    WeightedLoss(RoutingFeedbackLoss(heatmap), weight=100.0),  # existing
    WeightedLoss(RoutabilityGradientLoss(routability_scores), weight=50.0),  # NEW
])
```

**FR4.2 — Solver Invocation Before Each JAX Step.**
Before each iteration of the refinement loop, the SAT solver must be invoked to produce fresh `routability_scores`. The current refinement loop calls the maze router (`OrchestratorRouter.route()`), which does not invoke the SAT solver. The refinement loop shall be extended to also invoke `solve_topology_rust` and extract statistics.

**FR4.3 — Separate Solver Invocation.**
The SAT topology solver operates on a different abstraction (channel graph) than the maze router (grid graph). Both must be invoked each refinement iteration: the maze router for congestion heatmap (existing), the SAT solver for routability gradient (new). The SAT solver may be called with reduced timeout during refinement iterations (e.g., 500 ms vs. 5 s for the final pass).

**FR4.4 — Weight Scheduling.**
The routability gradient weight SHALL be managed by the orchestrator per outer refinement iteration, not by `WeightedLoss.schedule_start`/`schedule_end` (which operate on inner-loop epoch progress within a single training run). The orchestrator SHALL set `RoutabilityGradientLoss.weight` to 0.0 on iteration 0 (no routability signal yet—first placement is the baseline) and ramp to `target_weight` over the first 2 iterations, then hold constant. If routing success exceeds `routability_threshold` (0.85), the orchestrator shall scale the routability weight down by factor 0.3. Weight management occurs at the outer-loop level, outside of JAX compilation boundaries.

**FR4.5 — Compatibility with MomentumDampedRoutingFeedbackLoss.**
The `MomentumDampedRoutingFeedbackLoss` (`feedback.py:92`) blends congestion across iterations via EWMA. The `RoutabilityGradientLoss` shall maintain independent EWMA state with a similar `blend()`/`compute_loss()` separation pattern, ensuring only one blend per iteration.

### FR5: Convergence Guarantees

**FR5.1 — Weight Decay on Convergence.**
If `routability_score_mean` (mean across nets) decreases for 2 consecutive iterations AND routing completion is above `routability_threshold`, the `RoutabilityGradientLoss` weight is multiplied by 0.5. This prevents the routability term from dominating once the placement is already good.

**FR5.2 — Oscillation Detection.**
If `routability_score_mean` increases (worsens) for 2 consecutive iterations, log a warning and freeze the routability scores at their best-observed values. This mirrors the oscillation-avoidance pattern proposed in `docs/ideation/2026-06-28-sidecar-feedback-convergence-ideation.md` (#2).

**FR5.3 — Monotonic Improvement Tracking.**
The refinement loop already tracks `best_completion` (`iterative_placer.py:82`). Extend this to also track `best_routability_score_mean`. If the current iteration's mean is worse than best, use best scores for the loss computation (pessimistic guard against regression).

**FR5.4 — Maximum Gradient Norm.**
The STE gradient produced by `RoutabilityGradientLoss` shall be clipped to a maximum L2 norm of `max_grad_norm = 1.0` mm per component per iteration, enforced via `jnp.clip` on the position update. This prevents a single bad routability signal from catastrophically displacing components.

### FR6: UNSAT Fallback

**FR6.1 — UNSAT Core Extraction.**
When the SAT solver returns UNSAT, extract the UNSAT core clause indices. Map each core clause back to the constraint family and the net indices involved (via the `var_to_net` mapping from FR2.1).

**FR6.2 — UNSAT Penalty Signal.**
For UNSAT results, set $r_n = 1.0$ for every net that appears in the UNSAT core, $r_n = 0.0$ otherwise (all-or-nothing core signal). The weight $w_c$ is set to 1.0 (FR2.3).

**FR6.3 — Maximum Movement Budget for UNSAT.**
When the solver returns UNSAT, the `max_movement_mm` for the subsequent JAX step is doubled (from the config default of 2.0 mm to 4.0 mm), because UNSAT indicates the current placement is structurally unsolvable and requires larger repositioning. This override applies only for the iteration immediately following an UNSAT result.

**FR6.4 — UNSAT Persistence Escape.**
If UNSAT persists for 3 consecutive iterations, fall back to the existing `simple_congestion_repel` heuristic (`iterative_placer.py:164`) and log a diagnostic indicating that the SAT solver could not guide convergence within the budget. This prevents infinite loops where gradient-based feedback cannot escape an unsolvable topology.

**FR6.5 — UNSAT Without Core Fallback.**
When the solver returns UNSAT but the UNSAT core is empty (no clause indices available from splr), the routability signal SHALL fall back to a heuristic penalty:
- Identify nets involved in violated constraints via the existing `audit_result` path (`audit.rs:39-129`).
- Assign $r_n = 1.0$ to all such nets (direct violation penalty).
- Assign $r_n = 0.5$ to all other nets in the same channel skeleton as detected-violation nets (propagation penalty — nets sharing a channel are likely also affected).

## 3. Non-Functional Requirements

### NFR1: Performance

- **NFR1.1:** SAT solver statistics collection shall add no more than 5% overhead to the solve time. CDCL internal counters are simple increments—no additional search is required.
- **NFR1.2:** Per-net score aggregation (FR2) shall complete in O(V + C) time where V = number of variables, C = number of clauses.
- **NFR1.3:** The STE JAX loss computation shall be compatible with `@jax.jit` compilation and shall not introduce Python callbacks that break JIT boundaries.
- **NFR1.4:** The refinement loop's SAT solver invocation (FR4.3) may use a shorter timeout (default: 500 ms) to keep iteration latency bounded.

### NFR2: Correctness

- **NFR2.1:** The STE gradient shall be mathematically consistent: `jax.grad` of the loss with respect to `positions` shall produce finite, non-NaN gradients for all inputs, even when `routability_scores` are all zeros or all ones.
- **NFR2.2:** The UNSAT core extraction shall be validated against the existing `audit_result` functionality (`audit.rs`) to ensure core clauses correspond to actual constraint violations.
- **NFR2.3:** The routability loss shall be zero when `routability_scores` are all zero (no penalty for already-routable placements).
- **NFR2.4:** Fixed components (e.g., connectors, mounting holes) defined by the `fixed_mask` in `LossContext` shall have zero routability gradient (already handled by `create_value_and_grad_fn` in `base.py:1218`).

### NFR3: Observability

- **NFR3.1:** Each refinement iteration shall log: per-net routability scores (top 5 worst nets), total routability loss, STE gradient norm, and whether SAT returned SAT or UNSAT.
- **NFR3.2:** The `IterationResult` dataclass (`iterative_placer.py:26`) shall be extended with `routability_score_mean: float` and `unsat_core_size: int`.
- **NFR3.3:** The `PlaceRouteResult` dataclass (`iterative_placer.py:38`) shall include a `routability_history: list[float]` tracking per-iteration mean routability scores.

### NFR4: Configurability

All routability gradient hyperparameters shall be configurable via `PipelineConfig` (`orchestrator.py:66`):
- `routability_gradient_weight: float = 50.0` — base weight in `CompositeLoss`.
- `routability_gradient_max_grad_norm: float = 1.0` — max L2 norm per component (FR5.4).
- `routability_gradient_unsat_movement_multiplier: float = 2.0` — movement budget multiplier on UNSAT (FR6.3).
- `routability_gradient_sat_timeout_ms: float = 500.0` — SAT timeout during refinement (FR4.3).
- `routability_gradient_unsat_escape_iterations: int = 3` — UNSAT persistence threshold (FR6.4).

## 4. Architecture

### 4.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Refinement Loop (orchestrator.py)             │
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────────┐  │
│  │ Maze     │    │ SAT Topology │    │ JAX Optimizer         │  │
│  │ Router   │───▶│ Solver       │───▶│ (CompositeLoss)       │  │
│  │          │    │ (splr CDCL)  │    │                       │  │
│  │ Produces:│    │ Produces:    │    │ Consumes:             │  │
│  │ heatmap  │    │ stats + core │    │ heatmap + scores      │  │
│  └──────────┘    └──────────────┘    └───────────┬───────────┘  │
│                                                   │              │
│                                          ┌────────▼───────────┐  │
│                                          │ RoutabilityGradient │  │
│                                          │ Loss (STE)          │  │
│                                          └────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Data Flow (per refinement iteration)

```
1. positions_n ──▶ MazeRouter ──▶ CongestionHeatmap
2. positions_n ──▶ ConstraintModelBuilder ──▶ SAT Model
3. SAT Model ──▶ splr CDCL ──▶ TopologyResult (with stats)
4. TopologyResult.stats ──▶ RoutabilityAggregator ──▶ routability_scores (N,)
5. heatmap + positions_n + routability_scores ──▶ JAX optimizer step
6. positions_{n+1} ◀── optax update
```

### 4.3 File Layout

| File | Purpose |
|---|---|
| `packages/temper-rust-router/src/solver.rs` | Extend with statistics collection (FR1) |
| `packages/temper-rust-router/src/solver_stats.rs` | **New:** statistics aggregation and serialization |
| `packages/temper-rust-router/src/types.rs` | Extend `TopologyResult` with stats fields |
| `packages/temper-rust-router/src/encoding.rs` | Add `var_to_net` mapping (FR2.1) |
| `packages/temper-placer/src/temper_placer/router_v6/routability_aggregator.py` | **New:** per-net score computation from solver stats (FR2) |
| `packages/temper-placer/src/temper_placer/losses/routability_gradient.py` | **New:** STE loss function (FR3) |
| `packages/temper-placer/src/temper_placer/pipeline/orchestrator.py` | Integrate into `_run_refinement` (FR4) |
| `packages/temper-placer/src/temper_placer/pipeline/iterative_placer.py` | Extend result dataclasses (NFR3) |

## 5. Risks and Open Questions

### Risk 1: splr API Limitations

splr 0.13's public API (the `SolveIF` trait and `Certificate` enum) may not expose internal CDCL statistics (backtrack count, clause activity, decision levels). The `Solver` struct likely holds these internally but splr's public interface is designed for black-box usage.

**Mitigation:** If splr does not expose these statistics:
1. Fork splr with a small patch to expose internal counters via accessor methods on `Solver`.
2. Alternatively, wrap splr's `Solver` to intercept CDCL callbacks if splr provides a hook mechanism.
3. As a fallback, use the `solver_time_ms` and clause/variable counts as coarse statistics. The UNSAT core is the highest-value signal and can be computed via MUS extraction on the CNF formula independently.

### Risk 2: STE Gradient Quality

The straight-through estimator replaces the true gradient $\frac{\partial L}{\partial r} \cdot \frac{\partial r}{\partial \text{positions}}$ with $\frac{\partial L}{\partial \text{proxy}}$ where proxy is HPWL. If HPWL correlates poorly with routability difficulty in some regions, the STE gradient may point in a useless direction.

**Mitigation:** The existing `RoutingFeedbackLoss` (maze-router congestion, `feedback.py:31`) provides a complementary gradient signal. The routability gradient is additive, not a replacement. `SpatialFeedbackLoss` (`spatial_feedback.py:23`) exists but is not currently wired into the refinement loop—it could be added as future work. The combined multi-term loss provides gradient redundancy.

### Risk 3: UNSAT Core Accuracy

splr's UNSAT certificate (`Certificate::UNSAT`) may not carry the UNSAT core. Computing a minimal UNSAT core (MUS) is NP-hard. A non-minimal core (all clauses in the UNSAT proof) is cheap to extract but may be large and uninformative.

**Mitigation:** If splr cannot produce an UNSAT core, use the `audit_result` function (`audit.rs`) to identify which constraints are violated by a partial assignment (greedy assignment of as many variables as possible). This is a heuristic but provides a useful subset of "likely culpable" nets.

### Open Question 1: SAT Solver Granularity

Should the SAT solver be invoked on a per-net basis (one SAT call per net) or globally (one SAT call for all nets)? The current architecture invokes the SAT solver globally on all nets simultaneously. Per-net invocation would provide finer-grained routability scores but would be O(N) more expensive.

**Recommendation:** Start with global invocation. Per-net invocation can be explored as an optimization if the global signal is too coarse.

### Open Question 2: STE Proxy Choice

Should the differentiable proxy be HPWL (simple, already implemented) or a learned proxy (e.g., a small neural network predicting routability from positions)? The existing `WirelengthLoss` (`losses/wirelength.py`) provides HPWL. A learned proxy would require training data that does not currently exist.

**Recommendation:** Start with HPWL. A learned proxy is deferred and tracked as a separate feature request.

### Open Question 3: splr Statistics API (Deferred to Planning)

Which splr internal statistics are actually extractable through the public API without source patches? This must be determined via a spike before FR1.1-FR1.4 can be finalized. The coarse-statistics fallback (FR1.7) provides a workable path regardless of the outcome, but the fine-grained signal quality depends on API access.

## 6. Acceptance Criteria

1. **AC1:** `solve_topology_rust` returns a `solver_stats` dict containing at minimum `backtrack_count`, `decision_level_histogram`, and `unsat_core_size`.
2. **AC2:** `RoutabilityGradientLoss` computes a scalar loss value within `@jax.jit` that is differentiable with respect to `positions`.
3. **AC3:** The loss gradient is non-zero for components connected to nets with high routability scores, and zero for components with routability score = 0.
4. **AC4:** A refinement loop iteration that produces UNSAT results in larger position updates than a SAT iteration (demonstrated via test fixture with a known-unsolvable placement).
5. **AC5:** After 3 consecutive UNSAT iterations, the refinement loop falls back to `simple_congestion_repel` and logs a diagnostic.
6. **AC6:** No regression in routing completion rate on existing test boards (Piantor, LibreSolar, RP2040, BitAxe) compared to baseline.
7. **AC7:** New unit tests in `tests/losses/test_routability_gradient.py` covering: zero signal → zero loss, STE gradient correctness, UNSAT fallback path.
8. **AC8:** New integration test in `tests/router_v6/test_stage3_routability_feedback.py` verifying end-to-end flow from SAT solver → statistics → loss → gradient → position update.

## 7. References

- `packages/temper-placer/src/temper_placer/pipeline/feedback.py`: Existing `RoutingFeedbackLoss` and `MomentumDampedRoutingFeedbackLoss` (maze-router congestion feedback pattern).
- `packages/temper-placer/src/temper_placer/pipeline/iterative_placer.py`: Outer refinement loop with congestion repel.
- `packages/temper-placer/src/temper_placer/pipeline/orchestrator.py`: `_run_refinement` integrating placement + routing.
- `packages/temper-rust-router/src/solver.rs`: Current splr integration (black-box `solve()` call).
- `packages/temper-rust-router/src/types.rs:348`: `TopologyResult` struct with `unsat_core` field (unpopulated).
- `packages/temper-placer/src/temper_placer/core/state.py:234-269`: Straight-through estimator pattern for Gumbel-Softmax.
- `packages/temper-placer/src/temper_placer/geometry/transform.py:434-452`: STE documentation and implementation.
- `packages/temper-placer/src/temper_placer/losses/spatial_feedback.py`: `SpatialFeedbackLoss` pattern for external-feedback-as-loss.
- `docs/ideation/2026-06-28-sidecar-feedback-convergence-ideation.md`: Convergent feedback loop design.
- `docs/solutions/performance-issues/2026-06-23-pcb-autorouter-completion-rate-47x-speedup.md`: Creepage lesson — unroutable placements waste cycles.
- `packages/temper-placer/src/temper_placer/losses/base.py:753-807`: `LossFunction` ABC interface.
- `packages/temper-placer/src/temper_placer/losses/base.py:914-1022`: `CompositeLoss` aggregation pattern.
