---
title: "Hierarchical Group-Centroid Pre-Clustering for Placement Initialization"
date: 2026-07-01
status: active
depth: deep
source: docs/brainstorms/2026-07-01-hierarchical-group-preclustering-requirements.md
---

## Summary

Build a 4-phase hierarchical pre-clustering initializer that consumes
`PlacementConstraints.component_groups` and injects group-aware starting
positions into `PlacementState` before `GeometricPhase`. The approach
reduces dimensionality from placing N components to placing G super-nodes
(G << N), letting the optimizer start with correct intra-group topology
at epoch 0 instead of rediscovering it through 3000 epochs of
`GroupClusterLoss` gradient descent.

**Phases**: (1) internal force-directed micro-solve per group, (2)
coarsen to super-nodes with aggregated adjacency, (3) global spectral
embedding of coarsened graph, (4) explode super-node positions back to
component positions.

**Configuration trigger**: `config.initialization.group_preclustering:
true` + non-empty `PlacementConstraints.component_groups`. Graceful
degradation when no groups are defined or pre-clustering is disabled.

---

## Problem Frame

`PlacementConstraints.component_groups` (`packages/temper-placer/src/temper_placer/io/config_loader.py:665`)
already encodes designer intent — gate-drive circuits, sense-feedback
paths, matched-length pairs, star-ground clusters — each with
`max_spread_mm`, `proximity_rules`, and `weight`. `GroupSeparation`
constraints (`config_loader.py:225`) encode minimum inter-group
distances.

Yet **none of this reaches initialization**:

| Init path | File | Group awareness |
|---|---|---|
| `SpectralInitializer` | `optimizer/initialization.py:203` | None |
| `TopologicalInitializationHeuristic` | `heuristics/topological_init.py:44` | None |
| `ZoneAwareSpectralInitializer` | `optimizer/zone_aware_init.py:207` | Zone-aware only |
| `compute_force_directed_layout` | `heuristics/force_directed.py:197` | None |

The curriculum activates `grouping: 50.0` at epoch 3000
(`optimizer/curriculum.py:86`) — 37.5% of the 8000-epoch budget is spent
discovering what the config already declares. The gradient must pull
scattered components across the board back into tight clusters.

**Validation hypothesis**: After current spectral init on the Temper
golden board, >= 60% of groups are predicted to have members exceeding
their `max_spread_mm`. This experiment gates whether the 4-phase
approach is justified (see Testing Strategy).

**Actors:**
- **A1. Placement engineer.** Defines `component_groups` in YAML config;
  expects them to be respected from epoch 0.
- **A2. Optimizer developer.** Modifies the initialization path; needs
  clear boundaries between pre-clustering and gradient descent.
- **A3. CI system.** Must verify that pre-clustering produces valid
  starting positions and that the fallback path (no groups) is
  unchanged.

---

## Scope Boundaries

### In Scope

- `HierarchicalGroupInitializer` class in
  `packages/temper-placer/src/temper_placer/optimizer/initialization.py`
- Integration into `OptimizationPipeline` at the TopologicalPhase →
  GeometricPhase transition (`optimizer/phases.py:265`)
- Phase 1: Intra-group micro-placement using `compute_force_directed_layout`
  on sub-adjacency matrices
- Phase 2: Group coarsening — super-node adjacency aggregation and
  dimension tracking
- Phase 3: Global spectral embedding of super-nodes using
  `compute_spectral_coordinates` + `scale_to_board`
- Phase 4: Explosion — mapping super-node centroids + micro-offsets back
  to component positions
- Configuration flag `group_preclustering: bool` in
  `InitializationConfig`
- Spanning-group detection (threshold at 30% board diagonal)
- Overlapping-group resolution (first-wins assignment with warning)
- Fixed component handling within groups
- Group-internal boundary preservation (shift entire group inward when
  members exceed board bounds post-explosion)

### Deferred (to follow-up work)

- Auto-detection of groups from connectivity topology
- Template groups (`template_group` field on `ComponentGroup`) — may
  benefit from pre-clustering but not addressed here
- Multi-objective NSGA-II diversity seeding
- Hierarchical init as a standalone `Heuristic` in the
  `heuristics/` framework (see Key Decision 4)

### Out of Scope

- Changes to curriculum phases, loss weights, or `GroupClusterLoss` —
  losses continue to work as before (just see near-zero loss from
  epoch 0)
- Changes to `ProximityLoss` or `GroupSeparationLoss`
- Modifications to the YAML config schema — `ComponentGroup`,
  `PlacementConstraints` unchanged
- Zone-aware initialization handling of cross-zone groups (these
  groups are skipped with a warning)

---

## Key Decisions

1. **Force-directed micro-solver for Phase 1 (not spectral).**
   `compute_force_directed_layout` (`heuristics/force_directed.py:197`)
   is already in the codebase, handles proximity naturally via attractive
   forces, and converges fast on small subgraphs (<< 10 iterations for
   groups of < 20 components). Spectral embedding produces linear
   embeddings that don't respect component footprints and may place
   components at coincident positions. The fallback for groups whose
   diameter exceeds `max_spread_mm * 1.2` post-solve is simple radial
   placement (circle at `max_spread_mm / 2` radius).

   **Rationale**: F-R spring model directly minimizes Σ spring_constant ×
   (d_ij − target_distance)² per the mathematical specification. The
   existing `compute_force_directed_layout` signature accepts arbitrary
   `initial_positions`, `board_width`, `board_height`, and a pre-computed
   `weighted_adj` — ideal for sub-graph isolation.

2. **First-wins assignment for overlapping groups.**
   If a component appears in multiple `ComponentGroup` lists, assign it
   to the group with the tighter (smaller) `max_spread_mm` and issue a
   warning for the other. This is a minor refinement of the requirements'
   "first-wins" proposal — prioritizing the stricter constraint is more
   conservative. Track component→group conflicts as a metric; if
   real-world configs need it, escalate to group merging in a follow-up.

3. **Pipeline integration at phases.py:265, not in train.py:317.**
   `OptimizationPipeline.run()` already transitions from `TopologicalPhase`
   to `GeometricPhase` at `phases.py:298-306`. Inserting the
   pre-clustering step here (after TopologicalPhase.SUCCESS, before
   GeometricPhase.run) keeps the init pipeline cleaner than adding yet
   another branch in `train.py:317-354`. The `HierarchicalGroupInitializer`
   reads `constraints.component_groups` directly from the
   `ConstraintCollection` passed to the pipeline.

4. **New initializer class, not a Heuristic.**
   Implement as `HierarchicalGroupInitializer` in
   `optimizer/initialization.py` following the pattern of
   `SpectralInitializer` (dataclass with `initialize(netlist, board,
   constraints)` method). The existing `Heuristic` framework adds
   abstraction but the `PlacementContext` doesn't currently carry
   `component_groups` in a way that suits per-group micro-solving.
   Refactoring into a Heuristic is deferred to follow-up work.

5. **No coarsening for spanning groups (>30% board diagonal).**
   Groups whose `max_spread_mm > 0.3 * sqrt(board.width² + board.height²)`
   are treated as collections of singleton super-nodes. Their members
   receive positions from the standard spectral embedding (or zone
   assignment, or anchor positions for fixed components). A warning is
   logged. The 30% threshold is derived from the condition that a
   group's internal spread must be small relative to board dimensions for
   coarsening to be meaningful — beyond this threshold, collapsing the
   group into a single super-node distorts the global topology more than
   it helps.

---

## Design Details

### Data Flow

```
PlacementConstraints.component_groups
    |                              |
    v                              v
[Phase 1: Per-Group Micro-Solve]  (spanning groups → pass through)
    |  force_directed on sub-adjacency
    |  output: {group_id: relative_offsets (M_i, 2)}
    v
[Phase 2: Coarsen to Super-Nodes]
    |  build G×G aggregated adjacency
    |  output: super_adjacency (G, G), super_sizes (G,)
    v
[Phase 3: Global Spectral Embedding]
    |  compute_spectral_coordinates(super_adjacency)
    |  scale_to_board()
    |  apply GroupSeparation nudges
    |  output: super_centroids (G, 2)
    v
[Phase 4: Explode to Component Positions]
    |  position[i] = centroid[group(i)] + offset[i]
    |  shift-in-bounds for edge groups
    |  _separate_coincident_components()
    |  output: (N, 2) positions
    v
PlacementState.from_positions(positions)
```

### New Configuration

In `packages/temper-placer/src/temper_placer/optimizer/config.py`,
add to `InitializationConfig`:

```python
@dataclass
class InitializationConfig:
    # ... existing fields ...
    group_preclustering: bool = False  # NEW
```

The flag gate:
- `config.initialization.group_preclustering == True` **AND**
- `constraints.component_groups` is non-empty

Both must be true for the pre-clustering path to activate. If either is
false/empty, the pipeline proceeds with standard initialization (spectral,
random, or whatever `config.initialization.method` specifies).

### Phase 1: Intra-Group Micro-Placement

**Module**: `optimizer/initialization.py` — new private method
`_solve_group_micro_layout(group, netlist, sub_adjacency, rng_key)`.

For each `ComponentGroup` in `constraints.component_groups`:

1. **Resolve member indices.** Map `group.components` (list of component ref
   strings) to integer indices via `netlist.get_component_index(ref)`.
   Skip any ref not in the netlist.

2. **Extract sub-adjacency.** Use `build_adjacency_matrix(netlist)` then
   slice with `adj[np.ix_(member_indices, member_indices)]`. This is a
   `(M_i, M_i)` matrix where `M_i = len(member_indices)`.

3. **Initialize micro-positions.** For each member, start from a fixed
   position relative to the group's local origin (0, 0):
   - Fixed components: use their anchor position from
     `constraints.fixed_positions` or `component.fixed` attribute,
     translated to group-local space.
   - Unfixed components: place in a small circle at radius
     `max_spread_mm / 2` from origin, deterministically spaced by angle.
   - **Fixed seed**: Use `jax.random.PRNGKey(group_name_hash)` for
     deterministic initialization.

4. **Run force-directed solve.** Call `compute_force_directed_layout` with:
   - `initial_positions`: the local initialization from step 3
   - `weighted_adj`: the sub-adjacency (edges weighted by net count)
   - `board_width = board_height = max_spread_mm * 2` (a local bounding box
     large enough to contain the group)
   - `iterations`: 200 (higher than default since groups are small)
   - `repulsion_k`: computed from local area / M_i
   - `cooling_factor`: 0.95
   - `initial_temp`: `max_spread_mm / 10`

   Note: `compute_force_directed_layout` uses `jax.jit` on the step
   function, so calling it per group is efficient for small M_i.

5. **Validate and fallback.** Compute the pairwise diameter of the solved
   layout. If `diameter > max_spread_mm * 1.2`, fall back to radial
   placement: arrange components in a circle at radius
   `max_spread_mm / 2`, deterministically spaced.

6. **Handle single-component groups.** Trivially — the relative offset is
   `(0, 0)`.

7. **Handle groups with one fixed component.** The fixed component locks
   to its position; other members arrange around it (the force-directed
   solver handles this via the `fixed_mask` mechanism already in place).

8. **Output**: `dict[int, jnp.ndarray]` mapping `group_id → (M_i, 2)`
   relative offsets from the group's local origin, where `group_id`
   is an integer index for internal tracking.

### Phase 2: Group Coarsening

**Module**: `optimizer/initialization.py` — new private method
`_coarsen_to_super_nodes(component_groups, adjacency, board)`.

1. **Build group assignment map.** Create `component_to_group = [-1] * N`
   where -1 means ungrouped (singleton). For each group's member indices,
   set `component_to_group[idx] = group_id`. Resolve overlaps with the
   first-wins policy (actually "tightest constraint" per Key Decision 2).

2. **Detect spanning groups.** For each group, if
   `max_spread_mm > 0.3 * sqrt(board.width² + board.height²)`:
   - Mark the group as "spanning" — its members are treated as individual
     singleton super-nodes (i.e., set `component_to_group[idx] = -1` for
     each member).
   - Log warning: "Group '{name}' spans >30% of board diagonal ({diagonal:.1f}mm) — coarsening disabled, members placed individually."

3. **Count super-nodes.** `G = num_coarsened_groups + num_ungrouped_components`.
   Maintain a mapping from `super_node_id` (0..G-1) to the set of
   component indices it represents.

4. **Aggregate adjacency.** Build `super_adj = jnp.zeros((G, G))`.
   For each pair of original components `(i, j)` where `adjacency[i, j] > 0`:
   - `gi = component_to_group[i]` (mapped through super-node mapping if
     ungrouped)
   - `gj = component_to_group[j]`
   - If `gi != gj`: `super_adj[gi, gj] += adjacency[i, j]`

   **Proof**: `edge_weight(super_A, super_B) = Σ edge_weight(a_i, b_j)` for
   all cross-group nets — this is a straightforward aggregation that
   preserves total edge weight between groups.

5. **Assign super-node sizes.** For coarsened groups:
   `size = max_spread_mm` (or actual bounding box extent from Phase 1).
   For ungrouped components: `size = max(width, height)` of the
   component's footprint.

6. **Output**: `(super_adjacency, super_node_map, component_to_super)`
   where `super_node_map` is a list of lists of component indices per
   super-node.

### Phase 3: Global Spectral Embedding (Super-Nodes)

**Module**: `optimizer/initialization.py` — new private method
`_embed_super_nodes(super_adj, super_sizes, board, group_separations)`.

1. **Compute spectral coordinates.** Call
   `compute_spectral_coordinates(super_adj, n_dims=2, normalized=True)`.
   This is the same `compute_spectral_coordinates` from
   `optimizer/initialization.py:29`, applied to the coarsened graph.
   Output: `(G, 2)` spectral coordinates.

   **Proof sketch for Fiedler vector preservation**: The coarsened
   Laplacian `L_G` is a contraction of the original Laplacian `L_N`
   where nodes within each group are merged. By the Rayleigh quotient
   formulation, `λ_2(L_G) ≥ λ_2(L_N)` (coarsening removes intra-group
   edges, increasing the algebraic connectivity constraint for
   inter-group separation). The Fiedler vector of `L_G` preserves the
   ordering of groups relative to each other because cross-group edges
   are aggregated, not lost. The proof is analogous to spectral
   clustering coarsening under normalized cut preservation.

2. **Scale to board.** Call `scale_to_board(spectral_coords, board,
   margin_fraction=0.1)`. This maps spectral coordinates to board mm
   using the existing function at `initialization.py:134`.

3. **Apply GroupSeparation nudges.** If `constraints.group_separations`
   exists, for each `GroupSeparation(sep)`:
   - Compute current centroid distance between the two super-nodes.
   - If distance < sep.min_distance_mm: push centroids apart along the
     vector connecting them by `(min_dist - current_dist) / 2` each.
   - Repeat 3 times to converge (small G, so cheap).

4. **Output**: `(G, 2)` super-node centroid positions in board coordinates.

### Phase 4: Explode to Component Positions

**Module**: `optimizer/initialization.py` — new method
`_explode_positions(super_centroids, micro_offsets, component_to_super,
board)`.

1. **For each component `i` in each super-node `g`:**
   - `position[i] = super_centroids[g] + micro_offsets[group_id][local_idx]`

2. **For ungrouped (singleton) components**: position is directly the
   super-node centroid (offset = (0, 0)).

3. **Board-boundary correction.** After explosion, check if any component
   position falls outside the board bounds (or within margin). If so:
   - Compute the group's bounding box.
   - If the group intersects a board edge, shift the entire group inward
     by the overflow amount.
   - This preserves intra-group topology. Preferred over clipping
     individual members (which would break group structure).

4. **Coincident separation.** Call
   `_separate_coincident_components(positions, board)` from
   `initialization.py:280` to spread any components at identical
   positions (can happen for singleton nodes with identical coords).

5. **Output**: `(N, 2)` component positions in board coordinates.

### Pipeline Integration

In `packages/temper-placer/src/temper_placer/optimizer/phases.py`,
`OptimizationPipeline.run()` method, insert after the TopologicalPhase
result and before the GeometricPhase call:

```python
# In OptimizationPipeline.run(), between line 277 and line 298

# NEW: Hierarchical group pre-clustering
if (self.opt_config.initialization.group_preclustering
    and self.constraints.component_groups):
    from temper_placer.optimizer.initialization import (
        HierarchicalGroupInitializer,
    )
    from temper_placer.core.netlist import build_adjacency_matrix

    logger.info(
        f"Pre-clustering {len(self.constraints.component_groups)} "
        f"groups ({self._count_group_members(self.constraints.component_groups)} components)"
    )
    init = HierarchicalGroupInitializer(
        normalized_laplacian=self.opt_config.initialization.spectral_normalized,
        margin_fraction=self.opt_config.initialization.spectral_margin,
    )
    positions = init.initialize(
        self.netlist,
        self.board,
        self.constraints,
    )
    # Override current_state positions with pre-clustered positions
    from temper_placer.core.state import PlaceholderState
    current_state = PlaceholderState.from_positions(positions)
    logger.info(
        f"Pre-clustering complete: {init.diagnostics}"
    )
```

**Alternative consideration**: Instead of inserting in `phases.py`, we
could modify the `initial_state` path in `train.py:311` where
`initial_state` is already checked. However, `phases.py` is the correct
location because:
- The `TopologicalPhase` output (zones, clusters) is still used as
  context (e.g., for ungrouped components).
- The `GeometricPhase` receives a consistent `PlaceholderState` regardless
  of init path.
- This follows the existing pattern: phases.py orchestrates
  pipeline-level coordination, train.py handles training mechanics.

### `HierarchicalGroupInitializer` Class

```python
@dataclass
class HierarchicalGroupInitializer:
    """
    Initialize positions using hierarchical group pre-clustering.

    Reduces dimensionality from N components to G super-nodes (G << N)
    by exploiting component_groups from the config, then explodes back
    to full positions.

    Attributes:
        normalized_laplacian: Passed to Phase 3 spectral embedding.
        margin_fraction: Board margin for Phase 3 scaling.
        force_iterations: Iterations for Phase 1 micro-solve.
        diagnostics: List of diagnostic messages set during initialize().
    """

    normalized_laplacian: bool = True
    margin_fraction: float = 0.1
    force_iterations: int = 200
    diagnostics: list[str] = field(default_factory=list)

    def initialize(
        self,
        netlist: Netlist,
        board: Board,
        constraints: PlacementConstraints,   # carries component_groups
    ) -> Array:
        # Returns (N, 2) positions
        ...
```

### Edge Cases

| Scenario | Behavior |
|---|---|
| No groups defined | Return standard spectral init positions |
| All components in one group | Run micro-solve, no coarsening needed (1 super-node = board center) |
| Group with 1 component | Trivial offset (0, 0); super-node size = component size |
| Group with all fixed components | Each fixed position becomes the micro-solve anchor; others arrange around them |
| Group crosses zone boundaries | Skip coarsening for this group, warn |
| Component in multiple groups | Assign to group with tighter `max_spread_mm`, warn about the other |
| Spanning group | Members as individual singletons; no coarsening |
| Empty adjacency (no nets between components) | Each component is its own super-node; Phase 3 still works |
| Single net connecting all components | Coarsening still reduces dimensionality; Phases 1-4 all valid |

---

## Testing Strategy

### Validation Hypothesis Experiment (Prerequisite)

Before implementing code, run a measurement pass:

```
uv run python scripts/measure_group_spread_after_spectral.py
```

This script:
1. Loads the golden board config (with `component_groups` defined).
2. Runs standard `SpectralInitializer.initialize()`.
3. For each group, computes `max(member_to_centroid_distance)` and compares
   to `max_spread_mm`.
4. Reports: % of groups exceeding constraint, histogram of excess.

Gate: If fewer than 30% of groups violate their spread constraint,
pre-clustering is not justified. Document results and pause implementation.

### Property-Based Tests

**Location**: `packages/temper-placer/tests/optimizer/test_hierarchical_init_properties.py`

| Property | Strategy | Assertion |
|---|---|---|
| **P1: Group bounding box after micro-placement** | `@given` generates random groups of 2-20 components on random sub-adjacency, runs Phase 1 | `diameter(group_members) <= max_spread_mm * 1.2` — the 1.2x tolerance accounts for the force-directed solver's approximate convergence; beyond this, the fallback radial placement guarantees the constraint |
| **P2: Super-node positions within board bounds** | `@given` generates random group configurations, runs Phase 1-3 | All super-node centroids within `[margin, board.width - margin] × [margin, board.height - margin]` |
| **P3: Explosion preserves relative positions** | `@given` generates random micro-offsets and centroids, runs Phase 4 | Pairwise distances between group members are identical before and after explosion (distances between original micro-positions == distances after adding centroid) |
| **P4: Coarsened adjacency preserves total edge weight** | `@given` generates random adjacency + group assignments, runs Phase 2 | `sum(super_adj) == sum(original_adj)` (intra-group edges are excluded in coarsening, so this is: `sum(super_adj) == sum(original_adj) - sum(intra_group_edges)`) |
| **P5: Idempotence** | `@given` generates random constraints + netlist | Running `initialize()` twice with the same inputs produces identical positions |

### Unit Tests

**Location**: `packages/temper-placer/tests/optimizer/test_hierarchical_init.py`

- `test_micro_placement_2_components`: 2-component group, verify both
  positions are within `max_spread_mm` of each other.
- `test_micro_placement_4_components`: 4-component group on a square
  topology, verify all pairwise distances ≤ `max_spread_mm`.
- `test_micro_placement_one_fixed`: 3-component group with 1 fixed
  component — verify the fixed component's local position is unchanged
  and other components are within range.
- `test_spanning_group_not_coarsened`: Group with `max_spread_mm > 0.3 *
  board_diagonal` — verify members are treated as individual
  super-nodes and receive distinct (not centroid-collapsed) positions.
- `test_overlapping_group_resolution`: Same component in two groups —
  verify assignment to group with tighter `max_spread_mm`, warning
  generated for the other.
- `test_empty_groups_fallback`: Empty `component_groups` — verify
  behavior identical to standard `SpectralInitializer`.
- `test_single_group_board_center`: One group covering all components —
  verify positions cluster around board center.
- `test_fixed_component_anchor_preserved`: Component with `fixed = True`
  in a group — verify its final position matches `fixed_positions`.

### Spanning-Group Test

Dedicated test verifying the 30% threshold:

```python
def test_spanning_group_threshold_derivation():
    """Spanning group >30% board diagonal → members placed as singletons."""
    board = Board(width=100.0, height=100.0)
    board_diagonal = sqrt(100**2 + 100**2) * 0.3  # ≈ 42.4mm

    # Group with spread > 30% diagonal → spanning
    spanning_group = ComponentGroup(
        name="wide", components=["C1", "C2"],
        max_spread_mm=50.0  # > 42.4
    )
    # Group with spread < 30% diagonal → coarsened
    normal_group = ComponentGroup(
        name="tight", components=["C3", "C4"],
        max_spread_mm=20.0  # < 42.4
    )
    # ... assert spanning group members are singletons,
    #     normal group is coarsened to one super-node
```

### Integration Test

**Location**: `packages/temper-placer/tests/optimizer/test_hierarchical_init_integration.py`

- Load the golden board config with component groups.
- Run the full pipeline with `group_preclustering: True`.
- At epoch 0, compute group diameters for all groups in
  `component_groups`.
- Assert: ≥ 90% of groups have diameter < `max_spread_mm` (or within 10%
  margin).
- Assert: No group has diameter > `max_spread_mm * 1.5` (should be
  impossible; fallback radial placement guarantees ≤ `max_spread_mm`).

### A/B Testing Framework

**Location**: `packages/temper-placer/scripts/compare_preclustering.py`

Pipeline:
1. Run baseline (standard spectral init) on golden board, record:
   - `group_diameter_vs_max_spread` at epoch 0
   - `GroupClusterLoss` trajectory over 8000 epochs
   - Final wirelength
   - Convergence epoch (loss stabilizes within 1% for 500 epochs)
2. Run variant (pre-clustering) with same parameters, record same metrics.
3. Compare:
   - % groups within `max_spread_mm` at epoch 0
   - AUC of `GroupClusterLoss` (lower = better)
   - Final wirelength (should not be degraded)
   - Convergence speed (epochs to 95% of final loss)
4. Output: comparison table with % improvement per metric.

---

## Mathematical Basis

### Phase 1: Force-Directed Objective

The force-directed solver minimizes:

```
E = Σ spring_constant_ij × (d_ij - target_distance_ij)²
```

where `d_ij = ||pos_i - pos_j||_2` is the Euclidean distance between
components i and j within the group, `spring_constant_ij` is proportional
to the adjacency weight (number of shared nets), and `target_distance_ij`
is derived from proximity rules (`max_distance_mm`) when present, else
`max_spread_mm / sqrt(M_i)` (uniform target for an M_i-component cluster).

The standard Fruchterman-Reingold in `compute_force_directed_layout`
(`heuristics/force_directed.py:195`) uses:
- Repulsion: `F_r = k² / d` where `k = sqrt(area / N_local)`
- Attraction: `F_a = d² / k` (spring force)

This is equivalent to minimizing the spring energy above with additional
repulsion to prevent component overlap.

### Phase 2: Super-Node Adjacency Aggregation

Given original adjacency `A (N×N)` and group partition `p: {0..N-1} → {0..G-1} ∪ {-1}`:

```
super_A[g, h] = Σ_{i: p(i)=g} Σ_{j: p(j)=h} A[i, j]
```

The coarsened Laplacian `L_G = D_G - super_A` where `D_G` is the diagonal
degree matrix of super-nodes.

**Dimensionality reduction**: N → G, where G ≤ |groups| + N_ungrouped.
For typical designs with 10-50 groups and 200+ components, G ≈ 40-80,
reducing the spectral problem from 200×200 to 40×40 matrices.

### Phase 3: Spectral Embedding of Coarsened Graph

Same `compute_spectral_coordinates(adjacency, n_dims=2, normalized=True)`
applied to `super_A`:

- Compute L = I - D^(-1/2) A D^(-1/2)
- Solve `L v = λ v` for smallest 3 eigenvalues
- Discard λ_1 = 0 (constant eigenvector)
- Use eigenvectors for λ_2, λ_3 as (x, y) coordinates

**Fiedler vector ordering preservation**: The coarsened Laplacian's
Fiedler vector (λ_2 eigenvector) preserves the ordering of groups along
the primary axis because:
1. Coarsening aggregates intra-group edges (which only affect the constant
   eigenvector).
2. Cross-group edges are preserved exactly in `super_A`.
3. By the Courant-Fischer min-max theorem, the Fiedler vector of `L_G`
   minimizes `(x^T L_G x) / (x^T x)` subject to `x ⟂ 1`, which is the
   same objective as the original Laplacian but constrained to
   group-constant vectors. The optimal group ordering is thus preserved.

### Spanning-Group Threshold Derivation

A group is considered "spanning" when coarsening it into a single
super-node would distort the global layout more than it helps.

**Derivation**: The coarsening error ε is bounded by the ratio of the
group's internal spread to the board diagonal:

```
ε = max_spread_mm / board_diagonal
```

When `ε < 0.3`, the group's internal structure is << the board's scale,
so replacing it with a super-node loses negligible positional information.

When `ε ≥ 0.3`, the group's members span a significant fraction of the
board — collapsing them into one point would force the spectral embedding
to place other groups in arbitrary positions relative to this large
region.

**Threshold**: `max_spread_mm > 0.3 * sqrt(board.width² + board.height²)`

**Example**: On a 100×150mm board (diagonal = 180.3mm), groups with
`max_spread_mm > 54.1mm` are spanning. A star-ground group connecting
points across the full board would exceed this threshold.

---

## Implementation Phases

### Phase A: Configuration and Scaffolding (Day 1)

**Files**:
- `packages/temper-placer/src/temper_placer/optimizer/config.py`:
  Add `group_preclustering: bool = False` to `InitializationConfig`.
- `packages/temper-placer/src/temper_placer/optimizer/initialization.py`:
  Add `HierarchicalGroupInitializer` dataclass with:
  - `normalized_laplacian`, `margin_fraction`, `force_iterations`,
    `diagnostics` fields
  - `initialize()` method signature (returns `Array`)
  - Graceful fallback: if `constraints.component_groups` is empty,
    call `SpectralInitializer.initialize()`.

**No pipeline integration yet.** Just the class and tests for it.

### Phase B: Phase 1 — Intra-Group Micro-Placement (Day 1-2)

**Files**:
- `optimizer/initialization.py`: `_solve_group_micro_layout()` method
  - Extract sub-adjacency from netlist
  - Set up `compute_force_directed_layout` for each group
  - Fallback radial placement
  - Handle fixed components, single-component groups

**Tests**:
- `test_micro_placement_2_components`
- `test_micro_placement_4_components`
- `test_micro_placement_one_fixed`
- Property tests P1 (group bounding box after micro-placement)

### Phase C: Phase 2 — Group Coarsening (Day 2-3)

**Files**:
- `optimizer/initialization.py`: `_coarsen_to_super_nodes()` method
  - Component-to-group assignment (overlap resolution)
  - Spanning-group detection
  - Super-node adjacency aggregation
  - `component_to_super` mapping

**Tests**:
- `test_spanning_group_not_coarsened`
- `test_overlapping_group_resolution`
- Property tests P4 (coarsened adjacency preserves total edge weight)

### Phase D: Phase 3 & 4 — Global Embedding + Explosion (Day 3)

**Files**:
- `optimizer/initialization.py`:
  - `_embed_super_nodes()` — call existing `compute_spectral_coordinates`
    and `scale_to_board`
  - `_explode_positions()` — combine centroids + offsets, boundary shift

**Tests**:
- `test_single_group_board_center`
- Property tests P2 (super-node positions in bounds), P3 (explosion
  preserves relative positions), P5 (idempotence)

### Phase E: Pipeline Integration (Day 3-4)

**Files**:
- `optimizer/phases.py`: Insert pre-clustering call in
  `OptimizationPipeline.run()` between TopologicalPhase and
  GeometricPhase.
- `optimizer/__init__.py`: Export `HierarchicalGroupInitializer`.

**Tests**:
- `test_empty_groups_fallback` — verify standard path unchanged
- Integration test on golden board

### Phase F: Validation Hypothesis Experiment + A/B Testing (Day 4)

**Files**:
- `packages/temper-placer/scripts/measure_group_spread_after_spectral.py`
- `packages/temper-placer/scripts/compare_preclustering.py`

### Phase G: Edge Cases and Hardening (Day 4-5)

- Fixed component anchor preservation test
- Cross-zone group skip
- Full-graph coarsening (all components in groups)
- No-nets board (purely unconnected components)

### Phase H: CI Integration

- Add `test_hierarchical_init.py` to CI test suite
- Add `test_hierarchical_init_properties.py` to CI (may need Hypothesis
  deadline tuning for long-running strategies)
- Add `group_preclustering: false` to all existing integration test configs
  to ensure no regressions

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Force-directed solver produces poor local layouts for certain group topologies | Medium | Low — caught by validation | Fallback to radial placement if diameter exceeds 1.2 × `max_spread_mm`; grouping loss remains active as safety net |
| Coarsening loses inter-component connectivity detail | Low | Medium | Aggregated adjacency preserves cross-group edge weights exactly; the spectral embedding uses the same algorithm as current init |
| Overlapping-group resolution is wrong for a real config | Low | Medium | Track component→group conflict metric; if conflicts appear in production configs, escalate to group merging |
| Pre-clustered positions are worse for wirelength than spectral | Low | Medium | A/B test comparison; if wirelength degrades, add hybrid approach (pre-clustered for group members, spectral for inter-group) |
| Integration breaks existing spectral init path | Low | High | Guarded by `group_preclustering: bool` flag (default: `False`); no existing configs affected |
| Performance regression — 200 iterations per group for 50 groups | Low | Low | 50 × 200 = 10K iterations total, sub-millisecond each (JAX JIT on small matrices) — overall < 5 seconds for realistic boards |
| ZoneAwareSpectralInitializer interaction with cross-zone groups | Low | Low | Skip pre-clustering for cross-zone groups, fall back to zone-aware init for those members |

---

## References

| File | Role |
|---|---|
| `packages/temper-placer/src/temper_placer/optimizer/initialization.py` | Existing `SpectralInitializer`, `compute_spectral_coordinates`, `scale_to_board`, `_separate_coincident_components` — target for new `HierarchicalGroupInitializer` |
| `packages/temper-placer/src/temper_placer/io/config_loader.py:531` | `ComponentGroup` — input schema with `components`, `max_spread_mm`, `proximity_rules`, `weight` |
| `packages/temper-placer/src/temper_placer/io/config_loader.py:225` | `GroupSeparation` — minimum inter-group distance constraints |
| `packages/temper-placer/src/temper_placer/io/config_loader.py:620` | `PlacementConstraints` — carries `component_groups`, `group_separations`, `fixed_components`, `fixed_positions` |
| `packages/temper-placer/src/temper_placer/heuristics/force_directed.py:195` | `compute_force_directed_layout` — Phase 1 micro-solver (Fruchterman-Reingold with JAX JIT) |
| `packages/temper-placer/src/temper_placer/heuristics/topological_init.py:44` | `TopologicalInitializationHeuristic` — existing init path that also ignores groups |
| `packages/temper-placer/src/temper_placer/losses/grouping.py:50` | `GroupClusterLoss` — loss that currently rediscover groups; remains active post-init as safety net |
| `packages/temper-placer/src/temper_placer/optimizer/phases.py:265` | `OptimizationPipeline.run()` — integration point between TopologicalPhase and GeometricPhase |
| `packages/temper-placer/src/temper_placer/optimizer/curriculum.py:86` | Curriculum Phase 3 activation — `grouping: 50.0` at epoch 3000; the motivation for why pre-clustering matters |
| `packages/temper-placer/src/temper_placer/optimizer/config.py:180` | `InitializationConfig` — target for `group_preclustering` flag |
| `packages/temper-placer/src/temper_placer/optimizer/train.py:317` | Current init dispatch — spectral / zone-aware / learned / random; pre-clustering injected upstream in phases.py, not here |
| `packages/temper-placer/src/temper_placer/core/state.py:42` | `PlaceholderState.from_positions()` — target for exploded positions |
| `docs/brainstorms/2026-07-01-hierarchical-group-preclustering-requirements.md` | Source requirements document |
