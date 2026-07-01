---
date: 2026-07-01
topic: placement-initialization-states
focus: Domain-specific knowledge and codified placement rules for better initial states
mode: repo-grounded
---

# Ideation: Better Placement Initialization States

## Grounding Context

**Codebase Context:** temper-placer is a JAX-based gradient-descent PCB placement optimizer for the Temper induction cooker. 40+ differentiable loss terms with 5-phase curriculum learning (spread → feasibility → design_rules → performance → refinement). Current init approaches (random, spectral, zone-aware spectral, learned GNN, topological heuristic) use none of the domain knowledge already codified in `PlacementConstraints` — zones, groups, proximities, clearances, thermal, HV/LV separation, critical loops, star grounds.

**Critical gap:** `initialize_training_state()` in `train.py:286` doesn't receive `PlacementConstraints` at all.

**Past Learnings:** composable constraint stacking (ghost pads → seed filtering → channel scoring); PlacementState SSOT for seeding; rotation logits-vs-softmax trap; ascending-order principle for seed scoring; invariant chain for constraint enforcement.

**External Context:** DREAMPlace/AutoDMP analytical-then-differentiable pipeline; HiePlace core-component-first DP placement; force-directed PCB adaptation with fixed anchors; DPP/FPS seed diversity; molecular dynamics equilibration pattern.

## Topic Axes

1. Constraint injection & rule encoding — How domain rules get mathematically encoded as initialization biases
2. Seed diversity & multi-start — Multi-seed generation, diversity-preserving selection, seed filtering/ranking
3. Pipeline composition & integration — How init stages compose, data flow between init and optimizer
4. Thermal & safety bootstrapping — Edge-constrained placement for power devices, HV/LV safety separation
5. Group & proximity bootstrapping — Using functional groups and proximity constraints to pre-cluster related components

## Ranked Ideas

### 1. Constraint-Passthrough Init Pipeline
**Description:** Modify `initialize_training_state()` in `train.py:286` to accept and thread the full `PlacementConstraints` object to every registered initializer. 3-line signature change — constraints already parsed, validated, and available at call site; simply dropped on the floor today. Prerequisite for all other constraint-aware init ideas.

**Axis:** Pipeline composition & integration

**Basis:** `direct:` The gap is observable in code — `initialize_training_state()` does not pass constraints to the initializer. `direct:` Composability pattern from docs/solutions establishes that constraint injection into placement stages follows an additive, stackable pattern.

**Rationale:** Unblocks 6+ constraint-aware init ideas without code duplication or side channels. Zero risk of regressing existing behavior.

**Downsides:** None — pure data-flow fix.

**Confidence:** 95%
**Complexity:** Low
**Status:** Unexplored

### 2. Constraint-Weighted Spectral Laplacian
**Description:** Extend the spectral initializer's adjacency matrix so edge weights encode domain rules: critical-loop nets boosted 5×, HV↔LV edges negatively weighted, proximity-constrained pairs amplified. Single eigendecomposition naturally clusters components into constraint-respecting spatial partitions at zero extra solver cost.

**Axis:** Constraint injection & rule encoding

**Basis:** `direct:` Adjacency matrix already in `build_adjacency_matrix(netlist)` — edge weights are the natural extension point. `PlacementConstraints` provides `critical_loops`, `clearances`, `groups`, `proximity_constraints`. `reasoned:` The normalized Laplacian already handles varying node degrees; varying edge weights is the natural extension.

**Rationale:** Current spectral init treats every net equally. Constraint-weighted Laplacian seeds topology correctly so the optimizer doesn't fight inherited topology. Zero extra runtime.

**Downsides:** Negative edge weights need stabilization (shift to PSD). Unary constraints (e.g., "IGBT near board edge") don't map cleanly to pairwise edge weights.

**Confidence:** 80%
**Complexity:** Low-Medium
**Status:** Unexplored

### 3. Constraint-Cascade Alternating Projections (C-CAP)
**Description:** Start from random positions, iteratively project each component onto feasible sets in round-robin (HV/LV half-spaces, keepout interiors, zone containment, board-edge). After 10-20 cheap cycles, all hard geometric constraints satisfied by construction. Feeds into PlacementState as guaranteed-feasible initial positions.

**Axis:** Constraint injection & rule encoding

**Basis:** `external:` Feasibility pump heuristics from MIP solvers; convex alternating projections (von Neumann, 1950). `direct:` Every hard geometric constraint in `PlacementConstraints` is expressible as a convex set.

**Rationale:** Random init places 30-50% of components in forbidden zones. C-CAP guarantees feasibility at t=0, shifting the optimizer from "fix infeasibility" to "refine for optimality."

**Downsides:** Non-convex intersections have no convergence guarantee. Some constraint combinations may oscillate. Needs best-effort fallback.

**Confidence:** 75%
**Complexity:** Medium
**Status:** Unexplored

### 4. DPP-Diversified Multi-Seed with Cheap-Eval Gate
**Description:** Generate 20-50 seeds from spectral variants, use DPP to select K maximally diverse, run cheap triage (30 iter), promote best seed to full optimization. Hedges against single-seed brittleness with principled diversity.

**Axis:** Seed diversity & multi-start

**Basis:** `external:` DPPs for diversity-preserving subset selection (Kulesza & Taskar, 2012). `direct:` Spectral init has tunable parameters; diversity comes from varying those.

**Rationale:** Single-seed is high-variance lottery. DPP + cheap triage provides insurance against catastrophically bad seeds at <3% of total optimization cost.

**Downsides:** DPP kernel construction on placement similarity is non-trivial. Triage evaluation must correlate with final quality.

**Confidence:** 70%
**Complexity:** Medium
**Status:** Unexplored

### 5. Coarse-Grid Differentiable Probe (DPO-Init)
**Description:** Run the optimizer at coarse resolution (quarter-grid, collapsible footprints) for 50 steps as initialization. Initialization IS the optimizer at reduced fidelity — inherits all constraint encoding automatically.

**Axis:** Pipeline composition & integration

**Basis:** `direct:` `make_train_step` and `CompositeLoss` already differentiable. `reasoned:` Eliminates information loss at init/optimize boundary.

**Rationale:** Every new loss term or constraint automatically reaches initialization without code duplication.

**Downsides:** Coarsening heuristics may introduce artifacts. Coarse basin may differ from full-resolution basin. More expensive than static init.

**Confidence:** 65%
**Complexity:** Medium-High
**Status:** Unexplored

### 6. Thermal-Potential-Field Anchoring
**Description:** Compute thermal potential field from copper density, via-to-ground-plane density, edge proximity, and thermal exclusion zones. Place power devices at field minima as fixed anchors. Place remaining components relative to anchored power devices.

**Axis:** Thermal & safety bootstrapping

**Basis:** `direct:` `PlacementConstraints.thermal_constraints` exist but never reach init. `direct:` Curriculum Phase 3 activates `thermal_spread` at epoch 3000 — 37.5% of training without thermal awareness. `external:` Force-directed anchor-then-relax from HiePlace.

**Rationale:** Power device placement drives the entire thermal envelope. Anchoring prevents cascade failure where moving a power device forces re-optimization of all components placed relative to it.

**Downsides:** Freezing constrains optimizer degrees of freedom. Potential field computation is ad-hoc. Only benefits 4-6 power devices.

**Confidence:** 85%
**Complexity:** Low
**Status:** Unexplored

### 7. Hierarchical Group-Centroid Pre-Clustering
**Description:** For each functional group, solve local micro-placement internally. Coarsen each group to a super-node with aggregate connectivity. Run spectral embedding at group level. Explode super-nodes back to member components at pre-solved relative offsets.

**Axis:** Group & proximity bootstrapping

**Basis:** `direct:` `PlacementConstraints` defines functional groups and proximity constraints that never reach init. `direct:` Curriculum Phase 3 activates `grouping` loss at epoch 3000. `external:` HiePlace core-component-first DP placement; multilevel graph coarsening from VLSI.

**Rationale:** Reduces dimensionality from N components to G groups. Optimizer inherits correct intra-group topology — only needs to position groups, not individual components.

**Downsides:** Large-spanning groups can't be cleanly coarsened. Internal micro-placement quality depends on local solver. Overlapping groups need conflict resolution.

**Confidence:** 90%
**Complexity:** Medium
**Status:** Unexplored

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| 1 | Zone-Hard-Constrained Spectral | Over-constrained — ill-conditioned eigenproblem; weaker form (constraint-weighted Laplacian) sufficiency covers same ground |
| 2 | Constraint-Conditioned Learned GNN | Too expensive vs. likely value; requires training corpus + serving infra; future work |
| 3 | Distance-Geometry Bound Smoothing | Not actionable — contradictory bounds (min + max distance) common; triangle-inequality smoothing fails on them |
| 4 | Difficulty-Stratified Seed Exploration | Esoteric; adds complexity without clear advantage over simpler DPP diversity |
| 5 | Run-to-Run Transfer via Cached Templates | Already covered by corpus runner/snapshots workflow; infrastructure feature, not novel init strategy |
| 6 | Curriculum-Ladder Staged Warm-Starting | Doubles init cost; premature — prove constraint-aware init first |
| 7 | Safety-Feasibility Polygon Packing | Over-engineered; C-CAP projection handles same constraints more elegantly |
| 8 | Power-Weighted Thermal Voronoi | Overkill for 4-6 power devices; simple thermal anchoring handles same problem |
| 9 | Star-Ground Ascending-Order Scoring | Too narrow; subsumed into hierarchical group pre-clustering |
| 10 | Subcircuit Template Hashing (WL Kernels) | High implementation burden, uncertain match rate; better when corpus of good placements exists |
| 11 | Composable Constraint-Bias Field Pipeline | Soft-constraint complement to C-CAP; deferred to avoid diluting survivor set |
| 12 | HV/LV Binary Feasibility Mask | Folded into C-CAP (half-space projection) + Thermal Anchoring |
