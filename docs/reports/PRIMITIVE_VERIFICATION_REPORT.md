# Primitive Verification Report

**Date**: 2025-12-23
**Status**: Substantially Complete
**Objective**: Establish a rigorous "ground truth" for core geometric, optimization, and routing primitives in `temper-placer`.

## 1. Geometry Primitives (Epic: temper-t76y)

Verified the foundational geometric operations used for collision detection and loss calculation.

| Primitive | Verification Status | Tests |
|-----------|---------------------|-------|
| **AABB Overlap** | ✅ Verified | `test_aabb_overlap_oracle`, `test_rotated_bounds_oracle` |
| **SDF Circle** | ✅ Verified | `test_sdf_circle_oracle` |
| **SDF Rectangle** | ✅ Verified | `test_sdf_rectangle_oracle` |
| **Smooth Max/Min** | ✅ Verified | `test_smooth_max_oracle`, `test_smooth_max_gradient_oracle` |
| **Numerical Stability** | ✅ Verified | `test_smooth_function_extremes`, `test_overlap_distance_zero_separation` |

### Key Findings:
- **Rotated Bounds**: Confirmed that axis-aligned bounding boxes (AABB) for rotated components are conservative (always $\ge$ true bounds) and correctly handle $90^\circ/270^\circ$ swaps.
- **Gradient Continuity**: Verified that `LogSumExp` and `Softplus` approximations maintain finite, continuous gradients even at extreme input values ($x = \pm 100$).
- **Zero Separation**: Confirmed that overlapping components at identical positions produce correct negative distances and gradients that push them apart.

## 2. Optimizer & Initialization (Epic: temper-suhj)

Verified the correctness of placement algorithms and numerical stability guards.

| Primitive | Verification Status | Tests |
|-----------|---------------------|-------|
| **Spectral Init** | ✅ Verified | `test_laplacian_eigenvalues_non_negative`, `test_path_graph_spectral_linearity` |
| **NSGA-II sorting** | ✅ Verified | `test_non_dominated_sort_simple`, `test_nsga2_domination_transitive` |
| **Legalization** | ✅ Verified | `test_no_overlap_after_legalization`, `test_abacus_legalization_oracles` |
| **Force-Directed** | ✅ Verified | `test_force_directed_equilibrium_known`, `test_force_directed_newton_third_law` |
| **Determinism** | ✅ Verified | `test_spectral_init_determinism`, `test_nsga2_determinism` |
| **NaN/Inf Guards** | ✅ Verified | `test_loop_area_nan_position`, `test_overlap_nan_position` |

### Key Findings:
- **Numerical Robustness**: Implemented explicit guards in `CompositeLoss` and individual loss functions. The system now replaces NaN/Inf with large finite penalties, preventing a single unstable component from crashing the entire JAX optimization loop.
- **Graph Embedding**: Confirmed that `SpectralInitializer` correctly embeds path and cycle graphs into linear and circular layouts respectively.
- **Determinism**: Verified that with a fixed PRNG seed, both analytical (Spectral) and stochastic (NSGA-II) methods produce bit-identical results across multiple runs.

## 3. Loss Function Oracles (Epic: temper-83gx)

Verified that complex loss functions correctly penalize violations based on physical ground truth.

| Loss Function | Verification Status | Tests |
|---------------|---------------------|-------|
| **LoopAreaLoss** | ✅ Verified | `test_rectangle_area_oracle`, `test_self_intersecting_polygon_detection` |
| **ThermalLoss** | ✅ Verified | `test_thermal_edge_distance_oracles`, `test_thermal_boundary_conditions` |
| **GridAlignment** | ✅ Verified | `test_grid_alignment_oracles` |
| **Functional Grouping**| ✅ Verified | `test_grouping_diameter_oracles`, `test_thermal_spread_identical_positions` |

### Key Findings:
- **Pin Ordering**: Confirmed that `LoopAreaLoss` requires pins in sequence (CW/CCW). Added a `validate_loop_ordering` heuristic that uses convex hull comparison to detect self-intersecting "figure-8" paths.
- **Thermal Boundaries**: Verified that components touching the board edge correctly return zero distance, while components pushed outside are penalized linearly or quadratically as intended.
- **Clustering**: Confirmed that `GroupClusterLoss` correctly uses the Radius of Gyration (RoG) to provide dense gradients for all components in a group, not just the furthest pair.

## 4. Routing Primitives (Epic: temper-1w8u)

Verified the A* pathfinding and grid occupancy logic used for routability verification.

| Primitive | Verification Status | Tests |
|-----------|---------------------|-------|
| **GridCell Logic** | ✅ Verified | `test_gridcell_equality_reflexive`, `test_neighbors_with_layers` |
| **A* Pathfinding** | ✅ Verified | `test_straight_line_horizontal`, `test_diagonal_manhattan` |
| **Obstacle Avoidance** | ✅ Verified | `test_obstacle_forces_one_step_detour` |
| **Pin Escape** | ✅ Verified | `test_pin_escapes_perpendicular`, `test_corner_pin_escapes` |
| **Multi-layer Routing**| ✅ Verified | `test_crossing_nets_one_uses_via` |

### Key Findings:
- **Layer Transitions**: Confirmed that the router correctly identifies layer change opportunities when nets cross on a single layer.
- **Escape Routes**: Verified that pins are reachable even when located deep inside a component footprint by automatically unblocking "escape paths" toward the component boundary.

## Summary of Test Artifacts

The following test suites have been established as permanent regression guards:

1. `packages/temper-placer/tests/verification/test_geometry_oracles.py`
2. `packages/temper-placer/tests/verification/test_determinism.py`
3. `packages/temper-placer/tests/verification/test_nan_guards.py`
4. `packages/temper-placer/tests/losses/test_loop_area_oracles.py`
5. `packages/temper-placer/tests/losses/test_loss_oracles.py`
6. `packages/temper-placer/tests/routing/test_maze_router_oracles.py`
7. `packages/temper-placer/tests/optimizer/test_spectral_oracles.py`
8. `packages/temper-placer/tests/optimizer/test_force_directed_oracles.py`
9. `packages/temper-placer/tests/optimizer/test_legalization.py`
10. `packages/temper-placer/tests/optimizer/test_nsga2.py`

## 5. Lessons Learned & Numerical Gotchas

During the verification process, several critical failure modes were identified and mitigated:

### The "Figure-8" Loop Trap
- **Issue**: `LoopAreaLoss` uses the Shoelace formula, which computes "algebraic area". If pins are ordered incorrectly (e.g., crossing the loop), the calculated area can be **exactly zero** for a symmetric self-intersecting shape.
- **Impact**: The optimizer sees "zero EMI" for a badly tangled loop and has no gradient to fix it.
- **Mitigation**: Implemented `validate_loop_ordering` which compares Shoelace area to Convex Hull area to detect "imploding" polygons.

### LogSumExp Masking Stability
- **Issue**: Masking invalid elements with large constants (e.g., `1e10`) before `LogSumExp` leads to overflow (`exp(10 * 1e10)`) and `NaN` gradients when alpha is large.
- **Impact**: Immediate optimization crash on nets with varying pin counts.
- **Mitigation**: Confirmed that using `jnp.inf` directly is the only mathematically stable way to mask elements in JAX's `logsumexp`.

### Gradient Poisoning
- **Issue**: In JAX, if a single component produces a `NaN` (e.g., pushed outside the board), that `NaN` propagates through the global sum and destroys the gradients for **all** components.
- **Impact**: The entire optimization loop collapses as soon as one component becomes unstable.
- **Mitigation**: Added `jnp.nan_to_num` guards at the `CompositeLoss` boundary. Unstable components are now assigned a massive finite penalty ($10^6$), allowing the optimizer to "push" them back into safety instead of crashing.

### AABB Approximation Error
- **Issue**: Axis-Aligned Bounding Boxes (AABB) for rotated components are highly conservative. A thin 1x100mm component at 45° creates a 72x72mm "ghost collision" zone.
- **Impact**: Limits maximum density on boards with many diagonal components.
- **Observation**: Future high-density designs will require **Oriented Bounding Boxes (OBB)** or pure **SDF** collision checks.

### Pin Reachability (Escape Routes)
- **Issue**: Blocking the exact footprint of a component makes pins (located inside the footprint) unreachable "islands" for the `MazeRouter`.
- **Mitigation**: Verified that "Escape Routes"—pre-unblocked paths from the pin outward toward the component edge—are mandatory for routing verification.

### NSGA-II Diversity Stagnation
- **Issue**: Crowding distance for Pareto front extremes is `Inf`. If a population has many identical "perfect" solutions, diversity logic can become stagnant.
- **Mitigation**: Adjusted tests to expect and handle these infinite values, and confirmed that the selection operator correctly breaks ties using these distances.
