---
plan_type: feat
origin: docs/ideation/2026-06-28-sidecar-feedback-convergence-ideation.md
status: active
created: 2026-06-28
---

# feat: Sidecar-as-Contract Placement-Routing Feedback Loop

## Summary

Formalize `bottleneck_report.json` as a mandatory Stage contract, then layer convergence-stability mechanisms on top. The router MUST write a bottleneck report after routing; the placer MUST consume it before re-placing. The pipeline runner enforces the handoff in CI. A momentum-damped congestion loss and convergence-halt guard prevent the loop from oscillating or degrading routing quality.

## Problem Frame

The placement-to-routing pipeline runs as sequential black boxes: place, then route, then done. The router's bottleneck detector (`sequential_routing.py:2030`) and the placer's `RoutingFeedbackLoss` (`pipeline/feedback.py:31`) both exist, but they don't connect. The router has no obligation to produce a bottleneck report, and the placer has no obligation to consume one. The feedback loop skeleton (`pipeline/feedback.py:147`, `iterative_placer.py`, `orchestrator.py` with `max_iterations=5`) is stubbed out with `# TODO: Implement actual coordinate shifts` (`feedback.py:129,132`).

The convergence risk is multiply determined: (1) a single-iteration heatmap snapshot is noisy — two similar routes produce different hotspot patterns; (2) the placer's gradient responds to the full heatmap uniformly, causing global placement drift; (3) the loop has no regression guard — three iterations at 16/24 is worse than one at 18/24, but the loop runs all five anyway.

## Requirements

* **R1**: The routing stage declares it writes a `bottleneck_report` sidecar, and the placer declares it reads one. The pipeline runner validates the handoff — a missing sidecar fails CI.
* **R2**: After every routing pass, the router produces a `BottleneckReport` containing: failed nets with failure reasons, per-net-class congestion heatmaps, and spatial bottleneck regions (bounding boxes of max-flow min-cut areas).
* **R3**: The placer's `RoutingFeedbackLoss` uses an EWMA (exponentially weighted moving average) of congestion across iterations, not the single-iteration snapshot. The momentum weight decays per iteration so corrections shrink near convergence.
* **R4**: The feedback loop halts on routability regression — if `routed_nets / total_nets` has not improved in 2 iterations, or has regressed from the best-so-far, the loop terminates with a diagnostic. The fixed `max_iterations=5` is replaced by an adaptive termination that cannot make routing worse than single-pass.
* **R5**: Existing single-pass pipeline behavior is preserved when the feedback loop is not enabled (backward compatibility).

## Scope Boundaries

**In scope**:
- Define `BottleneckReport` dataclass and `DeclaredArtifact` contract types
- Extend `Stage` ABC with `declared_writes`/`declared_reads` properties
- Wire declared-artifact validation into the pipeline runner
- Add CI gate for missing sidecar enforcement
- Implement EWMA momentum-damped `RoutingFeedbackLoss`
- Implement convergence halt on routability regression

**Deferred to Follow-Up Work**:
- Per-net-class congestion heatmaps (Idea #4 from ideation)
- Diff-based modified-region feedback (Idea #5)
- Adaptive A* iteration budget for previously-failed nets (Idea #7)
- Full round-trip placement↔routing iteration (requires resolving `feedback.py:129,132` TODOs)

**Out of scope**:
- New routing algorithms or placement strategies
- Changes to the DRC oracle
- GPU-accelerated heatmap computation
- Human-in-the-loop bottleneck review

## Key Technical Decisions

1. **Contract via `declared_writes`/`declared_reads` on Stage ABC**, not a separate registry or config file. This mirrors the existing `invariants` property pattern (see `deterministic/stages/base.py:19-21`) and keeps the contract co-located with the stage that owns it. (see origin: ideation idea #6, brainstorming decision "contract first")

2. **Hard enforcement in CI, not WARNING-only.** The pipeline runner validates declared-artifact handoffs at the end of the stage loop. A declared write that wasn't produced, or a declared read that points to a missing file, raises a hard error. The `TEMPER_FEEDBACK_ENABLED` env var gates whether the sidecar is checked — when disabled, the contract is a no-op (R5).

3. **BottleneckReport is a JSON sidecar file**, following the established pattern from `placement.channels.json` and `Stage2Output.json`. It is written by `compile_routing_results()` and read by the feedback loop's `RoutingFeedbackLoss`. The sidecar is versioned with a `schema_version` field.

4. **EWMA momentum uses iteration-decaying alpha.** Iteration 0: `alpha=1.0` (raw snapshot). Subsequent: `alpha = max(0.1, 1.0 / (iteration + 1))`. The blended heatmap = `alpha * current + (1-alpha) * previous`. The decay schedule `1/(n+1)` is simple, convergent, and avoids the need for a tunable hyperparameter.

5. **Convergence halt tracks best-so-far routability ratio.** The loop records `best_routability` across iterations. If `current < best_routability * 0.95` (a 5% regression), or if `current == best_routability` for 2 consecutive iterations, the loop terminates. This prevents both oscillation damage and wasted cycles on converged solutions.

## Implementation Units

---

### U1. Define BottleneckReport and DeclaredArtifact contract types

**Goal**: Create the data model that the router writes and the placer reads, plus the contract primitives the Stage protocol uses.

**Requirements**: R1, R2

**Dependencies**: None

**Files**:
- **Create**: `packages/temper-placer/src/temper_placer/pipeline/bottleneck_report.py` — `BottleneckReport` dataclass, `DeclaredArtifact` type, serialization/deserialization
- **Create**: `packages/temper-placer/tests/pipeline/test_bottleneck_report.py` — unit tests

**Approach**:
- `BottleneckReport` dataclass:
  - `schema_version: str` (e.g., `"1.0.0"`)
  - `failed_nets: list[BottleneckNetEntry]` — per-net failure with reason, pin positions, net class
  - `congestion_heatmaps: dict[str, CongestionHeatmapData]` — per-net-class (keyed by `"HV"`, `"Signal"`, `"Power"`, etc.)
  - `bottleneck_regions: list[BottleneckRegion]` — spatial bounding boxes from min-cut analysis, with affected component pairs
  - `routability_ratio: float` — `routed_nets / total_nets`
  - `to_json()` and `from_json()` methods
- `DeclaredArtifact` dataclass: `name: str`, `description: str`, `schema_version: str`
- Serialization uses JSON with numpy array conversion for heatmap grids

**Patterns to follow**: `Stage2Output` at `pipeline.py:47-87` for dataclass structure. `CongestionHeatmap` at `routing/congestion_heatmap.py` for heatmap data shape.

**Test scenarios**:
- BottleneckReport round-trips through JSON without data loss
- Empty report (no failures) serializes and deserializes correctly
- Heatmap grid data survives numpy→list→numpy conversion
- schema_version mismatch raises a clear error on deserialization
- DeclaredArtifact equality and hash work correctly for contract validation

**Verification**: `pytest packages/temper-placer/tests/pipeline/test_bottleneck_report.py -v` passes.

---

### U2. Extend Stage ABC with declared-artifact contract and pipeline runner enforcement

**Goal**: Add `declared_writes` and `declared_reads` to the Stage ABC, wire validation into the pipeline runner, and add CI gate.

**Requirements**: R1, R5

**Dependencies**: U1

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/deterministic/stages/base.py` — add `declared_writes` and `declared_reads` properties
- **Modify**: `packages/temper-placer/src/temper_placer/deterministic/pipeline.py` — post-stage contract validation
- **Modify**: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — post-stage contract validation for RouterV6
- **Modify**: `packages/temper-placer/src/temper_placer/deterministic/flags.py` — add `TEMPER_FEEDBACK_ENABLED` env var flag
- **Create**: `packages/temper-placer/tests/pipeline/test_stage_contract.py` — contract enforcement tests

**Approach**:
- Add to Stage ABC (mirroring `invariants` pattern at `base.py:19-21`):
  - `declared_writes: tuple[DeclaredArtifact, ...]` — artifacts this stage promises to produce. Default empty tuple.
  - `declared_reads: tuple[DeclaredArtifact, ...]` — artifacts this stage requires from prior stages. Default empty tuple.
- Pipeline runner, after a stage's `run()` completes: iterate over `declared_writes` and verify each artifact file exists at the declared path. If missing, raise `MissingDeclaredArtifactError`.
- Pipeline runner, before a stage's `run()`: iterate over `declared_reads` and verify each required artifact exists (produced by a prior stage). If missing, raise `MissingRequiredArtifactError`.
- Both errors are hard failures when `TEMPER_FEEDBACK_ENABLED` is set (default). When the env var is `"0"`, `"false"`, or `"off"`, contract validation is skipped (R5).
- The `sequential_routing` stage declares `declared_writes = (DeclaredArtifact("bottleneck_report", "Routing bottleneck analysis", "1.0.0"),)`.
- The `RefinementStage` (or iterative placer) declares `declared_reads = (DeclaredArtifact("bottleneck_report", "Routing bottleneck analysis", "1.0.0"),)`.

**Patterns to follow**: `invariants` property at `base.py:19-21`. `is_drc_fence_fail_enabled()` at `flags.py:27-39` for env var pattern.

**Test scenarios**:
- Stage with empty `declared_writes` and `declared_reads` passes validation (no-op)
- Stage declares a write but the file is not produced → `MissingDeclaredArtifactError` raised
- Stage declares a read but the file was never written by a prior stage → `MissingRequiredArtifactError` raised
- Contract validation skipped when `TEMPER_FEEDBACK_ENABLED=false`
- Pipeline with all contracts satisfied runs to completion
- Missing sidecar is correctly attributed to the stage that failed to produce it

**Verification**: `pytest packages/temper-placer/tests/pipeline/test_stage_contract.py -v` passes. Pipeline with contracts enabled runs against a test board and validates handoff.

---

### U3. Implement momentum-damped congestion loss

**Goal**: Replace the single-iteration congestion snapshot with an EWMA that prevents the placer from over-reacting to noisy heatmap data.

**Requirements**: R3

**Dependencies**: U1, U2

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/pipeline/feedback.py` — add `MomentumDampedRoutingFeedbackLoss` class
- **Create**: `packages/temper-placer/tests/pipeline/test_feedback_momentum.py` — unit tests

**Approach**:
- New class `MomentumDampedRoutingFeedbackLoss` wraps the existing `RoutingFeedbackLoss`:
  - Constructor takes `initial_heatmap: CongestionHeatmap` (from first routing pass)
  - Maintains an internal `blended_grid` array updated each iteration
  - `update(new_heatmap: CongestionHeatmap, iteration: int)` blends the new heatmap into `blended_grid`:
    - `alpha = max(0.1, 1.0 / (iteration + 1))`
    - `blended = alpha * new_grid + (1 - alpha) * blended`
  - `__call__` computes the loss using `blended_grid` rather than the raw single-pass grid
- The alpha decay schedule `1/(n+1)` starts at 1.0 (iteration 0 = pure current snapshot) and asymptotically approaches 0, making later iterations respond less to new data. The `max(0.1, ...)` floor ensures the loop never fully freezes.
- The existing `RoutingFeedbackLoss` is preserved for single-pass use; the momentum-damped variant is used only when the feedback loop is active.

**Patterns to follow**: `RoutingFeedbackLoss` at `feedback.py:31-89` for the loss function signature and JAX integration pattern.

**Test scenarios**:
- Iteration 0: blended_grid equals raw heatmap (alpha=1.0)
- Iteration 3 with constant heatmap: blended_grid converges to the constant
- Iteration 3 with alternating heatmaps: blended_grid is a smoothed average, not oscillating
- alpha never drops below 0.1 floor even at high iteration counts
- Loss gradients are computed from blended_grid, not raw heatmap
- Single-pass mode uses un-blended loss (backward compatible)

**Verification**: `pytest packages/temper-placer/tests/pipeline/test_feedback_momentum.py -v` passes.

---

### U4. Convergence halt on routability regression

**Goal**: Replace fixed `max_iterations=5` with adaptive termination that prevents the loop from degrading routing quality.

**Requirements**: R4

**Dependencies**: U1, U2, U3

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/pipeline/convergence.py` — add regression-aware termination
- **Create**: `packages/temper-placer/tests/pipeline/test_convergence_regression.py` — unit tests

**Approach**:
- Extend `ConvergenceCriteria` with:
  - `best_routed_nets: frozenset[str] | None` — net names routed at the best iteration (not just the count)
  - `best_routability: float | None` — best routability ratio seen so far
  - `stall_count: int` — consecutive iterations with identical routed/failed net sets
  - `regression_detected: bool` — a previously-routed net stopped routing
- The regression threshold is derived from the noise-floor characterization (U1 test): `threshold = best_routability * (1 - 3*sigma/mean)` where sigma and mean come from 5 identical single-pass routes on `temper.kicad_pcb`. If the noise-floor test is not yet run, default to 0.95 (5%).
- New method `check_regression(routed_nets: frozenset[str], total_nets: int) -> ConvergenceDecision`:
  - Compute `current_ratio = len(routed_nets) / total_nets`
  - If `best_routability is None`: record best, continue
  - If the new set of routed nets is a superset of `best_routed_nets` (all previous nets still route, possibly more): update best, reset stall_count, continue
  - If any net in `best_routed_nets` is NOT in the current routed set: `REGRESSION` — halt immediately with diagnostic naming the lost nets
  - If the routed net set is identical to the previous iteration's set: increment `stall_count`. If `stall_count >= 2`: `CONVERGED` — halt with success
  - If current_ratio is below the noise-floor-calibrated threshold (even without net loss): `REGRESSION`
  - Otherwise (different nets route but count is stable): continue (the loop is exploring, not converged or regressed)
- The existing `iteration >= max_iterations` check remains as a safety cap (default 10), but regression and convergence checks take priority.
- The `run_feedback_loop` in `feedback.py:147` calls `check_regression` after each routing pass and terminates early when indicated.

**Patterns to follow**: `ConvergenceCriteria` at `convergence.py:38-55`. The early-stopping pattern mirrors ML training loop validation-loss plateau detection.

**Test scenarios**:
- Routability improves monotonically (0.5 → 0.6 → 0.7), same nets route each time: loop continues until converged or cap
- A previously-routed net stops routing: loop halts with `REGRESSION` naming the lost net
- Routability stalls with identical net sets (0.6, 0.6, 0.6): loop halts after 2 stall iterations with `CONVERGED`
- Routability is constant but different nets route each iteration (set {A,B,C} → {D,E,F} → {A,B,C}): loop continues — this is oscillation, not convergence
- Routability improves then stalls with identical sets (0.5 → 0.7 → 0.7 → 0.7): halts on second stall
- Fixed max_iterations cap still applies as safety net (e.g., never exceed 10 iterations)

**Verification**: `pytest packages/temper-placer/tests/pipeline/test_convergence_regression.py -v` passes.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BottleneckReport serialization is too slow for CI | Low | Low | JSON with numpy→list conversion is O(grid cells). For typical 200×200×4 grids, this is negligible. |
| Momentum damping over-smooths real congestion shifts | Low | Medium | The `alpha >= 0.1` floor ensures the loop never ignores new data completely. The floor is tunable via configuration. |
| Regression threshold is uncalibrated without noise-floor data | Medium | Medium | U1 includes a noise-floor characterization test. The threshold defaults to 5% but is replaced by 3σ from measured variance once the test runs. |
| Contract validates existence but not freshness across iterations | Low | Low | Within a single pipeline run, artifacts are produced and consumed in-order. Freshness is a concern only if the same artifact is read and re-written in the same iteration — not the case for the bottleneck report. |
| Conditional/skipped stages break contract validation | Low | Medium | The `is_active` flag on Stage ABC handles this — disabled stages skip contract checks entirely. |
| `TEMPER_FEEDBACK_ENABLED` conflicts with `TEMPER_DRC_FENCE_FAIL` | Low | Low | Both are independent env vars read at runtime; no interaction. |

## Dependencies

- `CongestionHeatmap` from `routing/congestion_heatmap.py` — existing, used by U1 and U3
- `RoutingFeedbackLoss` from `pipeline/feedback.py` — existing, extended by U3
- `ConvergenceCriteria` from `pipeline/convergence.py` — existing, extended by U4
- `Stage` ABC from `deterministic/stages/base.py` — existing, extended by U2
- `is_drc_fence_fail_enabled()` pattern from `deterministic/flags.py` — existing, mirrored by U2

## Verification Checklist

- [ ] `BottleneckReport` round-trips through JSON without loss (including `routed_nets` list)
- [ ] Noise-floor characterization: 5 identical routes on `temper.kicad_pcb`, routability σ measured
- [ ] Stage contract validation raises errors on missing declared writes/reads
- [ ] Disabled stage (`is_active=False`) skips contract checks entirely
- [ ] Contract is a no-op when `TEMPER_FEEDBACK_ENABLED=false`
- [ ] `DeclaredArtifact.output_path` resolved relative to pipeline output directory
- [ ] EWMA `blend()` update separated from `compute_loss()` — blend called once per iteration
- [ ] EWMA blended_grid converges to constant under repeated identical inputs
- [ ] EWMA does not oscillate under alternating inputs
- [ ] Convergence halt fires when a previously-routed net stops routing
- [ ] Convergence halt fires when routed net set is identical for 2 consecutive iterations
- [ ] Convergence continues (does not halt) when ratio is stable but different nets route
- [ ] Fixed `max_iterations` safety cap still applies
- [ ] Loop with feedback enabled on `temper.kicad_pcb` produces routability ≥ single-pass baseline (R6)
