---
title: "Pattern: Hierarchical Group Coarsening for Dimensionality Reduction in Placement Initialization"
date: 2026-07-01
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "Reducing placement optimization dimensionality by exploiting functional group structure in component netlists"
  - "Initializing placement for boards where component_groups are declared in constraints (e.g., half-bridge stages, EMI-sensitive clusters, template-replicated blocks)"
  - "Bridging topological phase output into geometric phase input when group layout micro-solving is needed before global spectral placement"
  - "Handling spanning groups (>30% board diagonal) that cannot be meaningfully coarsened into a single super-node"
tags:
  - hierarchical-coarsening
  - spectral-embedding
  - super-node-aggregation
  - force-directed-micro-solve
  - spanning-group-detection
  - overlap-resolution
  - group-pre-clustering
  - placement-initialization
---
# Pattern: Hierarchical Group Coarsening for Dimensionality Reduction in Placement Initialization

## Context

The temper-placer's geometric optimizer operates on N individual component positions,
which scales quadratically in the Laplacian eigen-decomposition and linearly in
optimizer state size. For boards with many components (>50), this creates a
practical bottleneck at initialization.

However, design constraints often declare functional groups: a half-bridge stage, an
EMI-sensitive snubber cluster, a decoupling capacitor bank. These groups express
the designer's intent that a subset of components should be tightly coupled.
Instead of treating all N components as independent degrees of freedom for the
global placement, coarsening reduces the problem to G super-nodes (G << N), solves
at the group level, then reconstructs component positions from intra-group offsets.

The pattern lives between the `TopologicalPhase` and `GeometricPhase` in the
`OptimizationPipeline`, gated by `opt_config.initialization.group_preclustering`.

## Guidance

### Four-Phase Pipeline

The `HierarchicalGroupInitializer.initialize()` method implements a 4-phase pipeline
(`optimizer/initialization.py:694-759`):

```
┌──────────────────────────────────────────────────────────────┐
│                    N components, G groups                     │
└──────────────────────┬───────────────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │ Phase 1: Internal       │  Force-directed within
          │ Micro-Solve (per group) │  each group's max_spread_mm
          └────────────┬────────────┘  bounding box
                       │
          ┌────────────▼────────────┐
          │ Phase 2: Coarsen to     │  Groups → super-nodes
          │ Super-Nodes             │  Aggregate cross-group adj.
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │ Phase 3: Global Spectral│  Laplacian eigen-decomp
          │ Embed (G super-nodes)   │  on G×G adjacency
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │ Phase 4: Explode Back   │  centroid[sn] + offset[local]
          │ to Component Positions  │  Fixed anchors restored
          └─────────────────────────┘
```

#### Phase 1: Intra-Group Micro-Solve

Each group is solved independently via force-directed layout
(`optimizer/initialization.py:761-850`):

1. Build a subnetlist containing only the group's members
2. Initialize positions on a small circle within the group's `max_spread_mm` bounding box
3. Run force-directed solver (`heuristics/force_directed.py:compute_force_directed_layout`) with:
   - Repulsion `k = sqrt(local_bbox^2 / n_members)`
   - Attraction from the sub-adjacency matrix
   - Simulated annealing (temperature from `max_spread_mm / 10` down to 0.1, cooling factor 0.95)
4. Validate diameter: if result diameter > `max_spread_mm * 1.2`, fall back to deterministic
   radial placement (circle at `max_spread_mm / 2` radius)
5. Seed RNG from `md5(group.name)` for determinism

Fixed components within a group initialize at their recorded anchor positions and anchor
the force-directed solve (the solver preserves their positions throughout).

#### Phase 2: Coarsen to Super-Nodes

The `_coarsen_to_super_nodes` method (`optimizer/initialization.py:852-958`) maps N
components to G super-nodes:

1. **Spanning-group detection**: Groups with `max_spread_mm > 0.3 * board_diagonal`
   are flagged as spanning. Their members are NOT coarsened into a single super-node;
   instead, each member becomes its own singleton super-node. This prevents a
   single super-node from dominating the entire board and forces the global spectral
   embedding to reason about member placement.

   The 30% threshold derives from the board diagonal:
   ```python
   board_diagonal = sqrt(board.width^2 + board.height^2)
   spanning_threshold = 0.3 * board_diagonal
   ```

2. **Overlap resolution**: Components appearing in multiple groups are resolved by
   **tightest-constraint-first**: the component is assigned to the group with the
   smaller `max_spread_mm`. Reassigned components emit a diagnostic.

3. **Super-node construction**:
   - Coarsened (non-spanning) groups → one super-node per group, containing all
     assigned member indices
   - Ungrouped components → each gets its own singleton super-node
   - Spanning group members → each gets its own singleton super-node

4. **Aggregated adjacency**: The G×G `super_adj` matrix preserves total cross-group
   edge weight (`optimizer/initialization.py:938-950`):
   ```python
   for gi in range(G):
       for gj in range(gi + 1, G):
           weight = sum(adjacency[mi, mj]
                        for mi in super_node_map[gi]
                        for mj in super_node_map[gj])
   ```
   Intra-group edges are implicitly excluded (they exist between members of the same
   super-node), so `sum(super_adj) == sum(original_adj) - sum(intra_group_edges)`.

Returns five values: `super_adj` (G×G), `super_node_map` (list of member-index lists),
`component_to_super` (N-long mapping array), `group_to_super` (group-id → super-node-id
for coarsened groups only), `group_name_to_super` (name-based lookup).

#### Phase 3: Global Spectral Embedding

The `_embed_super_nodes` method (`optimizer/initialization.py:960-987`) computes
positions for G super-nodes:

1. Compute spectral coordinates from the G×G `super_adj` Laplacian (2nd and 3rd eigenvectors)
2. Scale to board bounds with `margin_fraction` padding
3. Apply `GroupSeparation` nudges: iterate over separation rules, push super-node
   centroid pairs apart if their distance falls below `min_distance_mm`
4. Single-super-node case (G=1): place at board center

#### Phase 4: Explode Back to Component Positions

The `_explode_positions` method (`optimizer/initialization.py:989-1051`) reconstructs
N component positions from G super-node centroids:

1. Assign each component its super-node centroid as base position
2. Apply micro-offsets: for coarsened groups, compute `position[i] = centroid[sn_id] + offset[group_id][local_i]`
3. Apply micro-offsets for spanning groups: members are singleton super-nodes, each
   gets `centroid[own_sn_id] + offset[group_id][local_i]`. The micro-solve runs even
   for spanning groups, but the offsets are applied at the member's own centroid
   rather than a shared group centroid.
4. **Fixed component override**: Fixed components are set to their recorded anchor
   positions (`fixed_anchors[comp_idx]`) explicitly after all offset/centroid
   computation, preserving exact coordinates through all four phases
5. Board-boundary correction: shift groups whose members exceed board bounds inward
6. Coincident separation: apply deterministic spiral pattern to components at the
   same position

### Pipeline Integration

The hierarchical initializer is invoked between `TopologicalPhase` and `GeometricPhase`
in the `OptimizationPipeline.run()` method (`optimizer/phases.py:281-316`):

```python
# 1. TopologicalPhase runs, producing initial_state
# 1.3 Hierarchical Group Pre-Clustering
if (opt_config.initialization.group_preclustering
    and placement_constraints.component_groups):
    init = HierarchicalGroupInitializer(
        normalized_laplacian=opt_config.initialization.spectral_normalized,
        margin_fraction=opt_config.initialization.spectral_margin,
    )
    positions = init.initialize(netlist, board, placement_constraints)
    current_state = PlacementState.from_positions(positions)
# 1.5 NSGA Phase (optional)
# 2. GeometricPhase runs from current_state
```

When `group_preclustering` is disabled or no `component_groups` are defined, the
initializer falls back to standard `SpectralInitializer`.

### Constraint Data Model

Component groups are declared in the constraints YAML and parsed into
`ComponentGroup` dataclasses (`io/config_loader.py:577-592`):

```python
@dataclass
class ComponentGroup:
    name: str
    components: list[str]
    max_spread_mm: float = 30.0     # Max diameter of group bounding box
    zone: str | None = None
    proximity_rules: list[ProximityRule] = field(default_factory=list)
    weight: float = 1.0
    description: str = ""
    template_group: str | None = None
    primary_pin: str | None = None
    stacked_layout: bool = False
```

`max_spread_mm` serves dual purposes: it defines the Phase 1 micro-solve bounding
box and determines coarsening behavior (spanning vs. coarsened).

### Fallback and Diagnostics

- **Spectral fallback**: If no `component_groups` are defined or constraints is `None`,
  the initializer delegates to `SpectralInitializer` with matching Laplacian/margin params.
- **Unknown component refs**: `_resolve_member_indices` emits a warning diagnostic and
  skips the missing component; no crash.
- **Empty groups**: Groups with zero resolved members are silently skipped in both
  the micro-solve and coarsening phases.
- **Diameter fallback**: If force-directed exceeds `1.2 * max_spread_mm`, falls back
  to deterministic radial placement.
- **Zero max_spread**: Defaults to 30.0mm.
- **Diagnostics accumulation**: Each phase appends human-readable status messages to
  `self.diagnostics` for downstream logging and observability.

## Consequences

- **32 dedicated tests** in `tests/optimizer/test_hierarchical_init.py` covering:
  - Phase A (config/scaffolding): fallback, config field gating, diagnostics population
  - Phase B (micro-placement): 2-component, 4-component, fixed-component anchoring,
    singleton groups, diameter fallback
  - Phase C (coarsening): spanning-group detection, threshold derivation,
    tightest-constraint overlap resolution, cross-group edge-weight preservation,
    all-in-groups path
  - Phase D (embedding + explosion): board-center placement, multi-group positioning,
    idempotence, GroupSeparation integration
  - Phase E (pipeline integration): end-to-end pipeline with/without pre-clustering
  - Phase G (edge cases): no-nets board, all-fixed components, unknown component refs,
    force-directed-to-radial fallback, zero `max_spread_mm` defaulting,
    no-matching-members ghost groups, singleton count correctness,
    fixed anchor preservation (coarsened + spanning)

- Dimensionality reduction from N components to G super-nodes (typically G ≤ N/2 for
  multi-component groups); spectral eigen-decomposition runs on the G×G Laplacian
  instead of N×N.

- Deterministic placement: identical `Netlist`, `Board`, and `PlacementConstraints`
  produce identical positions (verified by idempotence test).

## When to Apply

Apply this pattern when:
- Component groups are declared in design constraints with `max_spread_mm` bounds
- Board has >50 components and spectral initialization time becomes measurable
- Functional blocks (half-bridge stages, EMI clusters, replicated templates) exist
  as groups in the netlist
- `group_preclustering` config flag is `True`

Do NOT apply when:
- No `component_groups` are declared (the initializer falls back automatically)
- All groups are spanning (>30% board diagonal) — each member becomes a singleton
  super-node, yielding no dimensionality reduction
- Every component is fixed (trivially, no optimization degrees of freedom remain)

## Related

- `packages/temper-placer/src/temper_placer/optimizer/initialization.py:673-1213` — `HierarchicalGroupInitializer` implementation
- `packages/temper-placer/src/temper_placer/optimizer/phases.py:70-120` — `TopologicalPhase`
- `packages/temper-placer/src/temper_placer/optimizer/phases.py:122-165` — `GeometricPhase`
- `packages/temper-placer/src/temper_placer/optimizer/phases.py:267-316` — Pipeline integration (pre-clustering between topological and geometric)
- `packages/temper-placer/src/temper_placer/io/config_loader.py:577-592` — `ComponentGroup` dataclass
- `packages/temper-placer/tests/optimizer/test_hierarchical_init.py` — 32 tests (7 phases: A-G)
- `packages/temper-placer/src/temper_placer/heuristics/force_directed.py:compute_force_directed_layout` — Phase 1 micro-solve solver
- `packages/temper-placer/src/temper_placer/algo/coarsening.py` — Hypergraph coarsening (Heavy Edge Matching, distinct from group-level coarsening)
- `packages/temper-placer/src/temper_placer/placement/constraint_weights.py` — Constraint-to-Laplacian weight bridge (feeds `build_adjacency_matrix`)
- `docs/solutions/architecture-patterns/constraint-weighted-spectral-laplacian-pcb-placement-2026-07-01.md` — sibling pattern (constraint-augmented Laplacian for spectral embedding)
- `docs/solutions/architecture-patterns/declarative-stage-dag-replaces-orchestrator-2026-06-22.md` — pipeline stage architecture (pre-clustering is Phase 1.3 in this DAG)
