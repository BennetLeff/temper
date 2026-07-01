# Hierarchical Group-Centroid Pre-Clustering for Placement Initialization

**Date:** 2026-07-01  
**Status:** Brainstorm / Requirements  
**Topic:** Pre-solve intra-group topology from `PlacementConstraints.component_groups` and inject into `PlacementState` before gradient descent begins.

---

## Problem Statement

`PlacementConstraints` (`io/config_loader.py:665`) already defines functional groups via `component_groups: list[ComponentGroup]` — gate-drive circuits, sense-feedback paths, matched-length pairs, star-ground clusters — each with `max_spread_mm`, `proximity_rules`, and `weight`. `GroupSeparation` constraints (`config_loader.py:225`) encode minimum inter-group distances. These constraints encode *known design intent*.

Yet **none of this reaches initialization**. The current initialization paths ignore groups entirely:

- `SpectralInitializer` (`optimizer/initialization.py:203`) computes a global spectral embedding of the full adjacency graph. It discovers connected subgraphs but has no concept of designer-annotated functional groups.
- `TopologicalInitializationHeuristic` (`heuristics/topological_init.py:44`) builds a topological graph purely from netlist adjacency and infers adjacency constraints at a fixed default 20 mm — again ignoring explicit group definitions.
- `ZoneAwareSpectralInitializer` (`optimizer/zone_aware_init.py`) respects zone assignments but not groups.

The consequence: the curriculum's Phase 3 (`design_rules`, `optimizer/curriculum.py:74–91`) activates `grouping: 50.0` at epoch 3000 — **37.5% of training has already passed** (epochs 0–3000 of 8000). The optimizer must rediscover intra-group proximity via gradient descent against `GroupClusterLoss` (`losses/grouping.py:50`), which applies a quadratic penalty when group diameter exceeds `max_spread_mm`. This is wasteful: the gradient must pull scattered components across the board back into tight clusters, doing work the designer already encoded.

**In short:** The optimizer wastes the first 3000 epochs discovering what `component_groups` already declares. A pre-clustered initialization would give the optimizer correct intra-group topology immediately, letting Phase 1–2 focus on inter-group layout.

**Validation hypothesis:** We predict that after current spectral initialization on the Temper board, at least 60% of functional groups have member-to-centroid distances exceeding the group's `max_spread_mm` constraint. This will be measured as a prerequisite experiment: run spectral init on the golden board design, compute per-group maximum member-to-centroid distances, and compare against the `max_spread_mm` values defined in `PlacementConstraints`. If fewer than 30% of groups violate their spread constraint, the 4-phase pre-clustering approach may not be justified over simpler alternatives (see Rejected Alternatives).

---

## Proposed Approach: 4-Phase Hierarchical Pre-Clustering

The approach reduces dimensionality from placing N components to placing G groups (G << N) by exploiting the fact that intra-group topology is well-defined by proximity rules and spread constraints.

### Phase 1: Intra-Group Micro-Placement (per group)

For each `ComponentGroup` in `constraints.component_groups`:

1. **Extract subgraph.** Build a sub-adjacency matrix for group members only, using netlist connectivity (`Netlist.build_adjacency_matrix()`). Weight edges by net count (multiple shared nets = stronger coupling).

2. **Solve local layout.** Compute relative positions of group members around their shared centroid using one of:
   - **Force-directed layout** (preferred for small groups): Run `compute_force_directed_layout()` (`heuristics/force_directed.py:197`) on the sub-adjacency, with group proximity rules as strong attractive forces. Convergence is fast for small groups (< 20 components).
   - **Spectral embedding** (fallback): `compute_spectral_coordinates()` (`optimizer/initialization.py:29`) on the sub-adjacency, scaled to fit within `max_spread_mm`.
   - The output is relative offset vectors `(dx, dy)` from the group centroid, in mm.

3. **Orient the micro-layout.** If `primary_pin` is set on the group, use it to define a canonical orientation (e.g., pin-to-centroid vector defines "front"). Apply `rotation_hints` from the topological phase if available.

4. **Validate against constraints.** Check that no pair exceeds `max_spread_mm` (hard constraint) and that proximity rules are satisfied. If a group cannot be laid out within constraints (e.g., too many components for the spread limit), flag as a warning and fall back to random or uniform placement for that group.

### Phase 2: Group Coarsening (super-nodes)

Replace each group with a single "super-node":

1. **Aggregate connectivity.** For each cross-group net that connects a component in group A to a component in group B, add an edge between super-node A and super-node B. Edge weight = sum of all component-level edge weights on that net. This preserves the netlist topology at the group level.

2. **Aggregate dimensions.** Super-node "size" = `max_spread_mm` (or the actual bounding-box extent from Phase 1). Used for placement margin estimation.

3. **Handle ungrouped components.** Components not in any group remain as singleton super-nodes (size = their actual footprint).

4. **Handle overlapping groups.** See Risk & Conflict Resolution below.

### Phase 3: Global Spectral Embedding (super-nodes)

1. **Build group-level adjacency matrix.** From the coarsened graph (Phase 2), build a (G, G) weighted adjacency matrix.

2. **Compute spectral embedding.** Run `compute_spectral_coordinates()` on the group-level adjacency. This gives global (x, y) positions for each super-node centroid in normalized spectral space.

3. **Scale to board.** Use `scale_to_board()` (`optimizer/initialization.py:134`) to map spectral coordinates onto the board, respecting group sizes as margins.

4. **Apply group separations.** If `GroupSeparation` constraints exist (e.g., power stage vs. MCU must be > 50 mm apart), enforce these by shifting super-node centroids apart before scaling. This can be done via a simple force-directed pass on the super-nodes alone.

### Phase 4: Explode (reconstruct full positions)

For each component in each group:
- `position = super_node_centroid + relative_offset_from_phase_1`

The resulting `(N, 2)` array feeds directly into `PlacementState.from_positions()` and becomes the initial state for the `GeometricPhase`.

---

## Integration Point

The pre-clustering should run **before `GeometricPhase` but after `TopologicalPhase`**, as a new step within `OptimizationPipeline.run()` (`optimizer/phases.py:265`) or as part of `SpectralInitializer.initialize()` when `component_groups` are present.

Specifically:
- If `constraints.component_groups` is non-empty, call `HierarchicalGroupInitializer.initialize(netlist, board, constraints)` instead of (or in addition to) the default spectral init.
- The resulting positions replace the `initial_state` passed to `GeometricPhase`.
- The `TopologicalPhase` still runs first (zones, cluster detection), but its output positions for grouped components are overridden by the hierarchical init.

**Key files affected:**
- `optimizer/phases.py` — `OptimizationPipeline.run()` or `TopologicalPhase.run()`
- `optimizer/initialization.py` — new `HierarchicalGroupInitializer` class alongside `SpectralInitializer`
- `heuristics/topological_init.py` — possibly feed group info into the topological graph
- `io/config_loader.py` — `ComponentGroup` is the input schema (no changes needed unless we add init-specific fields)

---

## Success Criteria

1. **Functional groups start within their spread constraints.** After initialization, for each group in `component_groups`, the pairwise diameter ≤ `max_spread_mm` (or within 10% margin). No component in a gate-drive group starts across the board from its IGBT.

2. **Phase 1–2 loss trajectories improve.** With correct intra-group topology at epoch 0, `GroupClusterLoss` should be near zero from the start, and the optimizer converges to a solution with lower final loss or in fewer epochs.

3. **Wirelength is not degraded.** The hierarchical approach should not produce measurably worse wirelength than the current spectral init, since inter-group topology is preserved via the coarsened adjacency.

4. **Falls back gracefully.** If no `component_groups` are defined, behavior is identical to current spectral init. For groups whose bounding-box diagonal exceeds 30% of the board diagonal: keep members as individual singleton super-nodes in the group-level graph. Place each member at its anchor point (for anchored components), zone-assigned position (for zone-bound components), or spectral-initialized position (for unconstrained members). Log a warning: "Group <name> spans >30% of board diagonal — coarsening disabled, members placed individually."

---

## Rejected Alternatives

**Curriculum tuning (earlier GroupClusterLoss activation):** Activating `GroupClusterLoss` at curriculum epoch 0 with a higher weight was considered as a simpler alternative. This approach was rejected because: (a) a strong group-clustering loss applied to scattered initial positions creates local minima — the loss pulls group members together while wirelength loss pulls them toward connected-but-distant components, and gradient descent stalls in the tension; (b) gradient descent from scattered positions against a quadratic grouping penalty converges slowly regardless of weight magnitude — pre-clustering provides a convex neighborhood where convergence is fast; and (c) curriculum tuning is complementary, not competing — early loss activation can be retained after pre-clustering as an additional convergence guarantee. The two approaches compound: pre-clustering handles the coarse topology, curriculum tuning handles the fine refinement.

**Cluster-then-embed (single-level):** Placing each group as a tight cluster at its centroid and running standard single-level spectral init avoids the coarsening/explosion abstraction entirely. Rejected because: the single-level approach loses inter-group topology — spectral init positions group centroids purely by net connectivity without respecting the group-level adjacency structure. The coarsening step preserves which groups should be near each other based on shared nets, providing better global group layout than centroid-only embedding.

## Scope Boundaries

### In scope

- `HierarchicalGroupInitializer` class in `optimizer/initialization.py`
- Integration into `OptimizationPipeline` (Phase 1 → Phase 2 transition)
- Intra-group micro-placement (force-directed solver for small groups)
- Group-level coarsening and spectral embedding
- Exploding back to component positions
- Handling of ungrouped components (pass through as singletons)

### Out of scope (for this document)

- Changes to the curriculum phases or loss weights — those remain unchanged; the initializer just provides better starting positions
- Changes to `GroupClusterLoss` or `ProximityLoss` — they continue to work as before (just see lower loss from epoch 0)
- Template groups (`template_group` field on `ComponentGroup` for isomorphic layout) — may benefit from pre-clustering but not addressed here
- Auto-detection of groups from connectivity — the `component_groups` from the YAML config are the source of truth
- Multi-objective NSGA-II phase — the hierarchical init can supply the initial population but group-aware diversity seeding is out of scope

---

## Risks and Mitigations

### Risk 1: Large-spanning groups cannot be coarsened cleanly

The star-ground cluster may span the entire board (GND referenced everywhere). Coarsening it into a single super-node destroys useful spatial information: the optimizer needs to know that the star point is anchored at a specific position.

**Mitigation:** Detect "spanning groups" where `max_spread_mm` exceeds, say, 30% of the board diagonal. For these groups:
- Skip coarsening (keep members as individual components in the group-level graph).
- Place members at their anchor points or zone-assigned positions.
- Log a warning that the group was not pre-clustered.

Heuristic: `is_spanning = max_spread_mm > 0.3 * sqrt(board.width^2 + board.height^2)`

### Risk 2: Overlapping groups (one component in multiple groups)

A component can technically appear in multiple `ComponentGroup` lists (e.g., a gate driver IC belongs to both "gate_drive_A" and "half_bridge"). This breaks the coarsening assumption that each component maps to exactly one super-node.

**Mitigation (3 levels):**
1. **Hard error** if a component appears in multiple groups — force the config to be fixed. Simplest but restrictive.
2. **First-wins assignment** — assign component to the first group that lists it; issue a warning. Simple but arbitrary.
3. **Group merging** — if two groups share one or more components, merge them into a single micro-placement solve. Most correct but complex.

**Recommendation:** Start with (2), log a warning, and escalate to (3) if real-world configs need it. Track merged-component frequency as a metric.

### Risk 3: Micro-placement quality depends on solver choice

Force-directed layout can produce different results depending on random seed, iteration count, and cooling schedule. Poor local layouts become "frozen in" and may resist correction during gradient descent.

**Mitigation:**
- Use a deterministic initialization for the force-directed solver (fixed seed).
- Run the solver with high iteration count since groups are small (fast).
- Validate post-init: if any group's diameter exceeds `max_spread_mm * 1.2`, fall back to a simpler radial placement (components arranged in a circle at `max_spread_mm / 2` radius from centroid).
- The grouping loss remains active as a safety net, but its role is proportional to how close pre-clustering already positioned group members. Pre-clustering reduces the optimizer's workload from "discover group topology + refine relative positions" to "refine relative positions within already-correct clusters." The safety net catches small positioning errors (e.g., a decoupling cap placed 8mm from its IC instead of 5mm). It does not attempt to reassemble groups that pre-clustering scattered — that scenario is prevented by the Success Criteria. This is consistent with the core motivation: unguided gradient descent from scattered positions is wasteful; guided refinement from near-correct positions is efficient.

### Risk 4: Pre-clustering could produce overlapping groups

If two group centroids end up close together in the global spectral embedding, their expanded components may overlap badly.

**Mitigation:** The existing overlap loss (`overlap: 200.0` in Phase 2) handles this. Additionally, after explosion, run one pass of `_separate_coincident_components()` (`optimizer/initialization.py:280`) to spread any components at identical positions.

---

## Unknowns (to resolve during implementation)

### 1. Best micro-solver for intra-group layout

Candidates:
- **Force-directed** (`heuristics/force_directed.py`): Well-understood, already in codebase, good for small dense graphs. Requires iteration count tuning.
- **Spectral** (`optimizer/initialization.py` compute_spectral_coordinates): Deterministic, no iteration needed, but produces linear embeddings that don't respect component footprints and may place components at identical coordinates.
- **Constraint satisfaction** (PCL/SAT): Overkill for small groups but guarantees proximity constraints are met exactly.

**Recommendation:** Start with force-directed (it's already there, handles proximity rules naturally), benchmark against spectral for groups of varying sizes.

### 2. Handling boundary conditions at group edges

When a group's centroid is placed near a board edge in Phase 3, the micro-layout from Phase 1 may position some members outside the board boundary. Two options:
- **Clip to board** after explosion (simple, but breaks intra-group topology).
- **Shift the entire group** inward to keep all members in-bounds (preserves topology, may conflict with desired centroid position).

**Recommendation:** After explosion, apply the existing `boundary` loss early. If the group intersects an edge, shift the entire group inward by the overflow amount.

### 3. Should pre-clustering be exposed as a separate Heuristic?

The existing `Heuristic` framework (`heuristics/base.py`) supports `HeuristicPriority.INITIALIZATION`. Pre-clustering could be added as `HierarchicalGroupInitializationHeuristic` alongside `TopologicalInitializationHeuristic`. This would give it access to the full `PlacementContext` including constraints, board, and netlist.

**Tradeoff:** Heuristic framework adds abstraction but fits the existing architecture. Direct integration into `SpectralInitializer` is simpler but less composable.

**Recommendation:** Implement as a new initializer class in `optimizer/initialization.py` first (simpler, faster to validate). Consider refactoring into a Heuristic if the pattern proves useful across multiple initialization strategies.

### 4. Interaction with ZoneAwareSpectralInitializer

`ZoneAwareSpectralInitializer` (`optimizer/zone_aware_init.py`) already partitions components by zone and places each zone independently. If groups cross zone boundaries, pre-clustering must either:
- Place the group in the zone of its majority of members, or
- Refuse to pre-cluster cross-zone groups.

**Recommendation:** If a group spans multiple zones, skip pre-clustering for that group and let the zone-aware init handle its members individually. Log a warning.

---

## References

| File | Role |
|------|------|
| `optimizer/initialization.py` | Existing `SpectralInitializer` and `compute_spectral_coordinates` — target for new `HierarchicalGroupInitializer` |
| `io/config_loader.py` | `PlacementConstraints`, `ComponentGroup`, `GroupSeparation` — input schema |
| `heuristics/topological_init.py` | `TopologicalInitializationHeuristic` — existing init path that also ignores groups |
| `losses/grouping.py` | `GroupClusterLoss`, `ProximityLoss`, `GroupSeparationLoss` — losses that currently rediscover groups |
| `optimizer/phases.py` | `OptimizationPipeline` — integration point for the hierarchical init |
| `optimizer/curriculum.py` | Phases 2/3 boundary at epoch 3000 — the motivation for why pre-clustering matters |
| `heuristics/force_directed.py` | `compute_force_directed_layout` — candidate micro-solver for Phase 1 |
| `core/state.py` | `PlacementState.from_positions()` — target data structure for exploded positions |
