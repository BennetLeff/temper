---
title: "feat: Routability Gradient Signal for Differentiable Placement↔SAT Co-Optimization"
type: feat
status: active
date: 2026-06-28
origin: docs/brainstorms/2026-06-28-routability-gradient-signal-requirements.md
---

# Routability Gradient Signal

## Summary

Extract solver-internal CDCL statistics (backtrack count, clause activity, decision-level histogram, UNSAT core size) from the CaDiCaL SAT solver via rustsat traits as a continuous _routability signal_. Feed this back to JAX placement as a differentiable penalty term using a straight-through estimator (STE) within a new `StatefulLossFunction` ABC that separates `blend()` (called once per refinement iteration) from `compute_loss()` (called during JAX inner-loop optimization). The placement optimizer learns to produce layouts the SAT solver finds easy, not just layouts with short wirelengths.

---

## Problem Frame

The placement optimizer (JAX gradient descent) and the routing SAT solver communicate at most once per iteration through a binary "did it route?" signal (`SolverStatus::SAT` / `UNSAT`). When the SAT solver returns UNSAT, the placement optimizer receives zero gradient information about _why_ the topology is unsolvable or _which_ nets are the bottleneck. The entire outer-loop iteration is wasted—placement restarts with no directional guidance.

The existing refinement loop (`refinement_stage.py:14`) composes a `CompositeLoss` with maze-router congestion feedback (`RoutingFeedbackLoss`) but has no SAT-derived routability term. The SAT topology solver operates on a different abstraction (channel graph) than the maze router (grid graph), and its per-variable conflict statistics carry structural information about _which nets_ make the constraint model hard to satisfy.

## Codebase State (Pre-Implementation)

| Element | Current state |
|---|---|
| SAT solver | `rustsat-cadical` via `solve_with_cadical()` in `solver.rs:20`. CaDiCaL exposes `conflicts()`, `decisions()`, `propagations()` via `GetInternalStats` trait, plus `SolveStats` with `cpu_solve_time()`, `n_clauses()`, `n_vars()`. **Not currently collected.** |
| UNSAT cores | `solve_with_cadical_cores()` in `solver.rs:123` already extracts core clause indices via selector-literal assumptions and `solver.core()`. **Working.** |
| `TopologyResult` | `types.rs:348` — fields: `status`, `num_vars`, `num_clauses`, `assignments`, `unsat_core: Vec<usize>`, `solver_time_ms`. **No CDCL stats fields.** |
| `CnfFormula` | `encoding.rs:9` — fields: `num_vars`, `clauses`, `var_names`. **No `var_to_net` mapping.** |
| `InternalVariable` | `types.rs:265` — all 4 variants carry `net_idx: usize`. **Ready for `var_to_net` mapping.** |
| `InternalConstraint` | `types.rs:290` — `Capacity`, `DiffPair`, `LayerRestriction`. **Maps 1:1 to ConstraintFamily in FR1.2.** |
| PyO3 entry | `lib.rs:26` `solve_topology_rust()` returns a plain `PyDict` with `status`, `assignments`, `topology_graph`, `solver_time_ms`, `num_vars`, `num_clauses`, `unsat_core`. **No `solver_stats` sub-dict.** |
| `TopologicalSolution` | `topology_solver.py:25` — dataclass with `status`, `assignment`, `solver_time_ms`. **No `solver_stats` field.** |
| STE pattern | `core/state.py:269` — `soft + jax.lax.stop_gradient(hard - soft)` for Gumbel-Softmax. **Established in codebase.** |
| `MomentumDampedRoutingFeedbackLoss` | `feedback.py:92` — EWMA blend/compute_loss separation pattern. **Ready to replicate for routability.** |
| `LossFunction` ABC | `losses/base.py:753` — `name` property + `__call__(positions, rotations, context, ...)`. **No `StatefulLossFunction` subclass yet.** |
| Refinement loop | `refinement_stage.py:74` `update_fn()` builds `CompositeLoss` with `WirelengthLoss`, `OverlapLoss`, `ChannelCapacityLoss`, `RoutingFeedbackLoss`. **No routability term.** |
| UNSAT fallback | `simple_congestion_repel()` at `iterative_placer.py:164`. **Only called by legacy `_run_refinement`; not wired in `RefinementStage`.** |
| `IterationResult` | `iterative_placer.py:26` — fields: `iteration`, `completion_rate`, `nets_routed`, `nets_failed`, `total_congestion`, `hotspot_count`, `placement_changed`. **No routability fields.** |
| `PipelineConfig` | `orchestrator.py:66` — has `max_movement_mm`, `routability_threshold`. **No routability-gradient hyperparameters.** |

## Scope Boundaries

**In scope:**
- Rust: extend `TopologyResult` with CDCL stats, add `var_to_net` mapping in `CnfFormula`, wire `GetInternalStats`/`SolveStats` into `solve_with_cadical`, pass stats through PyO3
- Python: `TopologicalSolution.solver_stats` field, new `routability_aggregator.py` for per-net scoring, new `StatefulLossFunction` ABC + `RoutabilityGradientLoss`, integration into `RefinementStage`
- STE loss: HPWL proxy (differentiable), straight-through estimator pattern from `state.py:269`, JAX-jittable, gradient clipping
- Convergence: weight decay on improvement, oscillation detection via score history, monotonic best-score tracking, UNSAT persistence escape
- Config: new `PipelineConfig` fields for all routability-gradient hyperparameters
- Tests: unit tests for loss, integration test for end-to-end flow

**Out of scope:**
- Modifying the core CaDiCaL/CDCL algorithm — we read stats, not alter solver behavior
- Per-pin routability signal (net-level aggregation only)
- Replacing `RoutingFeedbackLoss` (maze-router congestion) — additive, not replacement
- Multi-solver backends (only CaDiCaL via rustsat is targeted)
- Real-time solver statistics streaming (batch-per-iteration is sufficient)
- Full negotiation-style iterative SAT (one SAT call per refinement iteration)

## Requirements Mapping

This plan covers all functional requirements (FR1–FR6) and non-functional requirements (NFR1–NFR4) from the origin brainstorms document, organized into implementation units below.

---

## Implementation Units

### U1. Rust: Solver Statistics Collection and Var-to-Net Mapping

**Goal**: Extend `TopologyResult` with CDCL statistics from CaDiCaL via rustsat traits, add `var_to_net` mapping to `CnfFormula`, serialize both through the PyO3 boundary.

**Requirements**: FR1.1–FR1.7, FR2.1

**Dependencies**: None

**Files**:
- **Modify**: `packages/temper-rust-router/src/types.rs` — add stats fields to `TopologyResult`, add `var_to_net` to `CnfFormula`
- **Modify**: `packages/temper-rust-router/src/encoding.rs` — populate `var_to_net` during CNF encoding
- **Modify**: `packages/temper-rust-router/src/solver.rs` — collect CDCL stats from CaDiCaL via `GetInternalStats`/`SolveStats` traits; implement coarse-stats fallback
- **Modify**: `packages/temper-rust-router/src/lib.rs` — serialize stats into `"solver_stats"` sub-dict in `solve_topology_rust` return value
- **Create**: `packages/temper-rust-router/src/solver_stats.rs` — **New**: statistics data structures and aggregation logic

**Approach**:

1. **Extend `CnfFormula`** (`encoding.rs:9`):
   - Add field: `pub var_to_net: Vec<usize>` — same length as `num_vars`, maps variable index → net index.
   - Populate during `encode_to_cnf()`: when adding each variable to `var_map`, record its `net_idx` from `InternalVariable` in `var_to_net`.

2. **Define Rust-side stats types** (`solver_stats.rs`, new file):
   ```rust
   pub struct SolverStats {
       pub conflicts: u64,
       pub decisions: u64,
       pub propagations: u64,
       pub decision_level_histogram: [u64; 10], // quantile bins
       pub unsat_core_size: usize,
       // Coarse fallback (always populated):
       pub variable_count: u64,
       pub clause_count: u64,
       pub cpu_solve_time_ms: f64,
   }
   ```

3. **Collect stats from CaDiCaL** (`solver.rs`):
   - After `solver.solve()` returns, call:
     - `solver.conflicts()` → `u64` (via `GetInternalStats` trait on `CaDiCaL`)
     - `solver.decisions()` → `u64`
     - `solver.propagations()` → `u64`
   - From `SolveStats`: `cpu_solve_time()`, `n_clauses()`, `n_vars()`
   - Build `decision_level_histogram` from solved assignments: for each variable, record its decision level (available from `CaDiCaL`'s internal solver state if the trait exposes it; otherwise use quantile bucketing of `decisions / conflicts` ratio as a proxy for complexity depth).
   - **Risk**: `GetInternalStats` trait availability in `rustsat-cadical` 0.7.5 must be verified via a quick spike. If `conflicts()`/`decisions()`/`propagations()` are not exposed, fall back to coarse stats only (FR1.7).
   - `unsat_core_size` = `result.unsat_core.len()` (already available).

4. **Extend `TopologyResult`** (`types.rs:348`):
   - Add field: `pub solver_stats: Option<SolverStats>`.
   - `empty_result()` sets `solver_stats: None`.
   - Both `solve_with_cadical()` and `solve_with_cadical_cores()` populate stats on successful solve.

5. **Coarse statistics fallback** (`solver.rs`, in `solve_with_cadical`):
   - Even when fine-grained CDCL stats are unavailable:
     - `variable_count = cnf.num_vars`
     - `clause_count = cnf.clauses.len()`
     - `cpu_solve_time_ms = elapsed`
   - These are always populated into `solver_stats` (maybe as a `SolverStats::coarse(...)` constructor).
   - Compute `clause_to_var_ratio = clause_count / max(variable_count, 1)` and `solve_throughput = variable_count * clause_count / max(cpu_solve_time_ms, 0.001)`.

6. **Serialize to Python** (`lib.rs:26`):
   - Under `d.set_item("solver_stats", py_dict)?`:
     ```python
     solver_stats = {
         "conflicts": int,      # or None if unavailable
         "decisions": int,
         "propagations": int,
         "decision_level_histogram": list[int],  # 10 bins
         "unsat_core_size": int,
         # Coarse (always present):
         "variable_count": int,
         "clause_count": int,
         "cpu_solve_time_ms": float,
         "clause_to_var_ratio": float,
         "solve_throughput": float,
     }
     ```
   - Also serialize the `var_to_net` mapping as a flat list under `"var_to_net"` key for Python-side aggregation.

**Test scenarios**:
- SAT solve on a 3-net 2-channel model: verify `conflicts > 0`, `decisions >= num_vars`
- UNSAT solve: verify `unsat_core_size > 0`, core clause indices valid (all < `num_clauses`)
- Coarse fallback when fine-grained stats unavailable: `variable_count`, `clause_count`, `cpu_solve_time_ms` present
- `var_to_net` mapping length equals `num_vars`, every net_index < n_nets
- Round-trip Rust → Python: all stats dict keys present and non-null for a non-trivial solve

**Verification**: `cargo test -p temper-rust-router` passes. Manual Python `solve_topology_rust(...)` call on test board returns `solver_stats` dict.

---

### U2. Python: TopologicalSolution Extension and Solver Stats Passthrough

**Goal**: Extend `TopologicalSolution` dataclass with `solver_stats` and `var_to_net` fields. Update the pipeline stage that calls `solve_topology_rust` to capture and pass through the new data.

**Requirements**: FR1.5, NFR1.2

**Dependencies**: U1

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/router_v6/topology_solver.py` — add `solver_stats: dict | None` and `var_to_net: list[int] | None` to `TopologicalSolution`
- **Modify**: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — capture `solver_stats` and `var_to_net` from `rust_result` dict and pass to `TopologicalSolution`

**Approach**:
- `TopologicalSolution` dataclass gains `solver_stats: dict | None = None` and `var_to_net: list[int] | None = None` defaulting to `None` for backward compatibility.
- The Rust solver call in `pipeline.py:632` already receives a dict. Extract `rust_result.get("solver_stats")` and `rust_result.get("var_to_net")` and pass to the `TopologicalSolution(...)` constructor.
- The existing `TopologicalSolution` constructor at `pipeline.py:647` is extended with these two new kwargs.

**Test scenarios**:
- `TopologicalSolution` created without `solver_stats` (backward compat) — field is `None`
- `TopologicalSolution` created with `solver_stats` dict — field preserves all keys
- Pipeline stage 3.8 run on test board: `solution.solver_stats` is a non-empty dict, `solution.var_to_net` is a list of length `num_vars`

**Verification**: Existing stage 3 tests pass. Manual inspection of `solution.solver_stats` from a pipeline run.

---

### U3. Python: Per-Net Routability Score Aggregation

**Goal**: Compute `routability_scores: Array (N,)` (per-component penalty) from solver statistics and `var_to_net` mapping.

**Requirements**: FR2.1–FR2.4

**Dependencies**: U1, U2

**Files**:
- **Create**: `packages/temper-placer/src/temper_placer/router_v6/routability_aggregator.py` — **New**: net-level score computation from solver stats
- **Create**: `packages/temper-placer/tests/router_v6/test_routability_aggregator.py` — unit tests

**Approach**:

1. **`RoutabilityAggregator` class** with method `compute_scores(stats: dict, var_to_net: list[int], n_components: int) -> tuple[jnp.ndarray, float]`:
   - Returns `(routability_scores: (N,) jnp.ndarray, score_mean: float)`.

2. **SAT case (status == "sat")** — FR2.2 formula:
   - For each net $n$, compute:
     - $b_n$ = backtrack count attributed to net (from `solver_stats.backtracks_by_net` if granular, else divide `conflicts` proportionally by net variable count)
     - $a_n$ = clause activity sum (from `solver_stats.activity_by_net` if granular, else uniform)
     - $d_n$ = mean decision level for net's variables
     - $c_n$ = 0 (SAT case — no UNSAT core)
   - Normalize each term by max across all nets: $B_{\max} = \max_n b_n$, etc.
   - Weights: $w_b=0.3, w_a=0.2, w_d=0.2, w_c=0.3$ (configurable).
   - Per-net score $r_n = \text{clamp}(w_b \cdot b_n/B_{\max} + \dots, 0, 1)$.

3. **UNSAT case** — FR2.3:
   - $r_n = 1.0$ for every net in UNSAT core, $0.0$ otherwise.
   - `unsat_core_size` from stats; core clause indices mapped to net indices via `var_to_net`.
   - If UNSAT core is empty (splr didn't produce one): fallback to audit-based penalty (U7).

4. **Score aggregation to components** — FR2.4:
   - Map per-net scores to per-component via: `p_i = max(r_n for n in nets(i))`.
   - Uses `context.netlist` to look up nets incident to each component.

5. **Coarse stats fallback** (when fine-grained CDCL stats unavailable, FR1.7):
   - For each net, use `clause_to_var_ratio` and `solve_throughput` as proxy:
     - Nets with more variables (wider channels) get higher score on hard instances.
   - $r_n = \text{clamp}((clause\_to\_var\_ratio / 10) \cdot (net\_var\_count / N), 0, 1)$.
   - Multiply by `(solver_time_ms / timeout_ms)` as a difficulty factor.

**Test scenarios**:
- 3 nets, 2 channels, SAT solve with known stats: scores computed correctly
- All-zero stats → all scores zero (FR2.3 correctness: NFR2.3)
- UNSAT with core of 2 clauses → 2 nets get score 1.0, others 0.0
- Empty UNSAT core → fallback triggered (scores from audit path, delegated to U7)
- Coarse stats path: `clause_to_var_ratio` high → scores > 0
- Per-component aggregation: component connected to 3 nets gets max score
- Score vector length equals `n_components`

**Verification**: `pytest packages/temper-placer/tests/router_v6/test_routability_aggregator.py -v` passes.

---

### U4. Python: StatefulLossFunction ABC

**Goal**: Add `StatefulLossFunction` abstract base class to `losses/base.py`, extending `LossFunction` with `blend()`/`compute_loss()` separation pattern.

**Requirements**: FR3.1

**Dependencies**: None (pure ABC addition)

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/losses/base.py` — add `StatefulLossFunction` ABC after `LossFunction` (line ~823)

**Approach**:
```python
class StatefulLossFunction(LossFunction, ABC):
    """
    A loss function that maintains mutable state updated once per refinement
    iteration, outside the JAX inner loop.

    The blend() / compute_loss() separation ensures stateful blending
    happens exactly once per iteration, while compute_loss() is pure
    and JAX-jittable.

    Subclasses must implement blend() and compute_loss().
    """

    @abstractmethod
    def blend(self, state: dict) -> None:
        """
        Blend new feedback data into internal state.

        Called by the orchestrator once per outer refinement iteration,
        BEFORE the JAX inner optimization loop.

        Args:
            state: Dict with iteration-specific data (e.g. routability scores,
                   heatmaps, solver stats).
        """
        ...

    @abstractmethod
    def compute_loss(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute loss from the blended internal state.

        Called during JAX gradient descent. Must be pure and jittable.

        Returns:
            LossResult with scalar value and breakdown.
        """
        ...

    @abstractmethod
    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Convenience: delegates to compute_loss().

        For use when the loss is used without blend() in a single-pass context.
        """
        ...
```

- `__call__` delegates to `compute_loss()` by default, so subclasses only implement `blend()` and `compute_loss()`.
- Place the class in `base.py` after line ~823 (after `LossFunction.weight_schedule`).

**Test scenarios** (in `tests/losses/test_stateful_loss.py`):
- Concrete subclass with both methods → `__call__` delegates correctly
- `isinstance(stateful_loss, LossFunction)` is True (Liskov substitution)
- `name` property inherited from `StatefulLossFunction` via `LossFunction`

**Verification**: `pytest packages/temper-placer/tests/losses/test_stateful_loss.py -v` passes.

---

### U5. Python: RoutabilityGradientLoss with Straight-Through Estimator

**Goal**: Implement `RoutabilityGradientLoss(StatefulLossFunction)` with STE gradient, HPWL soft proxy, and `blend()`/`compute_loss()` separation.

**Requirements**: FR3.1–FR3.6, NFR1.3, NFR2.1, NFR2.3, NFR2.4

**Dependencies**: U4, U3

**Files**:
- **Create**: `packages/temper-placer/src/temper_placer/losses/routability_gradient.py` — **New**: STE loss function
- **Create**: `packages/temper-placer/tests/losses/test_routability_gradient.py` — unit tests

**Approach**:

1. **Class `RoutabilityGradientLoss(StatefulLossFunction)`**:
   ```python
   @dataclass
   class RoutabilityGradientLoss(StatefulLossFunction):
       routability_scores: Array | None = None  # (N,) — set via blend()
       _iteration: int = 0
       _best_scores: Array | None = None        # monotonic best
       _score_history: list[float] = field(default_factory=list)
       # EWMA state
       _ema_scores: Array | None = None
       _alpha_floor: float = 0.1
   ```

2. **`blend(state: dict)` method** — FR3.1, FR4.5:
   - Receives `state` dict with `"routability_scores": (N,) array`, `"iteration": int`.
   - If iteration 0: `_ema_scores = raw_scores` (alpha = 1.0).
   - Else: `alpha = max(self._alpha_floor, 1.0 / (iteration + 1))`; `_ema_scores = alpha * raw_scores + (1 - alpha) * _ema_scores`.
   - Track `_score_history.append(float(mean(scores)))`.
   - Update `_best_scores` if current mean < best mean (monotonic improvement, FR5.3).

3. **`compute_loss()` method** — FR3.2–FR3.5, FR5.4:
   ```python
   def compute_loss(self, positions, rotations, context, ...) -> LossResult:
       scores = self._ema_scores  # blended EWMA scores
       # FR3.3: Straight-through estimator
       soft_proxy = self._compute_net_wirelengths(positions, context)  # (N,)
       ste_signal = soft_proxy + jax.lax.stop_gradient(scores - soft_proxy)
       # FR3.4: Loss = sum(ste_signal_i * distance_from_anchor_i)
       anchors = context.anchor_positions  # (N, 2) — position at iteration start
       distances = jnp.linalg.norm(positions - anchors, axis=-1)  # (N,)
       loss = jnp.sum(ste_signal * distances)
       # FR5.4: Gradient clip via jnp.clip on position delta
       # (applied in orchestrator, not here — loss value is unscaled)
       # NFR2.4: Fixed components have zero gradient (handled by grad mask
       # in create_value_and_grad_fn at base.py)
       return LossResult(value=loss, breakdown={
           "routability_gradient_total": loss,
           "routability_gradient_max": jnp.max(scores),
           "routability_gradient_mean": jnp.mean(scores),
           "routability_active_components": jnp.sum(scores > 0.0),
       })
   ```

4. **`_compute_net_wirelengths()` (soft proxy)** — FR3.5:
   - Reuse internals from `WirelengthLoss` (`losses/wirelength.py`):
   - For each net, compute HPWL via `jnp.max(pin_x) - jnp.min(pin_x) + jnp.max(pin_y) - jnp.min(pin_y)`.
   - Sum HPWL per component: for component $i$, sum HPWL of all nets incident to $i$.
   - Normalize to $[0, 1]$ by dividing by max per-iteration HPWL across components.
   - Implementation: use `context.netlist.pin_positions_by_net()` to get pin coords, compute HPWL per net, aggregate to components.
   - Must be JAX-differentiable: `jnp.max`/`jnp.min` are differentiable; this is standard in the codebase.

5. **`__call__` convenience** — delegates to `compute_loss()` (inherited from `StatefulLossFunction`).

6. **NFR2.2 correctness: zero loss on zero scores**:
   - When `routability_scores` are all zeros → `ste_signal` = soft_proxy + sg(0 - soft_proxy) = 0 → loss = 0.
   - Verified in test.

7. **NFR2.1 correctness: no NaN gradients**:
   - `jnp.nan_to_num(positions, nan=0.0)` on inputs.
   - `distances = jnp.clip(distances, 0.0, 1e6)` as safety.
   - `ste_signal = jnp.clip(ste_signal, -1.0, 1.0)`.

8. **Gradient clipping** (FR5.4):
   - The loss value uses unscaled `distances`, but the orchestrator applies `jnp.clip` on the position update delta with `max_grad_norm = 1.0` mm.
   - This is implemented in U6 (integration), not in the loss function itself.

**Test scenarios** (in `tests/losses/test_routability_gradient.py`):
- **Zero signal → zero loss** (AC7, NFR2.3): all routability scores = 0.0 → loss value = 0.0
- **STE gradient correctness** (AC3): component with high routability score gets non-zero gradient; component with score = 0 gets zero gradient
- **JAX jit compatibility** (NFR1.3): `compute_loss()` wrapped in `@jax.jit` runs without error
- **Differentiability** (AC2, NFR2.1): `jax.grad(compute_loss)(positions)` produces finite, non-NaN array
- **Distance-from-anchor weighting**: component that doesn't move from anchor → contributes zero to loss regardless of routability score
- **EWMA blend**: iteration 1 raw = [1.0, 0.5, 0.0]; iteration 2 raw = [0.5, 0.5, 1.0]; blended at alpha=0.5 produces [0.75, 0.5, 0.5]
- **Fixed components** (NFR2.4): component with `fixed_mask=True` in context gets zero gradient
- **UNSAT all-ones scores**: produces scalar loss within reasonable range
- **Breakdown keys**: all required keys present in `LossResult.breakdown`
- **NaN guard**: scores with NaN values don't propagate to loss

**Verification**: `pytest packages/temper-placer/tests/losses/test_routability_gradient.py -v` passes.

---

### U6. Python: Integration into RefinementStage

**Goal**: Wire `RoutabilityGradientLoss` into the active `RefinementStage.__call__` loop, invoking SAT solver each iteration and blending routability scores via `blend()`.

**Requirements**: FR4.1–FR4.4, NFR1.4

**Dependencies**: U1, U2, U3, U5

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/pipeline/stages/refinement_stage.py` — integrate SAT solver call + `RoutabilityGradientLoss` into the `update_fn` closure

**Approach**:

1. **SAT solver invocation per refinement iteration** (FR4.2, FR4.3):
   - Inside the `OrchestratorRouter.route()` method or within the iterator loop, after maze routing:
   - Build constraint model from current positions, call `solve_topology_rust()` with reduced timeout (default 500 ms, FR4.3 / NFR1.4).
   - Extract `solver_stats` and `var_to_net` from result.
   - Call `RoutabilityAggregator.compute_scores()` → `routability_scores: (N,) array`.
   - Return both `routability_scores` and solver status alongside the maze-routing result.

2. **Integration into `update_fn`** (FR4.1):
   - Before building `CompositeLoss`, call `routability_loss.blend({"routability_scores": scores, "iteration": iter_idx})`.
   - Add `WeightedLoss(routability_loss, weight=50.0)` to the `CompositeLoss` list:
     ```python
     WeightedLoss(RoutabilityGradientLoss(routability_scores), weight=50.0),
     ```
   - The `routability_loss` instance is created once outside `update_fn` and its `blend()` called each iteration.

3. **Separate SAT + maze router invocations** (FR4.3):
   - The maze router (congestion heatmap) and SAT solver (routability scores) are both invoked each iteration but produce independent feedback signals.
   - Both are passed into `update_fn` via the routing result.

4. **Weight scheduling** (FR4.4):
   - Iteration 0: `routability_loss.weight = 0.0` (no signal yet — first pass is baseline).
   - Iterations 1–2: ramp `weight = target_weight * (iter / 2)`.
   - Iteration 3+: `weight = target_weight` (50.0 default).
   - If completion_rate > `routability_threshold` (0.85): scale weight by 0.3.
   - Weight management happens at the orchestrator level, outside JAX compilation boundaries.

5. **Gradient clipping** (FR5.4):
   - After JAX optimizer step, clip position delta per component:
     ```python
     delta = updated_params["positions"] - old_positions
     delta_norm = jnp.linalg.norm(delta, axis=-1, keepdims=True)
     delta_clipped = delta * jnp.minimum(1.0, max_grad_norm / (delta_norm + 1e-8))
     params["positions"] = old_positions + delta_clipped
     ```
   - `max_grad_norm = config.routability_gradient_max_grad_norm` (default 1.0 mm).

6. **Timeout for SAT solver** (FR4.3, NFR1.4):
   - The `solve_topology_rust` function doesn't currently accept a timeout parameter.
   - Either: (a) add a `timeout_ms` parameter to the Rust function (uses `std::time::Instant` to terminate early after timeout), OR (b) use Python-side `concurrent.futures` with timeout.
   - Recommendation: add `timeout_ms` parameter to `solve_topology_rust` (Rust-side). On timeout, return `SolverStatus::Unknown` with coarse stats populated.

**Test scenarios** (in `tests/router_v6/test_stage3_routability_feedback.py` — AC8):
- Refinement iteration with SAT solver returning SAT → stats collected, scores computed, loss blended
- Refinement iteration with SAT solver returning UNSAT → UNSAT path triggered (delegated to U7)
- SAT timeout during refinement → `Unknown` status, coarse stats used
- Maze router + SAT solver both invoked each iteration
- Weight is 0.0 on iteration 0, ramps to target on iteration 2
- Position delta is clipped to `max_grad_norm` mm per component
- CompositeLoss breakdown includes routability_gradient terms

**Verification**: `pytest packages/temper-placer/tests/router_v6/test_stage3_routability_feedback.py -v` passes.

---

### U7. Python: UNSAT Fallback Path

**Goal**: Handle UNSAT solver results with core-based penalties, audit-based fallback, movement budget doubling, and persistence escape.

**Requirements**: FR6.1–FR6.5, FR2.3

**Dependencies**: U1, U3, U6

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/router_v6/routability_aggregator.py` — UNSAT scoring logic
- **Modify**: `packages/temper-placer/src/temper_placer/pipeline/stages/refinement_stage.py` — UNSAT handling (movement budget, escape)

**Approach**:

1. **UNSAT core extraction** (FR6.1):
   - Already working via `solve_with_cadical_cores()` in `solver.rs:123`.
   - Core clause indices are returned in `result.unsat_core` → `rust_result["unsat_core"]`.
   - In `routability_aggregator.py`: map core clause indices to net indices via `var_to_net` — for each core clause index, find which variables appear in that clause, then get their `net_idx` from `var_to_net`.

2. **UNSAT penalty signal** (FR6.2, FR2.3):
   - $r_n = 1.0$ for every net in UNSAT core → $r_n = 0.0$ for all others.
   - Mapped to components via `p_i = max(r_n for n in nets(i))`.

3. **Maximum movement budget for UNSAT** (FR6.3):
   - In `RefinementStage.__call__`, after detecting UNSAT:
   - Set `config.max_movement_mm = config.max_movement_mm * config.routability_gradient_unsat_movement_multiplier` (default 2.0 → 4.0 mm).
   - This override applies only for the iteration immediately following an UNSAT result.

4. **UNSAT persistence escape** (FR6.4):
   - Track consecutive UNSAT iterations in a counter: `unsat_streak`.
   - If `unsat_streak >= 3`:
     - Log diagnostic: `"SAT solver could not guide convergence within budget after 3 UNSAT iterations"`
     - Fall back to `simple_congestion_repel()` (`iterative_placer.py:164`).
     - Reset `unsat_streak` after applying repel.

5. **UNSAT without core fallback** (FR6.5):
   - When `result.unsat_core` is empty but status is UNSAT:
   - Call `audit_result()` PyO3 function (`lib.rs:110`) with a greedy partial assignment to identify violated constraints.
   - From audit violations, extract violating variable names → map to nets via constraint model → $r_n = 1.0$ for those nets.
   - Propagation penalty: nets sharing a channel with a detected-violation net → $r_n = 0.5$.

**Test scenarios**:
- UNSAT with non-empty core: 3 core clauses → 3 nets get score 1.0, others 0.0
- UNSAT with empty core + audit violations found: violating nets get 1.0, channel-sharing nets get 0.5
- UNSAT with empty core + no audit violations: all scores = 1.0 (conservative: everything is suspect)
- Movement budget doubles after UNSAT (2.0 → 4.0 mm default)
- After 3 consecutive UNSAT iterations → `simple_congestion_repel` called, diagnostic logged
- UNSAT streak resets after a SAT iteration

**Verification**: Updated `test_routability_aggregator.py` tests pass. Integration test with UNSAT fixture passes.

---

### U8. Python: Convergence Guards and Weight Scheduling

**Goal**: Implement weight decay on convergence, oscillation detection, monotonic improvement tracking, and convergence halt.

**Requirements**: FR5.1–FR5.3, FR4.4

**Dependencies**: U5, U6

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/losses/routability_gradient.py` — add convergence-guard state and logic
- **Modify**: `packages/temper-placer/src/temper_placer/pipeline/stages/refinement_stage.py` — wire guard calls per iteration

**Approach**:

1. **Weight decay on convergence** (FR5.1):
   - In `RoutabilityGradientLoss.blend()`, after computing `_score_history`:
   - If `_score_history[-1] < _score_history[-2]` AND `_score_history[-2] < _score_history[-3]` (3-point decreasing trend), AND `completion_rate > routability_threshold`:
     - `self.current_weight *= 0.5`.
   - `current_weight` is an instance attribute, initially `target_weight`, used in `compute_loss()` to scale the output.

2. **Oscillation detection** (FR5.2):
   - If `score_mean` increases (worsens) for 2 consecutive iterations:
     - Log warning: `"Routability score oscillating: freezing scores at best-observed values"`
     - Freeze `_ema_scores` to `_best_scores` (monotonic best, FR5.3).
     - Reset freeze on next SAT iteration.

3. **Monotonic improvement tracking** (FR5.3):
   - Already implemented in `RoutabilityGradientLoss._best_scores` (U5 step 2).
   - In `compute_loss()`: if current `_ema_scores` mean > `_best_scores` mean, use `_best_scores` instead (pessimistic guard).
   - Track `best_routability_score_mean` alongside the existing `best_completion` in `PlaceRouteIterator`.

4. **Integration with existing convergence halt** (FR5.4 already covered in U6):
   - The existing `PlaceRouteIterator` tracks `best_completion` and halts on convergence.
   - Extend to also halt if `routability_score_mean < 0.05` for 2 consecutive iterations (placement is "solved" from routability perspective).
   - The gradient clipping from U6 step 5 prevents catastrophic displacement.

**Test scenarios**:
- Decreasing score_mean for 3 iterations + completion > 0.85 → weight halved
- Increasing score_mean for 2 iterations → oscillation warning logged, scores frozen
- Current mean worse than best mean → `_best_scores` used in loss
- Convergence halt: score_mean < 0.05 for 2 iterations → refinement terminates early

**Verification**: Unit tests for weight decay and oscillation detection in `test_routability_gradient.py`.

---

### U9. Python: Observability — Logging and Dataclass Extensions

**Goal**: Add per-iteration routability logging and extend result dataclasses.

**Requirements**: NFR3.1–NFR3.3

**Dependencies**: U6

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/pipeline/iterative_placer.py` — extend `IterationResult` and `PlaceRouteResult` dataclasses
- **Modify**: `packages/temper-placer/src/temper_placer/pipeline/stages/refinement_stage.py` — add logging per iteration

**Approach**:

1. **Extend `IterationResult`** (`iterative_placer.py:26`):
   ```python
   @dataclass
   class IterationResult:
       # ... existing fields ...
       routability_score_mean: float = 0.0
       unsat_core_size: int = 0
       solver_status: str = "unknown"  # "sat", "unsat", "unknown"
   ```

2. **Extend `PlaceRouteResult`** (`iterative_placer.py:38`):
   ```python
   @dataclass
   class PlaceRouteResult:
       # ... existing fields ...
       routability_history: list[float] = field(default_factory=list)
   ```

3. **Logging per iteration** (NFR3.1):
   In `RefinementStage.__call__` or the iterator, after each routing+SATSolver pass:
   ```python
   print(f"Iteration {i}: routability_mean={score_mean:.3f}, "
         f"worst_nets={top_5_worst_nets}, sat_status={status}, "
         f"unsat_core={core_size}, ste_grad_norm={grad_norm:.3f}")
   ```

**Test scenarios**:
- `IterationResult` fields correctly populated from refinement loop
- `PlaceRouteResult.routability_history` contains one float per iteration
- Log output includes top 5 worst nets and SAT status

**Verification**: Existing iterative placer tests pass with extended dataclasses (backward compatible defaults).

---

### U10. Python: Configuration — PipelineConfig Extensions

**Goal**: Add all routability-gradient hyperparameters to `PipelineConfig`.

**Requirements**: NFR4

**Dependencies**: None (additive to config)

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/pipeline/orchestrator.py` — add 5 new fields to `PipelineConfig` dataclass

**Approach**:

Add to `PipelineConfig` (`orchestrator.py:66`):
```python
# Routability gradient (new)
routability_gradient_weight: float = 50.0          # FR4.1 base weight
routability_gradient_max_grad_norm: float = 1.0    # FR5.4 max L2 norm (mm)
routability_gradient_unsat_movement_multiplier: float = 2.0  # FR6.3
routability_gradient_sat_timeout_ms: float = 500.0 # FR4.3 SAT timeout
routability_gradient_unsat_escape_iterations: int = 3  # FR6.4
```

These propagate from `PipelineConfig` → `DataContext` → `RefinementStage`.

**Test scenarios**:
- Default values are as specified
- Config round-trips through `dataclasses.asdict()`/`from __init__`
- Custom values propagate to `RefinementStage.__call__` via `DataContext`

**Verification**: Existing config serialization tests pass with new fields.

---

### U11. Testing: Unit and Integration Test Suite

**Goal**: Comprehensive test coverage per acceptance criteria AC1–AC8.

**Requirements**: AC1–AC8

**Dependencies**: U1–U10

**Files**:
- **Create**: `packages/temper-placer/tests/losses/test_routability_gradient.py` — unit tests for STE loss (AC7)
- **Create**: `packages/temper-placer/tests/losses/test_stateful_loss.py` — unit tests for ABC (U4)
- **Create**: `packages/temper-placer/tests/router_v6/test_routability_aggregator.py` — unit tests for aggregation (U3)
- **Create**: `packages/temper-placer/tests/router_v6/test_stage3_routability_feedback.py` — integration test for end-to-end flow (AC8)
- **Modify**: `packages/temper-rust-router/tests/test_encoding.rs` — add `var_to_net` verification (part of AC1)
- **Modify**: `packages/temper-placer/tests/router_v6/test_stage3_constraint_audit.py` — extend with solver_stats assertions (part of AC1)

**Test coverage matrix**:

| AC | Test file | Scenarios |
|---|---|---|
| AC1: `solver_stats` returned | `test_stage3_constraint_audit.py` (extended) | SAT/UNSAT both return stats; coarse fallback keys present |
| AC2: Loss is JIT-table + differentiable | `test_routability_gradient.py` | `@jax.jit` compiles; `jax.grad` produces finite values |
| AC3: Gradient zero for low-score nets | `test_routability_gradient.py` | score=0 → grad=0; score=1 → grad≠0 |
| AC4: UNSAT → larger position updates | `test_stage3_routability_feedback.py` | UNSAT iteration moves components further than SAT iteration |
| AC5: UNSAT persistence escape | `test_stage3_routability_feedback.py` | 3 UNSAT → simple_congestion_repel called |
| AC6: No regression on existing boards | `test_stage3_routability_feedback.py` + CI run | Completion rate >= baseline on known-good boards |
| AC7: Unit tests for loss | `test_routability_gradient.py` | zero signal, STE correctness, UNSAT fallback |
| AC8: Integration test end-to-end | `test_stage3_routability_feedback.py` | SAT solver → stats → scores → loss → gradient → position update |

**Additional test scenarios** (not directly tied to ACs):
- **Backward compatibility**: pipeline without routability gradient (weight=0 or missing config) produces identical results to current behavior
- **Empty problem**: 0 nets, 0 components → scores vector is empty → loss is 0
- **Single component**: single-component placement → routability gradient is defined (no NaN from empty reductions)
- **SAT timeout handling**: solver times out → `Unknown` status → coarse stats used → scores still computed

**Verification**: All test suites pass. `cargo test -p temper-rust-router` passes. `pytest packages/temper-placer/tests/losses/test_routability_gradient.py packages/temper-placer/tests/losses/test_stateful_loss.py packages/temper-placer/tests/router_v6/test_routability_aggregator.py packages/temper-placer/tests/router_v6/test_stage3_routability_feedback.py -v` passes.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `GetInternalStats` trait not exposed in `rustsat-cadical` 0.7.5 | Medium | Medium | Coarse stats fallback (FR1.7) provides workable signal. CaDiCaL C++ library exposes `cadical_stats()` — if rustsat wrapper doesn't surface it, add a small shim or use the `cadical-sys` crate directly. |
| STE gradient points in useless direction (HPWL proxy doesn't correlate with routability) | Medium | Medium | The routability term is additive to existing `RoutingFeedbackLoss` (maze congestion). Multi-term composite loss provides gradient redundancy. Monitor on test boards; if HPWL proxy is poor, a learned proxy (deferred) can replace it. |
| UNSAT core extraction has overhead (selector variables double variable count) | Low | Medium | `solve_with_cadical_cores()` already exists and works. Selector-variable overhead is addressed by using `solve_with_cadical()` (no selectors) for SAT cases and only switching to `_cores` variant on UNSAT. |
| SAT solver timeout during refinement adds iteration latency | Low | Low | 500 ms timeout is configurable. SAT solves for partial refinement updates are typically simpler than the final solve (fewer nets in play). If still slow, reduce `max_sat_nets` via the existing selective-SAT mechanism. |
| RefinementStage is deprecated for `_run_refinement` but active for `RefinementStage.__call__` | Low | Low | Plan targets `RefinementStage.__call__` (`refinement_stage.py:15`) which is the active path. The deprecated `_run_refinement` is not modified. |

## Open Questions

### Resolved During Planning

- **SAT solver granularity?** Global invocation (one SAT call covering all nets). Per-net invocation is O(N) more expensive and deferred.
- **STE proxy choice?** HPWL (already implemented in `WirelengthLoss` internals). Learned proxy is deferred.
- **Integration target?** `RefinementStage.__call__` at `refinement_stage.py:15` (active), not `_run_refinement` (deprecated).
- **Solver backend?** CaDiCaL via `rustsat-cadical` (migrated from splr). `GetInternalStats` trait availability must be verified.

### Deferred to Implementation

- **Exact `GetInternalStats` trait surface:** Verify which of `conflicts()`, `decisions()`, `propagations()` are available on `rustsat_cadical::CaDiCaL` 0.7.5. Run a spike in U1 before committing to fine-grained stats shape.
- **`decision_level_histogram` computation:** If CaDiCaL doesn't expose per-variable decision levels, use `decisions / conflicts` ratio quantile bucketing as a heuristic proxy for depth-of-search complexity.
- **UNSAT core empty → audit fallback:** The `audit_result()` approach (FR6.5) requires a partial assignment to audit against. The current `audit_result` expects a full assignment dict; a greedy partial assignment must be built first. Decide during implementation whether to (a) build partial assignment in Rust, or (b) call `audit_result` with an empty assignment and parse violations.

## Dependencies

- `CaDiCaL` via `rustsat-cadical` 0.7.5 — existing in `Cargo.toml`
- `GetInternalStats` trait + `SolveStats` trait from rustsat — availability to be verified
- `RoutingFeedbackLoss` / `MomentumDampedRoutingFeedbackLoss` — existing at `feedback.py:31,92`
- `LossFunction` ABC — existing at `losses/base.py:753`
- `CompositeLoss` / `WeightedLoss` — existing at `losses/base.py:846,914`
- `WirelengthLoss` internals (HPWL computation) — existing at `losses/wirelength.py`
- `PlaceRouteIterator` — existing at `pipeline/iterator.py`
- `RefinementStage.__call__` — existing at `pipeline/stages/refinement_stage.py:15`
- `simple_congestion_repel` — existing at `iterative_placer.py:164`
- `audit_result` PyO3 function — existing at `lib.rs:110`
- `solve_topology_rust` / `solve_with_cadical_cores` — existing at `lib.rs:26` / `solver.rs:123`

## Verification Checklist

- [ ] `solve_topology_rust` returns `solver_stats` dict with `conflicts`, `decisions`, `propagations` (or coarse fallback keys)
- [ ] `CnfFormula.var_to_net` populated correctly — length equals `num_vars`, values in range `[0, n_nets)`
- [ ] `TopologicalSolution.solver_stats` populated from Rust result
- [ ] `RoutabilityAggregator.compute_scores()` returns `(N,)` array in `[0, 1]`
- [ ] `StatefulLossFunction` ABC defined in `base.py`, `blend()`/`compute_loss()` signatures correct
- [ ] `RoutabilityGradientLoss` inherits from `StatefulLossFunction`
- [ ] STE loss is `@jax.jit`-compatible and `jax.grad` produces finite, non-NaN values
- [ ] Zero routability scores → zero loss
- [ ] High routability score on a component → non-zero gradient on that component
- [ ] EWMA blend separates from loss computation (blend called once per iteration)
- [ ] `RefinementStage.__call__` invokes SAT solver each iteration alongside maze router
- [ ] Weight ramps from 0.0 (iter 0) to target (iter 2+)
- [ ] Weight decays by 0.5 when score_mean decreases 2+ iterations and completion > threshold
- [ ] Oscillation detection freezes scores at best-observed values
- [ ] Gradient per-component is clipped to `max_grad_norm` mm
- [ ] UNSAT doubles movement budget for next iteration
- [ ] UNSAT persistence (3 consecutive) → `simple_congestion_repel` fallback
- [ ] Empty UNSAT core → audit-based penalty fallback
- [ ] `IterationResult` and `PlaceRouteResult` extended with routability fields
- [ ] Per-iteration log includes top 5 worst nets, score mean, SAT status, UNSAT core size
- [ ] `PipelineConfig` has all 5 new routability-gradient hyperparameters
- [ ] All new unit tests pass (`test_routability_gradient.py`, `test_routability_aggregator.py`, `test_stateful_loss.py`)
- [ ] Integration test passes (`test_stage3_routability_feedback.py`)
- [ ] Cargo tests pass (`cargo test -p temper-rust-router`)
- [ ] No regression on existing test boards (Piantor, LibreSolar, RP2040, BitAxe)
