---
title: "Pattern: Alternating Projections for Hard-Constraint Feasibility Pre-Processing"
date: 2026-07-01
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "Initializing gradient-based placement optimization where randomly-seeded positions violate hard geometric constraints and the optimizer needs a feasible starting point"
  - "Satisfying overlapping unary and pairwise constraints where constraint sets intersect but closed-form joint projection does not exist"
  - "Separating voltage domains (HV/LV) that must not share a half-space region and require deterministic geometric boundary enforcement"
tags:
  - constraint-satisfaction
  - alternating-projections
  - dykstra-algorithm
  - feasibility-pump
  - jax-projections
  - ccap
  - optimization-init
---

# Pattern: Alternating Projections for Hard-Constraint Feasibility Pre-Processing

## Context

The temper-placer uses gradient-based optimization (Adam) to minimize a
composite loss function over component positions. Before the first optimizer
step, randomly initialized positions routinely violate hard geometric
constraints — zones, keepouts, board edges, voltage-domain half-spaces,
edge-mounting strips, and manufacturing-side boundaries. Without pre-processing,
the optimizer wastes iterations escaping infeasible regions and can become
trapped in poor local minima that satisfy some constraints but not others.

The constraint sets are individually convex (or nearly so), but their
intersection lacks a single closed-form projection. Pairwise constraints
(clearance, proximity) add coupling between components, making joint projection
intractable.

## Guidance

### 1. C-CAP: Deterministic Feasibility Guarantee Before Optimization

The Constraint-Cascade Alternating Projections (C-CAP) step runs before the
main gradient-based optimizer. It projects all component positions onto the
intersection of unary hard-constraint sets using Dykstra's alternating
projection algorithm, then relaxes pairwise constraints via a two-tier
feasibility pump.

```python
# optimizer/train.py:405 — C-CAP is inserted before the initializer
if config.initialization.ccap_enabled and constraints is not None:
    from temper_placer.optimizer.ccap import CcapConfig, project_to_feasible
    result = project_to_feasible(
        positions, netlist, board, constraints, config=ccap_cfg,
    )
```

The result is a `CcapResult` with final positions, convergence status,
oscillation diagnostics, unresolved-component flags, and total pairwise
violation sum.

### 2. Seven Pure JAX Projection Operators

All unary projections are closed-form, pure JAX transforms in a single module:

| Operator | Constraint Set | Operation |
|---|---|---|
| `project_onto_board` | Board interior + margin | Orthogonal clamp to `[margin, dim − margin]` |
| `project_onto_zone` | Zone containment | Winding-number test → edge projection with half-size shrinking for rect zones |
| `project_outside_keepout` | Keepout avoidance | Expand keepout by component half-size, snap to nearest edge |
| `project_onto_half_plane` | HV/LV separation | Orthogonal projection onto horizontal or vertical boundary line |
| `project_onto_edge_strip` | Edge mounting | Clamp to strip of width `max_dist` adjacent to board edge |
| `project_onto_side` | Manufacturing side | Clamp y to `[0, midline)` for top or `[midline, board_h]` for bottom |
| `identity_projection` | Fixed position | Pass-through (no-op) |

Each operator is idempotent (`P(P(x)) = P(x)`) — verified by dedicated
idempotence tests. All accept JAX arrays and return JAX arrays with no side
effects. The zone operator uses a fast-path for 4-vertex axis-aligned
rectangular zones (half-size shrinking by offsetting bounds) and a generic
winding-number path for arbitrary polygon zones.

### 3. Dykstra's Algorithm with Sparse Correction Vectors

Dykstra's algorithm extends alternating projections with correction vectors
that prevent "drift" toward constraints projected earlier in the cycle. Without
corrections, plain alternating projections can undo prior constraints.

```python
# optimizer/ccap.py:490 — one Dykstra cycle
def _dykstra_cycle(positions, schedule, correction_dict, ref_to_idx):
    for ref, proj_list in schedule:
        idx = ref_to_idx[ref]
        pos = positions[idx]
        for constraint_id, proj_fn in proj_list:
            correction = correction_dict.get((ref, constraint_id), jnp.zeros(2))
            p_corrected = pos + correction
            q = proj_fn(p_corrected)
            correction_dict[(ref, constraint_id)] = p_corrected - q
            pos = q
        positions = positions.at[idx].set(pos)
    return positions
```

Correction vectors are stored in a sparse `dict[(component_ref, constraint_id)]`
— not a dense `(N, C, 2)` tensor — because most components are subject to only
2–4 unary constraints. This avoids `O(N * C)` memory where C is the total
number of constraint types across all components.

The schedule is ordered by descending constraint count (most-constrained
components first) so components with many hard constraints converge their
positions before others are placed.

### 4. Two-Tier Feasibility Pump with Prioritization

After unary convergence, the feasibility pump pushes apart component pairs that
violate pairwise minimum-distance constraints. It runs two separate tiers:

- **Safety tier** (`safety_step_size = 0.5 mm`): HV/LV clearance and noise
  isolation. These are safety-critical (arcing, EMC) and receive larger step
  sizes for faster convergence.
- **Quality tier** (`quality_step_size = 0.2 mm`): Component spacing rules,
  group separation, and thermal spread. Smaller step size preserves layout
  quality.

Each pump step accumulates violation gradients, applies the step (masking out
fixed components), then re-projects through Dykstra to re-establish unary
feasibility:

```python
# optimizer/ccap.py:530
def _feasibility_pump_step(positions, netlist, constraints, step_size,
                           ref_to_idx, movable_mask, pump_pairs, schedule,
                           correction_dict):
    accumulated = jnp.zeros_like(positions)
    for i, j, min_dist in pump_pairs:
        delta = positions[i] - positions[j]
        dist = jnp.sqrt(jnp.sum(delta**2))
        dist_safe = jnp.maximum(dist, 1e-6)   # NaN guard
        violation = jnp.maximum(0.0, min_dist - dist)
        direction = jnp.where(dist_sq > 1e-12, delta / dist_safe,
                              jnp.array([1.0, 0.0]))
        accumulated = accumulated.at[i].add(direction * violation)
        accumulated = accumulated.at[j].add(-direction * violation)
    positions = positions + step_size * accumulated * movable_mask[:, None]
    positions = _dykstra_cycle(positions, schedule, correction_dict, ref_to_idx)
    return positions, total_violation
```

The pump converges when the fractional change in total violation drops below
`pump_convergence_ratio` (default 0.01) over `pump_convergence_window`
iterations.

**NaN gradient guard**: The epsilon `1e-6` on distance (`dist_safe`) prevents
division by zero when two components occupy the same position, which would
otherwise produce NaN gradients from `delta / 0.0`.

### 5. 2-Cycle Oscillation Detection

Dykstra can oscillate between two constraint sets when no point satisfies both
(e.g., a zone and a keepout that entirely overlap). A 2-cycle oscillation is
diagnostic of an infeasible constraint configuration:

```python
# optimizer/ccap.py:692
def _detect_oscillation(position_history, tol):
    """Detect 2-cycle: |p_t - p_{t-2}| < tol AND |p_t - p_{t-1}| > 10*tol"""
    for ref, history in position_history.items():
        if len(history) < 4:
            continue
        p0, p1, p2, p3 = history[-4:]
        w1_close = norm(p3 - p1) < tol
        w1_far   = norm(p3 - p2) > tol * 10
        w2_close = norm(p2 - p0) < tol
        w2_far   = norm(p2 - p1) > tol * 10
        oscillating[ref] = (w1_close and w1_far) and (w2_close and w2_far)
```

Two consecutive 2-step windows are required to distinguish true alternation
from slow monotonic drift. A component drifting gradually toward convergence
may move `tol * 10` within one cycle, but it will not return to a prior
position on the next cycle.

### 6. LV Half-Space Defined Independently from HV

High-voltage and low-voltage components are separated by a half-space boundary.
Rather than defining LV as the complement of HV (which makes the constraint set
non-convex), LV has its own independent half-space constraint:

- **HV half-space**: `y >= boundary` (HV zone is north of boundary)
- **LV half-space**: `y <= boundary` (LV zone is south of boundary)

Both are convex half-planes. A component cannot satisfy HV by being assigned to
the LV half-plane, eliminating the non-convex ambiguity.

```python
# projections.py:185
def project_onto_half_plane(point, boundary_line, normal_sign=1.0):
    """normal_sign > 0 → feasible is y >= boundary (HV)"""
    x, y = point[0], point[1]
    if normal_sign > 0:
        new_y = jnp.maximum(y, boundary_line)
    else:
        new_y = jnp.minimum(y, boundary_line)
    return jnp.array([x, new_y])
```

The boundary line is auto-derived from HV and LV zone centroids. If zones
separate more along the x-axis, the boundary is vertical; otherwise horizontal.

### 7. Side-vs-Zone Conflict Detection with Zone-Skipping Override

When a manufacturing side constraint and a zone assignment conflict (e.g., a
component assigned to a zone whose area is mostly on the opposite side), the
pre-flight validator detects this:

```python
# optimizer/ccap.py:227
def _validate_side_zone_overlap(netlist, board, constraints):
    """For each zone-assigned component with side constraint, check that
    >= 50% of the zone area is on the allowed side. If not, return a dict
    mapping component_ref -> side (override)."""
```

The returned override map is consumed by `_build_projection_schedule`: when a
component's ref is a key in the override dict, the ZONE projection is **skipped**
for that component. This prevents oscillation between the side projection
(clamp y to midline) and the zone projection (push back into zone interior).

Without this override, Dykstra would oscillate indefinitely — the side
constraint pulls the component up, the zone pushes it down — and the component
would be flagged as unresolved.

### 8. Unresolved Component Flagging for Designer Review

After Dykstra and the feasibility pump complete, components that still violate
any unary constraint by more than `tol * 5` are flagged:

```python
# optimizer/ccap.py:728
def _flag_unresolved(positions, schedule, ref_to_idx, tol):
    """For each component, find the blocking constraint with largest violation."""
```

Each unresolved entry contains:
- `component`: reference designator
- `blocking_constraint`: constraint ID (e.g., `zone_hv_zone`, `keepout_0`)
- `best_distance_mm`: remaining violation distance

These are logged at WARNING level and returned in `CcapResult.unresolved` for
the UI to surface to the designer. A component flagged as unresolved indicates
a constraint configuration that may need manual adjustment.

## Consequences

- **Guaranteed unary feasibility**: After Dykstra, every component satisfies
  all hard geometric constraints to within convergence tolerance. The optimizer
  never sees a position outside a zone or inside a keepout.
- **Deterministic output**: Same initial positions + same constraints = same
  result. No entropy source in C-CAP (the `rng_key` parameter is reserved for
  future perturbation).
- **Idempotent operators**: Each projection is idempotent independently and
  chain-idempotent after Dykstra convergence.
- **Fast convergence**: Default 15-cycle max with 0.01 mm tolerance typically
  converges in 5–8 cycles for real designs.
- **Diagnosable infeasibility**: Oscillation detection + unresolved flagging
  gives actionable feedback when constraints conflict.

## Coverage

- **65 projection tests**: Per-operator correctness, idempotence, half-size
  expansion, winding-number inside/outside, edge-case bounds
  (`test_projections.py`)
- **19 core algorithm tests**: Correction-vector monotonicity, pump gradient
  direction, oscillation detection (2-cycle vs. slow drift vs. convergence),
  NaN avoidance, side-zone override, fixed-component invariance,
  deterministic output, simple-case convergence (`test_ccap.py`)
- **9 integration tests**: Unary feasibility ≥95%, convergence within max
  cycles, feasibility improvement over random, conflicting zone-keepout
  flagging, pump violation reduction, train.py pipeline integration, enabled
  vs. disabled consistency (`test_ccap.py` in `tests/integration/`)
