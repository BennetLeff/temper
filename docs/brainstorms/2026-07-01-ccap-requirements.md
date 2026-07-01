---
date: 2026-07-01
topic: ccap-feasibility-projections
focus: Constraint-Cascade Alternating Projections (C-CAP) — pre-optimization constraint-satisfying initializer
origin: docs/ideation/2026-07-01-placement-init-ideation.md (#3)
status: active
actors: Placement optimizer developer
dependencies:
  - docs/brainstorms/2026-07-01-constraint-passthrough-init-requirements.md
---
# Requirements: Constraint-Cascade Alternating Projections (C-CAP)

## Problem Statement

Current random init places 30–50% of components in forbidden zones (keepouts,
wrong voltage domains, thermal exclusion areas). The `PlacementConstraints`
object in `io/config_loader.py:620` already carries all domain-rule geometry
(zones, keepouts, HV/LV half-spaces, board edges, edge-mounting, fixed
positions) but never reaches initialization. The curriculum's Phase 1–2 (spread
+ feasibility, 37.5% of total training per `optimizer/curriculum.py:42–73`)
is primarily spent escaping gross constraint violations that could be
deterministically eliminated before the first gradient step.

Each Phase 1–2 epoch costs gradient computation, optimizer updates, and overlap
resolution on positions that may be meters outside the board.  Starting from a
guaranteed-feasible initial state eliminates this waste entirely.

The constraint-passthrough init (`docs/brainstorms/2026-07-01-constraint-passthrough-init-requirements.md`)
is the plumbing prerequisite; C-CAP is the first constraint-aware initializer
building on it.

## Proposed Approach

C-CAP starts from random positions and iteratively projects components onto
feasible constraint sets.  After 10–20 cheap projection cycles (no gradients,
no optimizer), all unary hard geometric constraints are satisfied by construction.
The output positions feed into `PlacementState` as guaranteed-feasible initial
positions, replacing random init.

### Architecture

#### 1. Unary Constraints → Hard Projection (Dykstra's Algorithm)

Unary constraints act on a single component independently.  Each constraint
defines a closed convex set in R²; the projection operator maps a point to the
nearest point in that set. The LV half-space is defined independently — not as the complement of the HV half-space (which would be non-convex). It is computed as the half-plane containing the LV zone centroid, with its normal pointing away from the HV zone centroid. This produces a convex half-plane and differs from the complement only in the region between zones (which should be empty of components by definition).

Dykstra's alternating projections (Boyle & Dykstra, 1986) extends von Neumann
alternating projections with **correction vectors**.  Each projection stores
"how far did I move this component?" and subsequent projections correct rather
than undo:

```
for each iteration:
    for each component c:
        for each unary constraint k on c:
            correction = stored_correction[c][k]
            p = position[c] + correction
            q = project_k(p)
            stored_correction[c][k] = p - q
            position[c] = q
```

**Implementation note:** Correction vectors are stored in a `dict[tuple[str, str], jnp.ndarray]` keyed by `(component_id, constraint_id)`. The dict is sparse — entries exist only for constraint-component pairs where the constraint applies. Unapplied constraints have no entry. Vectors are 2-element JAX arrays initialized to `jnp.zeros(2)` on first use. This avoids dense N×K array allocation for large constraint sets.

This handles ordering-dependence:  Component A projected away from keepout,
then B projected away from A's old position — the correction vector on B
preserves A's constraint satisfaction.  The corrections converge to a
fixed-point solution where all constraints are simultaneously satisfied
(or oscillate — see Risks).

#### 2. Pairwise Constraints → Feasibility-Pump Relaxation

Pairwise constraints involve two components (clearance, proximity, group
separation).  Hard projection of pairwise constraints is NP-hard—minimum
separation with variable positions reduces from the disk-packing problem (see Demaine, Fekete, & Lang, "Circle Packing is NP-hard", 2005).  Instead, C-CAP relaxes them into a
**violation-minimization step** at the end of each projection round:

```
after unary projection round completes:
    for each pairwise constraint (c_i, c_j, min_dist):
        violation = max(0, min_dist - distance(c_i, c_j))
        accumulated_violation[c_i] += violation
        accumulated_violation[c_j] += violation

    for each component c with accumulated_violation > 0:
        position[c] -= step_size * gradient_of_violation(c)
```

Before computing the pump gradient, add a minimum-distance epsilon: `distance = max(1e-6, sqrt(dx² + dy²))`. This prevents NaN gradients when two components are initialized at identical positions (common with default (0,0) positions for uninitialized components or components placed via a zone centroid that happens to coincide).

Components minimize sum-of-squared pairwise violations in an M-by-N
feasibility-pump step (Fischetti et al., 2005 — hard single-variable projection
+ soft pairwise relaxation).  The quantified slack is recorded in the output as
`pairwise_violations_mm`, which the optimizer sees and can prioritize in early
curriculum phases.

**Fixed component interaction:** `fixed_position=True` components are excluded from both Dykstra projection (identity projection, correction vectors are always zero) and the feasibility pump gradient step (their positions are immutable). They participate in pairwise violation computation as anchor points — the violation gradient is applied solely to movable components. Correction vectors for fixed components are never stored (sparse dict has no entry).

#### 3. Hard Guarantee with Visibility

Components that **cannot** satisfy all unary constraints after projection (e.g.,
component assigned to zone A but all positions in zone A are blocked by keepouts,
edge-mounting required but board too small) are NOT silently accepted.  They are
flagged in the output:

```python
unresolved: list[dict[str, str | float]] = [
    {"component": "U1", "blocking_constraint": "keepout_rect[2]",
     "best_distance_mm": 3.2},
    ...
]
```

The designer can resolve conflicting constraints (e.g., expand zone A, remove
overlapping keepout) before optimization runs.  The optimizer starts with
`fixed_components` excluding the unresolved ones, so they remain at their
best-effort positions and still participate in pairwise relaxation.

### Per-Constraint-Type Projection Formulas

| Constraint type | Constraint set | Projection operator |
|---|---|---|
| **Zone containment** | Convex polygon / axis-aligned rect | `point_in_polygon_clamp`: if inside → identity; if outside → nearest point on polygon boundary (`geometry/polygon.py:149` `point_in_polygon_winding` for detection, then nearest-point-on-segment sweep over polygon edges) |
| **Keepout region** | Complement of axis-aligned rect | `nearest_point_outside_rect`: clamp (x, y) to the nearest edge of the keepout rect, displaced outside by component half-size |
| **Board edge** | [margin, W-margin] × [margin, H-margin] | `orthogonal_projection_onto_rect`: clamp each coordinate independently to [margin, dim - margin] |
| **HV half-space** | Half-plane (e.g., y ≤ y_isolation - clearance/2) | `half_plane_projection`: if violates → project orthogonally onto the half-plane boundary line |
| **LV half-space** | Complement of HV half-plane | Same operator, opposite sign |
| **Edge-mounting** | Strip within `max_distance_from_edge_mm` of a board edge | `nearest_point_in_edge_strip`: clamp to the edge-adjacent strip |
| **Fixed position** | Single point | `identity_projection` (component is fixed; constraint is trivially satisfied) |
| **HV-LV clearance** (pairwise) | Pairwise separation ≥ hv_clearance_mm | Feasibility-pump: squared violation gradient |
| **Component spacing** (pairwise) | Pairwise separation ≥ min_separation_mm | Feasibility-pump: violation term in minimization step |
| **Group separation** (pairwise) | All pairs across groups ≥ min_distance_mm | Feasibility-pump: violation on all cross-group pairs |
| **Noise isolation** (pairwise) | Sensitive-to-noise-source distance ≥ min_distance_mm | Feasibility-pump |

### Integration Point

```
initialize_training_state()         (optimizer/train.py:286)
  ├── constraint passthrough       (already plumbed: constraints= parameter)
  └── C-CAP pre-processing (NEW)
       ├── Dykstra projection loop   (unary hard constraints → feasible positions)
       ├── Feasibility-pump step     (pairwise → violation-minimized positions)
       ├── Unresolved constraint flagging
       └── Write positions into PlacementState
            └── Fall through to existing initializer selection (random/spectral/force-directed
                as configured — the positions are already feasible so the initializer
                is a no-op or a minor refinement)
```

With C-CAP active, `initial_state` is populated pre-optimization.  The existing
code path at `train.py:311` (`if initial_state is not None`) directly uses those
positions.

## Success Criteria

1. **SC1 — Feasibility rate.**  After C-CAP (10–20 cycles), ≥ 95% of components
   satisfy all unary hard constraints (zone containment, keepout avoidance, board
   bounds, HV/LV half-space).  Measured on the golden Temper induction cooker board
   (`pcb/temper_agent_optimized.kicad_pcb` with constraints from
   `configs/temper_induction_cooker.yaml`).

2. **SC2 — Pairwise violation reduction.**  After the feasibility-pump pass,
   sum of squared pairwise violations is ≤ 50% of the pre-C-CAP random-init
   value.  (Pairwise is relaxed, not guaranteed — the optimizer still owns
   final pairwise resolution.)

3. **SC3 — No unresolved components on vanilla config.**  The standard Temper
   PCL configuration produces zero unresolved components (zone assignments are
   consistent with keepout geometry).  Unresolved flags are tested via a
   synthetic config with deliberately conflicting constraints.

4. **SC4 — Training time reduction.**  Phases 1–2 curriculum time can be reduced
   by ≥ 50% (epoch count) without regression in final wirelength or DRC count,
   because the optimizer no longer needs to escape gross constraint violations.
   Measured on the golden board with C-CAP vs. without.

5. **SC5 — Deterministic output.**  For fixed `seed`, C-CAP produces identical
   positions across runs.  (The algorithm is deterministic given fixed random init.)

6. **SC6 — Graceful degradation.**  When C-CAP is disabled (`config.initialization.ccap_enabled = False`),
   behavior is byte-identical to current random init — zero regression.

## Scope Boundaries

### In Scope

- **Unary hard constraints** (Dykstra projection):
  - Zone containment (`PlacementConstraints.zones` + `zone_assignments`)
  - Keepout regions (`PlacementConstraints.keepouts`)
  - Board edge / margin (`board_width_mm`, `board_height_mm`, `board_margin_mm`)
  - HV/LV half-space separation (derived from `hv_clearance_mm` and `PlacementConstraints.zones`
    with `net_classes=["HV"]` vs. `["LV"]`)
  - Edge-mounting constraints (`ThermalConstraint.prefer_edge` + `max_distance_from_edge_mm`)
  - Fixed positions (`fixed_positions`)
  - Manufacturing side constraints (`ManufacturingConstraint.side == "top"` → project to `y < midline`)

- **Pairwise relaxed constraints** (feasibility pump):
  - HV-LV clearance (`hv_clearance_mm`)
  - Component spacing rules (`component_spacing_rules`)
  - Group separation (`group_separations`)
  - Noise isolation (`noise_isolation`)
  - Thermal spread (`ThermalProperties.min_separation_mm`)
  - Proximity within component groups (`ComponentGroup.max_spread_mm`)

**Pump priority tiers:** Pairwise constraints in the feasibility pump are processed in order: (1) Safety-critical — HV/LV clearance, noise isolation (larger step size: 0.5mm per iteration); (2) Quality — component spacing, group separation, thermal spread (smaller step size: 0.2mm per iteration). Proximity-within-groups is deferred to the optimizer (it conflicts with the pump's repulsion focus). Each tier runs until its violation sum converges (<1% change over 3 iterations) before the next tier activates.

- **Integration:**
  - New module `geometry/projections.py` containing all projection operators
  - New module `optimizer/ccap.py` containing the Dykstra loop + feasibility pump
  - Call site in `optimizer/train.py:286` `initialize_training_state()` after
    constraint-passthrough plumbing exists
  - Unresolved-constraint flagging data structure
  - Unit tests for each projection operator (point-in-polygon clamp, keepout
    projection, half-plane, edge strip, board-edge clamp)
  - Integration test: C-CAP on golden board, verify 95%+ unary feasibility
  - Synthetic conflict test: verify unresolved flagging

### Rejected Alternatives

**Random-restart with rejection sampling:** Generate N random placements, score each for unary constraint violations, select the best. Rejected because: for a board with 40 components, each subject to 3-5 unary constraints at approximately 50% violation probability per constraint, the probability of a single component being fully feasible is roughly (0.5)⁴ ≈ 6%. For all 40 components to be simultaneously feasible by chance: effectively zero without N > 10⁶. Random-restart handles pairwise constraints not at all. C-CAP's deterministic projection achieves >95% unary feasibility in O(constraints × iterations) without the exponential scaling of random sampling. The practical value of this approach will be validated by measuring the actual random-feasibility rate on the golden board design.

### Out of Scope

- **Group-centroid pre-clustering** (component groups placed at shared centroid, then spread) —
  covered by `docs/brainstorms/2026-07-01-hierarchical-group-preclustering-requirements.md`
- **Critical loop / loop area minimization** — the optimizer owns this via `LoopAreaLoss`
- **Decoupling capacitor placement** — proximity constraints are relaxed, but specific
  pin-to-pin adjacency is the optimizer's job
- **Rotation optimization** — C-CAP operates on center positions only;
  rotation logits remain at uniform initialization
- **Net classification / clearance-class computation** — uses existing `PlacementConstraints`
  fields, does not recompute them
- **Copper zone / routing-aware projections** — C-CAP is geometry-only, not routing-aware
- **Spectral / force-directed initializers** — C-CAP replaces or feeds into them; it does
  not modify them
- **Constraint-weighted Laplacian** — separate initializer
  (`docs/brainstorms/2026-07-01-constraint-weighted-laplacian-requirements.md`)
- **Incremental constraint updates:** C-CAP always projects all components from scratch on invocation. Adding or removing a constraint and re-projecting only affected components is explicitly out of scope for v1. The O(constraints × components) cost of full reprojection is acceptable given C-CAP's sub-second runtime target.

## Classification of Constraint Types

### Unary (per-component, independent)

| Constraint | Source field in `PlacementConstraints` | Geometry |
|---|---|---|
| Zone containment | `zones` + `zone_assignments` | Polygon or rect → clamp to interior |
| Keepout avoidance | `keepouts` | Rect complement → clamp to nearest edge |
| Board edge margin | `board_width_mm`, `board_height_mm`, `board_margin_mm` | Rect → orthogonal clamp |
| HV half-space | `zones` with `net_classes=["HV"]` | Half-plane: y ≥ boundary OR y ≤ boundary |
| LV half-space | `zones` with `net_classes=["LV"]` | Half-plane: opposite sign |
| Edge-mounting | `thermal_constraints[].prefer_edge` | Edge-adjacent strip → clamp to strip |
| Fixed position | `fixed_positions` | Single point → identity (skip projection) |
| Manufacturing side | `manufacturing_constraints[].side` | Top/bottom half → clamp to half |
| Orientation lock | `manufacturing_constraints[].allowed_orientations` | Deferred to rotation init (C-CAP is position-only) |

### Pairwise (component-to-component, relaxed)

| Constraint | Source field in `PlacementConstraints` |
|---|---|
| HV-LV clearance | `hv_clearance_mm` |
| Component spacing | `component_spacing_rules` |
| Group separation | `group_separations` |
| Noise isolation | `noise_isolation` |
| Thermal spread | `thermal_properties.min_separation_mm` |
| Group proximity | `component_groups[].max_spread_mm` |
| Proximity rules | `component_groups[].proximity_rules` |

### Left to Optimizer

| Concern | Reason |
|---|---|
| Loop area minimization | Requires routing topology, not geometry-only |
| Decoupling cap pin adjacency | Pin-level, not component-to-component |
| Wirelength minimization | NP-hard; gradient descent is appropriate |
| Congestion / routability | Requires routing channel analysis |
| Aesthetics (alignment, grid snap) | Post-optimization grooming |
| Rotation selection | Discrete combinatorial choice |
| Differential pair routing | Routing-phase concern |

## Risks

### R1 — Dykstra Oscillation on Incompatible Constraints

**Scenario:** Zone A and keepout K overlap, and component C is assigned to zone
A but must avoid K.  Dykstra oscillates:  projection onto zone A lands inside K,
projection away from K lands outside zone A.

**Likelihood:** Medium — the Temper golden board has no overlapping zone+keepout
pairs by construction, but user-authored PCL may contain conflicts.

**Mitigation:**
1. Oscillation detection as a 2-cycle pattern: `|pos_t - pos_{t-2}| < convergence_tol` AND `|pos_t - pos_{t-1}| > convergence_tol * 10` for 2 consecutive 2-step windows. The convergence tolerance defaults to 0.01mm (using the `ccap_convergence_tol` config parameter, defined in Section Convergence Monitoring). This distinguishes genuine alternating cycles from slow legitimate drift, which would not satisfy the second condition.
2. Pre-flight check: validate that `zone_assignments` are compatible with
   `keepouts` before C-CAP runs — same as `validation/preflight.py` stage.
3. Fallback: unresolved components remain at their last position and get
   flagged with the blocking constraint.
4. **Side-vs-zone validation:** Manufacturing side constraints (`top` → y < board_midline, `bottom` → y ≥ board_midline) can conflict with zone assignments when a zone's interior is entirely on the wrong side of the board. Add a pre-flight validation step: for each zone-assigned component, verify that at least 50% of the zone's area overlaps the component's allowed side region. If not, log a warning and use the side constraint as authoritative (overriding zone containment for that component).

### R2 — Dykstra Convergence Too Slow

**Scenario:** 20+ cycles do not reach fixpoint for dense boards (>100 components)
with many overlapping unary constraints.  Each cycle costs `O(N * K)` where
N = components, K = unary constraints per component.

**Likelihood:** Low for Temper (≈40 components, ≈5 unary constraints each =
200 projections/cycle × 15 cycles = 3,000 projections total — negligible
compared to 8,000 gradient epochs).

**Mitigation:**
1. Convergence monitoring: stop when max position delta < 0.01mm.
2. Early-exit at 20 cycles with a warning if not converged.
3. Component ordering heuristic: project most-constrained components first
   (by number of unary constraints), so their positions stabilize before
   less-constrained components react.

### R3 — Pairwise Relaxation Destabilizes Unary Feasibility

**Scenario:** Feasibility-pump step moves components to reduce pairwise
violations, pushing them outside zones or into keepouts.

**Likelihood:** Medium — the pump step uses a gradient direction, not a
projection, so it may violate unary constraints.

**Mitigation:**
1. Apply the feasibility-pump step with a small step size (0.1–0.5mm).
2. After each pump step, re-run one unary projection cycle (cheap) to
   re-establish feasibility.
3. Record pairwise violation slack as a hint for the optimizer's early
   curriculum phases, rather than trying to fully resolve pairwise.

### R4 — Positions Optimizer Cannot Recover From

**Scenario:** C-CAP places components at constraint-satisfying but topologically
poor positions (e.g., all components squeezed into one corner of a zone to avoid
keepouts).  The optimizer's gradient landscape from these positions leads to
local minima.

**Likelihood:** Medium — the projection operator projects to the *nearest*
feasible point, not the *best* feasible point.

**Mitigation:**
1. Run a truncated spectral init (5–10 iterations) after C-CAP before
   optimizer handoff.  The spectral init has a global view of connectivity
   and can redistribute components within zones while respecting zone bounds.
   (This relates to Unknown U5 below.)
2. Monitor final wirelength vs. non-C-CAP baseline; if regression >5%,
   investigate adding stochastic perturbation within the zone bounds before
   handoff.

### R5 — HV/LV Half-Space Computation Ambiguity

**Scenario:** HV and LV zones are defined as named rectangles, but the half-space
boundary may be diagonal in some designs, or multiple HV zones create a non-convex
safe region.

**Likelihood:** Low for Temper (single HV zone covering the right third of the
board, single LV zone covering the left two-thirds).

**Mitigation — Multi-domain half-space construction:** For N voltage domains, construct N×(N-1)/2 pairwise half-spaces. For each domain pair (A, B), the half-space normal points from A's zone centroid to B's zone centroid. A components are on the positive side; B components remain on the negative side. This generalizes the 2-domain case cleanly. If zones are non-convex polygons, use the convex hull of the zone polygon for centroid computation. If a zone spans both sides of the board, use the zone's largest contiguous sub-polygon.

## Unknowns

- **U1 — Convergence rate on real Temper boards.**  How many Dykstra cycles does
  the golden board need?  10?  20?  50?  The theoretical bound is `O(1/ε)` for
  convex sets, but Temper has non-convex keepout complements.  Empirical
  measurement is the only way to settle this.

- **U2 — Interaction with spectral init.**  Should C-CAP run before or after
  spectral?  C-CAP → spectral means spectral gets feasible starting positions
  and can redistribute within zones.  Spectral → C-CAP means spectral provides
  a good topological layout, then C-CAP snaps to constraint boundaries.
  Recommendation: C-CAP first (guarantees feasibility), then spectral (improves
  topology within feasible region).  This should be experimentally validated.

- **U3 — Component size handling (RESOLVED).**  Projection operators accept `component_half_width` and `component_half_height` as explicit float parameters passed from the netlist component data at the C-CAP call site. They do NOT look up dimensions from global state internally — this keeps projection functions pure and JAX-compatible. The call site in `ccap.py` iterates over netlist components and passes dimensions as function arguments. For irregular polygons, the bounding box half-extents provide a reasonable first approximation.

- **U4 — Optimal cycle count.**  How many Dykstra cycles is "enough" on real
  boards?  Theory says until convergence (max delta < ε).  Practice may find
  that 10 cycles is sufficient for 95% feasibility.  This should be
  configurable: `ccap_max_cycles` with default 15, plus `ccap_convergence_tol`
  with default 0.01mm.

- **U5 — C-CAP + truncated spectral vs. spectral-only.**  Does the sequence
  C-CAP → truncated spectral (10 iters) → optimizer produce better final
  results than C-CAP → optimizer directly?  The spectral step may un-satisfy
  some constraints; should it be followed by another Dykstra round?  Needs
  experimental ablation.

- **U6 — Cost of Dykstra vs. gradient epoch.**  One Dykstra cycle is O(N * K)
  pure Python; one gradient epoch is O(N²) JAX-compiled.  If 15 Dykstra cycles
  costs more than 500 gradient epochs, the tradeoff is questionable.  Benchmark
  needed, but preliminary intuition: 15 × 40 × 5 = 3,000 projection ops, each
  ≈1–10 µs = 3–30ms, vs. 500 gradient epochs at ≈5ms each = 2.5s.  C-CAP is
  clearly cheaper.

## Prior Art

- **Dykstra's algorithm** (Boyle & Dykstra, 1986):  Alternating projections with
  correction vectors for coupled convex constraints.  Standard in signal
  processing (projections onto convex sets) and convex optimization.
- **Feasibility pumps** (Fischetti, Glover, Lodi, 2005):  Mixed-integer
  programming heuristic that alternates between satisfying linear constraints
  (LP solution) and integrality constraints (rounding), adding penalty terms
  for distance between the two.  C-CAP adapts the hard/soft split to
  unary/pairwise.
- **von Neumann alternating projections** (1950):  Theorem that alternating
  orthogonal projections onto two closed subspaces converges to the
  intersection.  Generalizes to convex sets (via Bregman, 1965; Censor &
  Elfving, 1994).
- **Projected gradient descent** in the optimizer (`optimizer/train.py`):  The
  optimizer already does projected gradient for boundary constraints via
  `boundary_loss`.  C-CAP is a dedicated pre-optimization step that does this
  faster because it doesn't compute gradients over all loss terms.

## Code Impact (Preliminary)

| File | Change |
|---|---|
| `geometry/projections.py` | **New.**  Per-constraint-type projection operators (zone clamp, keepout avoidance, board-edge clamp, half-plane, edge-strip) as pure JAX functions. |
| `optimizer/ccap.py` | **New.**  Dykstra loop, feasibility-pump step, oscillation detection, unresolved-flagging.  Imports `projections.py` and `PlacementConstraints`. |
| `optimizer/train.py` | Call `ccap.project_to_feasible(positions, constraints, netlist)` after constraint-passthrough plumbing exists, before existing initializer selection.  Populate `InitializationConfig` with `ccap_enabled`, `ccap_max_cycles`, `ccap_convergence_tol`. |
| `optimizer/config.py` | Add `ccap_enabled: bool = False`, `ccap_max_cycles: int = 15`, `ccap_convergence_tol: float = 0.01` to `InitializationConfig`. |
| `optimizer/initialization.py` | C-CAP function may be registered as a callable init step or exposed as a standalone pre-processing function; TBD based on how the constraint-passthrough init plumbing is finalized. |
| `geometry/polygon.py` | May add `nearest_point_on_polygon()` helper if not already present (currently has `point_in_polygon_winding` and `point_in_polygon_soft`). |
| `tests/unit/test_projections.py` | **New.**  Unit tests for each projection operator with known inputs/expected outputs. |
| `tests/integration/test_ccap.py` | **New.**  Integration tests: C-CAP on golden board → 95%+ feasibility; synthetic conflict → unresolved flagging; deterministic output. |

## Dependencies

- **Hard dependency:** `docs/brainstorms/2026-07-01-constraint-passthrough-init-requirements.md`
  — C-CAP cannot receive `PlacementConstraints` until the plumbing passes it
  through `initialize_training_state()`.
- **Soft dependency:** `docs/brainstorms/2026-07-01-hierarchical-group-preclustering-requirements.md`
  — Group pre-clustering is a complementary init improvement; the two can be
  developed independently and stacked (pre-cluster, then C-CAP-project each
  cluster centroid, then expand).
