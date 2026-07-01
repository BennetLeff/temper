---
date: 2026-07-01
status: active
depth: deep
source: docs/brainstorms/2026-07-01-ccap-requirements.md
---

# feat: Constraint-Cascade Alternating Projections (C-CAP)

## Summary

C-CAP is a deterministic, non-gradient pre-optimization step that projects randomly initialized component positions onto feasible constraint sets using Dykstra's alternating projection algorithm. After 10–20 cheap projection cycles, all unary hard geometric constraints (zone containment, keepout avoidance, board bounds, HV/LV half-spaces, edge-mounting) are satisfied by construction, eliminating the need for the optimizer to escape gross violations during curriculum phases 1–2. Pairwise constraints (clearance, spacing) are relaxed via a feasibility-pump minimization step. The output positions feed into `PlacementState` as guaranteed-feasible initial positions before the first gradient step.

---

## Problem Frame

Random init (`PlacementState.random_init()`) places 30–50% of components in forbidden zones. The optimizer's Phase 1–2 (spread + feasibility, 37.5% of total training per `optimizer/config.py:387-413`) is primarily spent escaping gross constraint violations that could be deterministically eliminated before the first gradient step. Each Phase 1–2 epoch costs gradient computation, optimizer updates, and overlap resolution on positions that may be meters outside the board.

Starting from a guaranteed-feasible initial state eliminates this waste entirely and should enable a ≥50% reduction in Phase 1–2 epoch count without regression in final wirelength or DRC count.

The `PlacementConstraints` dataclass (`io/config_loader.py:620`) already carries all domain-rule geometry but never reaches initialization. C-CAP is the first constraint-aware initializer building on the constraint-passthrough init plumbing prerequisite.

---

## Scope Boundaries

**In scope:**
- Two new modules: `geometry/projections.py` (projection operators) and `optimizer/ccap.py` (Dykstra loop + feasibility pump)
- Pure JAX projection operators for all unary constraint types (zone, keepout, board edge, HV/LV half-space, edge-mounting, fixed position, manufacturing side)
- Sparse Dykstra correction vector dict keyed by `(component_id, constraint_id)`
- Feasibility-pump relaxation of pairwise constraints with priority tiers (safety-critical → quality)
- 2-cycle oscillation detection with configurable convergence tolerance
- Unresolved-component flagging with blocking-constraint attribution
- Pre-flight validation: zone-keepout compatibility and side-vs-zone overlap check
- Config flag `initialization.pre_project: ccap` with `ccap_max_cycles`, `ccap_convergence_tol`
- Full test suite (property-based, unit, integration) per user requirements
- Mathematical appendix: Dykstra convergence sketch, projection derivations, oscillation definition

**Out of scope:**
- Group-centroid pre-clustering (separate initiative)
- Rotation optimization (C-CAP is position-only)
- Spectral / force-directed initializers (C-CAP feeds into them, does not modify them)
- Constraint-weighted Laplacian (separate initializer)
- Copper-zone / routing-aware projections (geometry-only)
- Incremental constraint updates (full reprojection on every invocation)
- Critical loop / loop area minimization (optimizer owns this)
- Net classification recomputation (uses existing `PlacementConstraints` fields)

---

## Key Technical Decisions

1. **Sparse correction vector dict, not dense array.** Correction vectors are stored in a `dict[tuple[str, str], jnp.ndarray]` keyed by `(component_id, constraint_id)`. Entries exist only for constraint-component pairs where the constraint applies. This avoids dense N×K array allocation for large constraint sets. Vectors are 2-element JAX arrays initialized to `jnp.zeros(2)` on first use. (From requirements §1.)

2. **LV half-space is independently defined, not as HV complement.** The LV half-space is computed as the half-plane containing the LV zone centroid, with its normal pointing away from the HV zone centroid. This produces a convex half-plane and differs from the complement only in the region between zones (which should be empty of components by definition). For N domains, construct N×(N-1)/2 pairwise half-spaces. (From requirements §1, R5 mitigation.)

3. **Minimum-distance epsilon in feasibility pump prevents NaN.** Before computing the pump gradient, add `distance = max(1e-6, sqrt(dx² + dy²))`. This prevents NaN gradients when two components are initialized at identical positions (common with default (0,0) positions for uninitialized components or components placed via a zone centroid that happens to coincide). (From requirements §2, U3 resolution.)

4. **Fixed components are identity-projected and excluded from pump gradients.** `fixed_position=True` components are excluded from both Dykstra projection (identity projection, correction vectors are always zero) and the feasibility pump gradient step (their positions are immutable). They participate in pairwise violation computation as anchor points — the violation gradient is applied solely to movable components. Correction vectors for fixed components are never stored (sparse dict has no entry). (From requirements §2, fixed component interaction.)

5. **Pump priority tiers with sequential convergence.** Pairwise constraints are processed in order: (1) Safety-critical — HV/LV clearance, noise isolation (step size: 0.5mm); (2) Quality — component spacing, group separation, thermal spread (step size: 0.2mm). Proximity-within-groups is deferred to the optimizer. Each tier runs until its violation sum converges (<1% change over 3 iterations) before the next tier activates. (From requirements §2, pump priority tiers.)

6. **Oscillation detection uses 2-cycle pattern.** Triggered by `|pos_t - pos_{t-2}| < tol` AND `|pos_t - pos_{t-1}| > tol * 10` for 2 consecutive 2-step windows. `tol = ccap_convergence_tol` (default 0.01mm). This distinguishes genuine alternating cycles from slow legitimate drift. On detection: flag component as unresolved, continue with best-effort position. (From requirements R1 mitigation.)

7. **Convergence monitoring with hard cap.** Stop when max position delta < `ccap_convergence_tol` (default 0.01mm). Early-exit at `ccap_max_cycles` (default 15) with a warning if not converged. Component ordering heuristic: project most-constrained components first (by number of unary constraints). (From requirements R2 mitigation.)

8. **Post-pump re-projection to maintain feasibility.** After each feasibility-pump step, re-run one unary projection cycle to re-establish feasibility. This is cheap and prevents the pump gradient from pushing components outside zones or into keepouts. (From requirements R3 mitigation.)

9. **Component dimensions passed as explicit parameters.** Projection operators accept `component_half_width` and `component_half_height` as explicit float parameters passed from the netlist at the C-CAP call site. They do NOT look up dimensions from global state internally — keeping projection functions pure and JAX-compatible. For irregular polygons, the bounding box half-extents provide a reasonable first approximation. (From requirements U3 resolution.)

10. **Side-vs-zone pre-flight validation.** For each zone-assigned component, verify that at least 50% of the zone's area overlaps the component's allowed side region. If not, log a warning and use the side constraint as authoritative (overriding zone containment for that component). (From requirements R1 mitigation, side-vs-zone.)

---

## Implementation Units

---

### U1. Create `geometry/projections.py` — Projection Operators

**Goal**: Implement pure JAX projection operators for all unary constraint types as enumerated in the requirements per-constraint-type table.

**Requirements**: SC1, SC5

**Dependencies**: None (uses existing `geometry/polygon.py` for `point_in_polygon_winding`)

**Files**:
- **Create**: `packages/temper-placer/src/temper_placer/geometry/projections.py`
  - `project_onto_zone(point, zone_vertices, half_w, half_h) -> Array` — clamp to polygon interior via nearest-point-on-boundary
  - `project_outside_keepout(point, keepout_rect, half_w, half_h) -> Array` — clamp to nearest edge of complement
  - `project_onto_board(point, margin, board_w, board_h) -> Array` — orthogonal clamp to [margin, dim-margin]
  - `project_onto_half_plane(point, boundary_line, normal_sign) -> Array` — project orthogonally onto boundary line
  - `project_onto_edge_strip(point, board_w, board_h, max_dist, edge) -> Array` — clamp to edge-adjacent strip
  - `project_onto_side(point, board_h, midline, side) -> Array` — manufacturing side clamp
  - `identity_projection(point) -> Array` — pass-through for fixed positions
  - `nearest_point_on_polygon(point, vertices) -> Array` — helper: sweep edges, find nearest point on boundary
  - `nearest_point_on_segment(point, a, b) -> Array` — helper: project onto line segment with parametric t clamped to [0,1]
- **Modify**: `packages/temper-placer/src/temper_placer/geometry/__init__.py` — export new module symbols

**Approach**:
- All functions are pure: inputs are JAX arrays, outputs are JAX arrays. No global state, no side effects.
- `project_onto_zone` uses `point_in_polygon_winding` from `geometry/polygon.py:149` for detection. If inside → identity. If outside → `nearest_point_on_polygon` which sweeps all polygon edges calling `nearest_point_on_segment` for each edge, selecting the minimum-distance point.
- `project_outside_keepout` handles the complement of an axis-aligned rect. Compute the nearest point on each of the 4 edges of the keepout rect, displaced outward by the component half-size. Select the minimum-distance projection.
- `project_onto_half_plane` for HV: `y >= boundary` → if violating (`y < boundary`), project to `y = boundary`. LV is opposite sign. Multi-domain: construct pairwise half-spaces, normal points from domain A centroid to B centroid.
- `project_onto_edge_strip`: for each of the 4 board edges, compute the nearest point within the edge-adjacent strip (distance from edge ≤ `max_distance_from_edge_mm`). Allow the component to be positioned at any of the 4 edge strips; select the nearest.
- `project_onto_side`: if `side == "top"`, clamp y to `y <= midline`; if `"bottom"`, clamp y to `y >= midline`. Uses `board_midline = board_height_mm / 2`.
- `identity_projection`: `return point` — no-op. For use in the projection dict where a constraint is trivially satisfied.
- `nearest_point_on_polygon`: iterates over polygon edges via `jax.lax.fori_loop`, calling `nearest_point_on_segment(p, vertices[i], vertices[(i+1) % n])` for each edge. Returns the point with minimum Euclidean distance.
- `nearest_point_on_segment`: computes parameter `t = clamp(dot(p-a, b-a) / |b-a|², 0, 1)`, returns `a + t * (b - a)`. Handles degenerate segments (|b-a| → 0) by returning `a`.

**Test scenarios** (for U8 `test_projections.py`):
- Point inside axis-aligned rect: `project_onto_zone` returns identity
- Point outside axis-aligned rect: clamped to nearest edge
- Point inside keepout rect: `project_outside_keepout` displaces to nearest external point
- Point outside keepout rect: identity
- HV component below LV boundary: `project_onto_half_plane` moves it to boundary
- LV component above LV boundary: identity
- Component near board edge: `project_onto_edge_strip` clamps to edge strip
- Component at board center: `project_onto_edge_strip` moves to nearest edge strip
- Fixed component: `identity_projection` returns unchanged position

**Verification**: `pytest packages/temper-placer/tests/unit/test_projections.py -v` passes. All operators are idempotent: `P(P(x)) == P(x)`.

---

### U2. Create `optimizer/ccap.py` — Dykstra Loop + Feasibility Pump

**Goal**: Implement the main C-CAP algorithm: Dykstra alternating projections for unary constraints, feasibility-pump relaxation for pairwise constraints, oscillation detection, and unresolved-flagging.

**Requirements**: SC1, SC2, SC3, SC5, SC6

**Dependencies**: U1

**Files**:
- **Create**: `packages/temper-placer/src/temper_placer/optimizer/ccap.py`
  - `CcapConfig` dataclass: `max_cycles: int = 15`, `convergence_tol: float = 0.01`, `safety_step_size: float = 0.5`, `quality_step_size: float = 0.2`, `pump_convergence_ratio: float = 0.01`, `pump_convergence_window: int = 3`
  - `CcapResult` dataclass: `positions: Array`, `unresolved: list[dict]`, `pairwise_violations_mm: float`, `cycles_run: int`, `converged: bool`, `oscillation_detected: bool`
  - `project_to_feasible(positions, netlist, board, constraints, config) -> CcapResult` — main entry point
  - `_build_projection_schedule(netlist, board, constraints) -> dict` — build per-component ordered projection list
  - `_dykstra_cycle(positions, schedule, correction_dict, netlist) -> tuple[Array, dict]` — single Dykstra pass
  - `_feasibility_pump_step(positions, netlist, constraints, tier_config) -> Array` — pairwise violation minimization
  - `_detect_oscillation(position_history, tol) -> dict[str, bool]` — 2-cycle detection per component
  - `_flag_unresolved(positions, schedule, constraints) -> list[dict]` — identify impossible components
  - `_validate_zone_keepout_compatibility(constraints) -> list[str]` — pre-flight check
  - `_validate_side_zone_overlap(netlist, board, constraints) -> list[str]` — pre-flight check
  - `_compute_pairwise_violations(positions, netlist, constraints) -> tuple[Array, float]` — per-component violation accumulation

**Approach**:

**Dykstra loop** (`_dykstra_cycle`):
```
for each component c (ordered by constraint count, most-constrained first):
    for each unary constraint k on c:
        correction = stored_correction.get((c_id, k_id), jnp.zeros(2))
        p = position[c] + correction
        q = project_k(p, half_w, half_h)
        stored_correction[(c_id, k_id)] = p - q
        position[c] = q
```
- The correction dict is sparse and mutable (Python `dict`) — JAX arrays are read/written per cycle, but no JIT barrier prevents dict mutation since cycles are pure Python loops.
- Fixed components are skipped (identity projection; no correction entry created).
- Component ordering: sort by number of applicable unary constraints descending. This heuristic stabilizes most-constrained components first.

**Feasibility pump** (`_feasibility_pump_step`):
```
for tier in [safety_critical, quality]:
    converged = False
    while not converged:
        accumulated = jnp.zeros((N, 2))
        violation_sum = 0.0
        for each pairwise constraint in tier:
            dist = max(1e-6, norm(position[ci] - position[cj]))
            violation = max(0, min_dist - dist)
            if violation > 0:
                direction = (position[ci] - position[cj]) / dist
                gradient_i = direction * violation
                gradient_j = -direction * violation
                accumulated[c_i] += gradient_i
                accumulated[c_j] += gradient_j
                violation_sum += violation
        position -= step_size * accumulated  # fixed components masked out
        converged = |violation_sum_prev - violation_sum| / violation_sum_prev < 1%
```
- Safety-critical tier: HV/LV clearance, noise isolation (step_size=0.5mm).
- Quality tier: component spacing, group separation, thermal spread (step_size=0.2mm).
- Proximity-within-groups is skipped (deferred to optimizer).
- After each pump step, run one `_dykstra_cycle` to re-establish unary feasibility.
- Fixed component mask: `accumulated = accumulated * movable_mask[:, None]`.

**Oscillation detection** (`_detect_oscillation`):
- Per component: maintain last 4 positions in a circular buffer.
- Check 2-cycle pattern: `|pos_t - pos_{t-2}| < tol` AND `|pos_t - pos_{t-1}| > tol * 10`.
- Must be true for 2 consecutive 2-step windows to trigger.
- Returns `dict[component_id, bool]` — components flagged as oscillating.

**Unresolved flagging** (`_flag_unresolved`):
- After Dykstra completes (converged or max cycles), for each component, verify that all unary constraints are satisfied within `tol * 5` (5× convergence tolerance, to account for floating-point near-misses).
- For components where at least one constraint is violated, find the blocking constraint with the largest violation distance.
- Return `[{"component": ref, "blocking_constraint": constraint_id, "best_distance_mm": dist}, ...]`.

**Pre-flight validation** (`_validate_zone_keepout_compatibility`, `_validate_side_zone_overlap`):
- Zone-keepout: for each keepout, check if any zone assignment maps a component-ref to a zone whose bounding box fully overlaps the keepout. If yes, warn. If zone interior is entirely subsumed by keepout geometry, flag as error.
- Side-zone: for each zone-assigned component with a manufacturing side constraint, compute the fraction of zone area on the allowed side (zone_height_on_side / zone_total_height). If < 50%, log warning and emit an override mapping: that component's zone constraint is replaced by the side constraint.

**Main entry point** (`project_to_feasible`):
```python
def project_to_feasible(
    positions: Array,        # (N, 2) from random init
    netlist: Netlist,
    board: Board,
    constraints: PlacementConstraints,
    config: CcapConfig,
    rng_key: Array | None = None,
) -> CcapResult:
```
1. Run pre-flight validation; log warnings.
2. Build projection schedule from constraints.
3. Run Dykstra loop (up to `max_cycles`), checking convergence and oscillation each cycle.
4. Run feasibility pump (two tiers) after Dykstra, with post-pump re-projection.
5. Flag unresolved components.
6. Return `CcapResult` with final positions, unresolved list, pairwise violation sum, convergence status.

**Config flag**: `config.initialization.ccap_enabled = True` triggers C-CAP in `initialize_training_state()`. Alternatively, `config.initialization.pre_project = "ccap"` as a forward-looking field on `InitializationConfig`. The plan uses `ccap_enabled` for v1 simplicity.

**Test scenarios** (for U9 `test_ccap.py`):
- Dykstra invariants (PBT): correction vectors converge monotonically (norm never increases)
- Dykstra invariants (PBT): projection onto a convex set is idempotent: P(P(x)) = P(x)
- Unit: zone containment projection with known input/output
- Unit: keepout avoidance projection with known input/output
- Unit: HV half-space projection with known input/output
- Unit: board-edge projection with known input/output
- Integration: full C-CAP pipeline on golden board, verify unary feasibility ≥ 95%
- Integration: deterministic output for fixed seed
- Synthetic conflict: oscillating constraint triggers unresolved flagging
- Oscillation detection: synthetic 2-cycle → detected, slow drift → not detected, convergence → correctly identified
- Pairwise: pump gradient direction is always away from the violating component
- Pairwise: NaN avoidance when components share initial position
- Pre-flight: zone-keepout overlap emits warning
- Pre-flight: side-zone <50% overlap logs warning and overrides
- Graceful degradation: `ccap_enabled=False` → byte-identical to current random init

**Verification**: `pytest packages/temper-placer/tests/unit/test_ccap.py packages/temper-placer/tests/integration/test_ccap.py -v` passes.

---

### U3. Add C-CAP Config Fields to `InitializationConfig`

**Goal**: Add `ccap_enabled`, `ccap_max_cycles`, `ccap_convergence_tol` to `InitializationConfig` in `optimizer/config.py`.

**Requirements**: SC6

**Dependencies**: None

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/optimizer/config.py`
  - Add to `InitializationConfig`:
    - `ccap_enabled: bool = False`
    - `ccap_max_cycles: int = 15`
    - `ccap_convergence_tol: float = 0.01`

**Approach**:
- Simple dataclass field additions with conservative defaults (disabled by default for backward compat).
- Default `False` ensures SC6 (byte-identical behavior when disabled).
- `ccap_max_cycles = 15` per requirements U4.
- `ccap_convergence_tol = 0.01` (0.01mm) per requirements U4.

**Verification**: Existing tests pass unchanged. `OptimizerConfig()` constructs without error.

---

### U4. Wire C-CAP into `initialize_training_state()`

**Goal**: Call `ccap.project_to_feasible()` after constraint-passthrough plumbing and random init, before existing initializer selection, in `optimizer/train.py:286`.

**Requirements**: SC1, SC2, SC6

**Dependencies**: U1, U2, U3

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/optimizer/train.py`
  - After `PlacementState.random_init()` block (lines 349-358) and before rotation logit init, insert:
    ```python
    if config.initialization.ccap_enabled:
        from temper_placer.optimizer.ccap import project_to_feasible, CcapConfig
        from temper_placer.io.config_loader import PlacementConstraints

        ccap_cfg = CcapConfig(
            max_cycles=config.initialization.ccap_max_cycles,
            convergence_tol=config.initialization.ccap_convergence_tol,
        )
        result = project_to_feasible(
            positions=positions,
            netlist=netlist,
            board=board,
            constraints=constraints,  # from constraint-passthrough plumbing
            config=ccap_cfg,
            rng_key=rng_key,
        )
        positions = result.positions
        logger.info(
            "C-CAP: converged=%s, cycles=%d, unresolved=%d, pairwise_violations=%.2fmm",
            result.converged, result.cycles_run, len(result.unresolved),
            result.pairwise_violations_mm,
        )
        if result.unresolved:
            logger.warning("C-CAP unresolved components: %s", result.unresolved)
    ```
  - The `constraints` parameter is provided by the constraint-passthrough init plumbing (hard dependency per requirements). Without it, C-CAP is silently skipped.

**Approach**:
- The call site sits between random init and the existing initializer selection (`if config.initialization.method == "spectral"` block).
- This order (C-CAP → spectral) guarantees feasibility first, then spectral can redistribute within zones. Matches requirements U2 recommendation.
- `PlacementConstraints` is the existing dataclass from `io/config_loader.py:620` — all domain-rule geometry is accessed through its fields.
- If constraint-passthrough plumbing is not yet merged (`constraints` parameter absent), C-CAP is skipped with a debug log.
- The `rng_key` parameter is passed through to C-CAP for reproducibility (seed is derived from `config.seed`).

**Verification**: Integration test with `ccap_enabled=True` on golden board shows C-CAP log output and improved initial feasibility. `ccap_enabled=False` produces identical positions to baseline.

---

### U5. Add `nearest_point_on_polygon` Helper to `geometry/polygon.py`

**Goal**: Add a nearest-point-on-polygon-boundary helper to the existing polygon module, used by `project_onto_zone`.

**Requirements**: SC1

**Dependencies**: None

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/geometry/polygon.py`
  - Add `nearest_point_on_polygon(point: Array, vertices: Array) -> Array`
  - Add `nearest_point_on_segment(point: Array, a: Array, b: Array) -> Array`

**Approach**:
- `nearest_point_on_segment`: compute `t = jnp.clip(jnp.dot(point - a, b - a) / jnp.maximum(jnp.sum((b - a)**2), 1e-10), 0.0, 1.0)`, return `a + t * (b - a)`.
- `nearest_point_on_polygon`: iterate over all edges, call `nearest_point_on_segment` for each, return the point with minimum distance. Uses `jax.lax.fori_loop` for JAX compatibility (or a vectorized scan over edges for small polygons).
- Both functions are pure JAX-compatible. Uses existing import patterns (JAX arrays).
- Alternative implementation (vectorized): For N edges, compute t for all edges simultaneously via broadcasting `(N, 2)` edge arrays, clamp, compute nearest points, then select minimum-distance via `jnp.argmin`.

**Verification**: Unit test with known polygon and external point verifies correct nearest boundary point.

---

### U6. Mathematical Appendix in `docs/`

**Goal**: Document the mathematical basis of C-CAP for traceability and review.

**Requirements**: Mathematical Basis (user requirement)

**Dependencies**: U1, U2

**Files**:
- **Create**: `docs/solutions/ccap-mathematical-basis.md` (or inline in plan appendix)

**Approach**:
- Section 1: Dykstra's algorithm convergence proof sketch for convex sets (Boyle & Dykstra, 1986): projection operators are firmly non-expansive; the sequence of iterates converges weakly to a point in the intersection of closed convex sets; correction vectors ensure no "undoing" of prior constraints. Formal statement: for closed convex sets C₁, ..., Cₖ with non-empty intersection, Dykstra's iterates converge to a point in ⋂Cᵢ.
- Section 2: Feasibility pump relaxation — derive the gradient of sum-of-squared pairwise violations: `L = Σ max(0, d_min - ||p_i - p_j||)²`. Gradient ∂L/∂p_i = Σ_j 2(p_i - p_j) · max(0, d_min - ||p_i - p_j||) / ||p_i - p_j|| (for violating pairs). The gradient direction is always away from the violating component.
- Section 3: Projection formula derivations:
  - Point-to-half-plane: `proj_{ax+by≥c}(p) = p + max(0, c - (a·p_x + b·p_y)) / (a² + b²) · (a, b)`
  - Point-to-polygon: winding number test for inclusion; if outside, nearest point = argmin_{e∈edges} nearest_point_on_segment(p, e)
  - Point-to-line-segment: `t = clamp(⟨p-a, b-a⟩ / ||b-a||², 0, 1)`, result = `a + t(b-a)`
- Section 4: 2-cycle oscillation detection — formal definition. A component oscillates if ∃t: ||p_t - p_{t-2}|| < ε AND ||p_t - p_{t-1}|| > 10ε for two consecutive 2-step windows. Convergence tolerance ε = ccap_convergence_tol.

**Verification**: Manual review by placement optimization team.

---

### U7. Create `tests/unit/test_projections.py` — Projection Operator Unit Tests

**Goal**: Unit tests for each projection operator with known inputs and expected outputs.

**Requirements**: Unit tests (user requirement)

**Dependencies**: U1

**Files**:
- **Create**: `packages/temper-placer/tests/unit/test_projections.py`

**Approach**:
- Test `project_onto_zone`:
  - Point at (5, 5) inside rect [(0,0),(10,10)] → unchanged
  - Point at (15, 5) outside rect → clamped to (10, 5)
  - Point at (5, 15) outside rect → clamped to (5, 10)
  - Point at (-5, 5) outside rect → clamped to (0, 5)
  - Point with component half-size (2, 2): clamped to (2, 5) instead of (0, 5)
- Test `project_outside_keepout`:
  - Point at (5, 5) inside keepout [(0,0),(10,10)] with half-size (0,0) → nearest edge (10, 5) or (0, 5) or (5, 0) or (5, 10), whichever is closest
  - Point at (15, 5) outside keepout → unchanged
  - Point on keepout edge (10, 5) → unchanged (on boundary)
- Test `project_onto_half_plane`:
  - HV component at y=10 with boundary at y=20 → projected to y=20
  - LV component at y=10 with boundary at y=0 → unchanged (above boundary)
- Test `project_onto_board`:
  - Position at (50, 50) on 100×100 board, margin=3 → unchanged
  - Position at (-1, 50) → clamped to (3, 50)
  - Position at (102, -5) → clamped to (97, 3)
- Test `project_onto_edge_strip`:
  - Max distance 20mm, board 100×100, edge="bottom" — nearest point in strip [0,100]×[0,20]
- Test all projections are idempotent: `P(P(x)) == P(x)` within float tolerance
- Test identity projection: `identity_projection(x) === x`

**Verification**: `pytest packages/temper-placer/tests/unit/test_projections.py -v` passes all.

---

### U8. Create `tests/unit/test_ccap.py` — C-CAP Core Unit Tests

**Goal**: Unit tests for Dykstra cycle, feasibility pump, oscillation detection, and unresolved flagging.

**Requirements**: Dykstra invariants PBT, feasibility-pump tests, oscillation detection tests (user requirement)

**Dependencies**: U1, U2

**Files**:
- **Create**: `packages/temper-placer/tests/unit/test_ccap.py`

**Approach**:

1. **Property-based tests (Dykstra invariants)** using `hypothesis`:
   ```python
   @given(positions=arrays(float, shape=(5, 2), elements=floats(0, 100)))
   def test_correction_vectors_converge_monotonically(positions):
       """Correction vectors never increase in norm across Dykstra cycles."""
   ```
   - Test with synthetic convex constraint sets (rects, half-planes). Run Dykstra for N cycles, verify `||correction[c][k]||` is non-increasing cycle-over-cycle for each (c, k).

   ```python
   @given(point=arrays(float, shape=(2,), elements=floats(-50, 150)))
   def test_projection_is_idempotent(point):
       """P(P(x)) = P(x) for each projection operator."""
   ```
   - Test with all convex projection operators: `jnp.allclose(proj(proj(p)), proj(p), atol=1e-6)`.

2. **Unit tests (known inputs/outputs)**:
   - `test_zone_containment_projection`: component assigned to zone rect, projected correctly
   - `test_keepout_avoidance_projection`: component inside keepout, projected to nearest external edge
   - `test_hv_half_space_projection`: HV component below boundary, projected to boundary
   - `test_board_edge_projection`: component outside board, clamped to margin

3. **Feasibility-pump tests**:
   ```python
   def test_pump_gradient_direction_away_from_violating_component():
       """Gradient moves components apart, not together."""
       # Place two components at same position (0,0) with min_distance=10mm
       # Gradient for component A should point away from component B
   ```
   ```python
   def test_pump_nan_avoidance_identical_positions():
       """Identical positions don't produce NaN gradients."""
       # Two components at (0,0), min_distance=5mm → no NaN in positions after pump
   ```

4. **Oscillation detection tests**:
   ```python
   def test_detect_2_cycle_oscillation():
       """Synthetic 2-cycle (A→B→A→B) is detected."""
       # Build position history with alternating pattern
   ```
   ```python
   def test_slow_drift_not_detected_as_oscillation():
       """Slow legitimate drift does not trigger oscillation detection."""
       # Incremental drift < tol * 10 between steps
   ```
   ```python
   def test_convergence_correctly_identified():
       """Stable positions identified as converged, not oscillating."""
       # Steady state (moves < tol for 2 consecutive windows)
   ```

5. **Unresolved flagging**:
   ```python
   def test_unresolved_when_zone_and_keepout_conflict():
       """Component assigned to zone that keepout fully covers → flagged."""
   ```
   ```python
   def test_no_unresolved_when_all_constraints_satisfied():
       """All constraints met → empty unresolved list."""
   ```

6. **Graceful degradation**:
   ```python
   def test_disabled_ccap_passthrough():
       """ccap_enabled=False produces identity result on positions array."""
   ```

**Verification**: `pytest packages/temper-placer/tests/unit/test_ccap.py -v` passes all.

---

### U9. Create `tests/integration/test_ccap.py` — End-to-End Integration Tests

**Goal**: Integration test on golden board, A/B comparison, deterministic output, and synthetic conflict testing.

**Requirements**: Integration test (user requirement), SC1, SC3, SC4, SC5

**Dependencies**: U1, U2, U3, U4

**Files**:
- **Create**: `packages/temper-placer/tests/integration/test_ccap.py`

**Approach**:

1. **Full C-CAP pipeline on golden board**:
   ```python
   def test_ccap_unary_feasibility_above_95_percent():
       """After C-CAP, ≥95% components satisfy all unary hard constraints."""
       # Load temper_induction_cooker.yaml config
       # Generate random init positions
       # Run C-CAP
       # For each component: check zone containment, keepout avoidance, board bounds, HV/LV
       # Assert: feasible_count / total_components >= 0.95
   ```

2. **A/B test**:
   ```python
   def test_ccap_vs_baseline_initial_feasibility():
       """C-CAP improves initial feasibility over random init."""
       # Baseline: random init → measure % feasible
       # Variant: random init + C-CAP → measure % feasible
       # Assert: variant feasibility >> baseline feasibility
   ```

3. **Deterministic output**:
   ```python
   def test_ccap_deterministic_for_fixed_seed():
       """Same seed → same positions."""
       # Run C-CAP twice with seed=42
       # Assert: jnp.allclose(run1.positions, run2.positions)
   ```

4. **Synthetic conflict**:
   ```python
   def test_ccap_flags_unresolved_on_conflicting_constraints():
       """Synthetic config with zone overlapping keepout → unresolved flag."""
       # Create tiny board, zone=full board, keepout=full board (conflict)
       # Assert: result.unresolved is non-empty
       # Assert: blocking constraint is correctly identified
   ```

5. **Pairwise violation reduction**:
   ```python
   def test_pairwise_violations_reduced_after_pump():
       """Feasibility pump reduces sum-of-squared pairwise violations."""
       # Measure violations before pump
       # Measure violations after pump
       # Assert: post-pump sum ≤ 50% of pre-pump (per SC2)
   ```

6. **E2E pipeline integration**:
   ```python
   def test_ccap_integrated_into_train():
       """train() with ccap_enabled=True runs without error and produces result."""
       # Run train() with ccap_enabled
       # Assert: TrainingResult returned, no exceptions
   ```

**Verification**: `pytest packages/temper-placer/tests/integration/test_ccap.py -v` passes all.

---

## Deferred Work

| Item | Rationale |
|------|-----------|
| C-CAP + truncated spectral ablation study (U5) | Requires experimental measurement on golden board; not a build-blocker |
| Component ordering heuristic tuning | Empirical measurement of "most-constrained-first" vs round-robin needed |
| Optimal Dykstra cycle count per board size | 15 is a conservative default; tuning requires multi-board benchmark |
| Incremental constraint updates | v1 always reprojects all components; O(constraints × components) is acceptable for sub-second runtime |
| Non-convex polygon zone handling | v1 treats zones as bounding boxes (which zones currently are); convex hull calculation deferred |
| Rotational alignment with edge-mounting | C-CAP is position-only; rotation logits remain uniform |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Dykstra oscillation on incompatible constraints (R1) | Medium | High | 2-cycle detection + pre-flight validation + unresolved flagging; fallback to best-effort position |
| Dykstra convergence too slow on dense boards (R2) | Low | Low | Convergence monitoring with early exit; component ordering heuristic; Temper has ~40 components so O(NK) is trivial |
| Pairwise pump destabilizes unary feasibility (R3) | Medium | Medium | Post-pump re-projection step; small step sizes (0.2–0.5mm); pump violations recorded as hints, not hard requirements |
| C-CAP positions trap optimizer in poor local minima (R4) | Medium | Medium | Optional truncated spectral init after C-CAP before handoff; monitor wirelength regression >5% |
| HV/LV half-space boundary ambiguity (R5) | Low | Low | Multi-domain pairwise half-space construction from zone centroids; Temper has single HV/LV pair |
| Constraint-passthrough plumbing not yet merged | Medium | High | Feature gate: skip C-CAP with debug log if constraints not available; C-CAP is a consumer of constraint-passthrough |
| NaN from identical positions in pump gradient (U3) | Medium | Medium | Minimum-distance epsilon (1e-6) before gradient division; component half-size offset seeding |
| Side-vs-zone conflict on manufacturing constraints | Low | Medium | Pre-flight validation with 50% area overlap check; side constraint as authoritative fallback |

---

## Dependencies

- **Hard dependency**: `docs/brainstorms/2026-07-01-constraint-passthrough-init-requirements.md` — C-CAP cannot receive `PlacementConstraints` until the plumbing passes it through `initialize_training_state()`. Feature gate ensures graceful degradation if not yet merged.
- **Soft dependency**: `docs/brainstorms/2026-07-01-hierarchical-group-preclustering-requirements.md` — Group pre-clustering is complementary; the two can be developed independently and stacked.
- `temper_placer/geometry/polygon.py` — `point_in_polygon_winding` (U1, U5 consume)
- `temper_placer/io/config_loader.py` — `PlacementConstraints` (U2 consumes)
- `temper_placer/optimizer/train.py` — `initialize_training_state()` (U4 modifies call site)
- `temper_placer/optimizer/config.py` — `InitializationConfig` (U3 modifies)
- `temper_placer/core/state.py` — `PlacementState.random_init()` (U4 integrates after)
- `temper_placer/core/netlist.py` — `Netlist` (component dimensions, refs)
- `temper_placer/core/board.py` — `Board` (zones, dimensions)

---

## Verification Checklist

- [ ] `project_onto_zone` correctly clamps to polygon interior; idempotent
- [ ] `project_outside_keepout` correctly displaces to nearest external edge; idempotent
- [ ] `project_onto_half_plane` correctly projects violating points onto boundary
- [ ] `project_onto_board` correctly clamps to [margin, dim-margin]
- [ ] `project_onto_edge_strip` correctly clamps to edge-adjacent strip
- [ ] Dykstra correction vectors converge monotonically (norm never increases) — PBT
- [ ] All projection operators are idempotent: P(P(x)) = P(x) — PBT
- [ ] Pump gradient direction is always away from violating component
- [ ] Pump NaN avoidance: identical positions do not produce NaN
- [ ] Oscillation: synthetic 2-cycle → detected; slow drift → not detected; convergence → correctly identified
- [ ] Unresolved: conflicting zone+keepout → flagged with blocking constraint; no conflicts → empty list
- [ ] Pre-flight: zone-keepout overlap emits warning; side-zone <50% overlap logs warning
- [ ] C-CAP on golden board: unary feasibility ≥ 95% (SC1)
- [ ] Pairwise violations after pump ≤ 50% of random-init value (SC2)
- [ ] No unresolved components on vanilla Temper config (SC3)
- [ ] Training time reduction: Phase 1–2 epochs reduced ≥ 50% without regression (SC4)
- [ ] Deterministic output for fixed seed (SC5)
- [ ] `ccap_enabled=False` → byte-identical to current random init (SC6)
- [ ] `OptimizerConfig()` constructs with default C-CAP fields (no regression)
- [ ] `initialize_training_state()` with C-CAP enabled runs without error
- [ ] `pytest packages/temper-placer/tests/unit/test_projections.py` passes
- [ ] `pytest packages/temper-placer/tests/unit/test_ccap.py` passes
- [ ] `pytest packages/temper-placer/tests/integration/test_ccap.py` passes
- [ ] `uv run python scripts/import_linter_gate.py` passes
- [ ] All existing tests continue to pass (no regression)
