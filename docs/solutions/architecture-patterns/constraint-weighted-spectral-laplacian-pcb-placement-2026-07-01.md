---
title: "Pattern: Constraint-Weighted Spectral Laplacian for Domain-Aware PCB Placement Initialization"
date: 2026-07-01
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "Encoding PCB domain constraints (proximity, clearance, critical loops, HV/LV separation, group coherence) as edge weight modifications on a spectral graph embedding"
  - "Computing initial placement coordinates from a constraint-augmented connectivity graph Laplacian where component clusters emerge naturally from the eigenvector structure"
  - "Precomputing constraint-to-net mappings to avoid repeated O(N_nets * avg_pins^2) lookups during weight derivation"
  - "Stabilizing a Laplacian with negative off-diagonal entries (repulsion) into a positive-semidefinite (PSD) matrix without full eigendecomposition"
  - "Falling back to plain spectral initialization when no constraints are loaded, maintaining backward compatibility"
tags:
  - spectral-graph-embedding
  - laplacian-eigenmaps
  - constraint-weights
  - gershgorin-circle-theorem
  - psd-stabilization
  - pcb-placement
  - domain-constraints
  - edge-weight-strategies
  - proximity-spring-constant
  - critical-loop-magnetic-energy
  - hv-lv-repulsion
  - clearance-coulomb
  - group-coherence
---

# Pattern: Constraint-Weighted Spectral Laplacian for Domain-Aware PCB Placement Initialization

## Context

Spectral placement computes an initial (x, y) embedding by taking the 2nd and 3rd
eigenvectors of the Laplacian matrix derived from the PCB connectivity graph.
This is effective for minimizing quadratic wirelength, but the standard approach
has no visibility into physical design intent: proximity constraints, groups that
must stay coherent, critical loops that demand tight geometry, or high-voltage
isolation requirements.

Prior approaches encoded these constraints as penalty terms in the gradient-based
optimizer. However, the optimizer starts from an initial placement; a poor start
means more iterations, more local minima, and more force-directed correction cycles.
Constraint-weighted spectral initialization moves the constraint-aware signal into
the Laplacian itself, so the spectral embedding naturally clusters components into
constraint-respecting spatial partitions from the first eigenvector solve.

## Guidance

### 1. Architecture Overview

The pattern has four layers that compose linearly:

```
┌──────────────────────────────────────────────────────────────┐
│ YAML Constraints (PCL)  +  PlacementConstraints  +  Netlist  │
└──────────────────────┬───────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │ ConstraintMapper│  O(N_nets × avg_pins²) precompute
              │   (U1)          │  ────────────────────────────
              │ adjacency_nets  │  (ref_a, ref_b) → [Net]
              │ loop_components │  loop_name → [ref]
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │ 5 Weight        │  per-edge constraint contributions
              │ Strategies (U2) │  ────────────────────────────
              │ proximity       │  w_prox = k_tier / max_dist
              │ group_coherence │  w_coh = w_base * (1+α*fraction)
              │ critical_loop   │  w_loop = I_rms²*f_sw/max_area
              │ hv_lv_repulsion │  w_rep = -C_iso/clearance²*(ΔV/Vref)
              │ clearance       │  w_clr = -C_iso/clearance²
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │ Laplacian       │  w_ij = w_base_net/(k-1) + constraint_w
              │ Construction    │  L = D^{-1/2}(D-A)D^{-1/2}
              │ + PSD Shift     │  Gershgorin bound → λ_min ≥ 0
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │ Spectral        │  eigen(L, k=3) → 2nd/3rd vectors
              │ Embedding       │  → board-scaled (x,y) positions
              └─────────────────┘
```

Key design decisions:
- **Per-edge `constraint_weight` dict** (`dict[(i, j), float]`) is separate from
  per-net `Net.weight`. Net weights represent routing importance; constraint weights
  represent physical topology constraints. They compose by addition in the adjacency
  matrix without coupling concerns.
- **`precomputed_laplacian`** parameter on `SpectralInitializer.initialize()`
  accepts a pre-built Laplacian array. When provided, the initializer skips its
  internal adjacency construction and uses the caller-supplied matrix. When
  `None`, plain spectral initialization runs (backward compatible).

### 2. ConstraintMapper: O(N_nets × avg_pins²) Precompute

`ConstraintMapper` (`constraint_weights.py:49`) resolves constraint component
references to netlist nets once, avoiding per-strategy recomputation.

```
ConstraintMapper.build(pcl, placement_constraints, netlist)
  ├── _build_adjacency_from_pcl(pcl, netlist)
  │     For each AdjacentConstraint(a, b):
  │       comp_to_nets[a] ∩ comp_to_nets[b] → shared nets
  │       Sorted key (min(a,b), max(a,b)) → list[Net]
  │     O(N_constraints × avg_nets_per_comp)
  │
  └── _build_loop_from_pcl(pcl, placement, netlist)
      └── _build_loop_from_critical_loops(placement, netlist)
            For each CriticalLoop:
              netlist.get_net(net_name) → collect unique refs
              O(N_loops × N_nets_in_loop)
```

The resulting `adjacency_nets` dict maps component-pair keys to lists of `Net`
objects shared by both components. The `loop_components` dict maps loop names to
ordered component reference lists.

A `ConstraintMapper` with empty input is valid and produces empty mappings — no
crashes, no special-casing required downstream.

### 3. Five Weight Derivation Strategies

Each strategy is a function that computes a scalar weight contribution for a
pair of components. Strategies may produce positive weights (attraction/pull)
or negative weights (repulsion/push). All five compose additively into the
`constraint_weight` dict.

#### 3.1 Proximity (spring constant from max_distance)

```
w_proximity = k_tier / max_distance_mm
```

where `k_tier` is `K_HARD=100.0`, `K_STRONG=10.0`, or `K_SOFT=1.0` depending on
the constraint's tier. A tighter max distance produces a stronger spring constant,
magnetically pulling the components together in the embedding.

Reference: `constraint_weights.py:209-223`

#### 3.2 Group Coherence (ratio scaling)

```
w_coherence = w_base × (1 + alpha_coherence × group_fraction)
```

where `group_fraction = |nets_in_group ∩ component_nets| / |component_nets|`.
Components with a high fraction of their nets shared with a defined component
group get a proportional coherence boost. `alpha_coherence=2.0` controls
amplification.

Reference: `constraint_weights.py:259-268`

#### 3.3 Critical Loop (magnetic energy proxy)

```
w_loop = w_base × I_rms² × f_switching / max_area_mm2
```

Derived from the physical relationship between loop area, RMS current, and
switching frequency — smaller allowed areas produce larger edge weights,
corresponding to tighter magnetic coupling in the embedding. Components in
the same critical loop are pulled together.

Reference: `constraint_weights.py:325-337`

#### 3.4 HV/LV Repulsion (negative weights)

```
w_repulsion = -C_iso / clearance_mm² × (V_diff / V_ref)
```

Produces negative edge weights between components on nets with different safety
categories (e.g., HighVoltage vs. Signal). The inverse-square scaling mirrors
Coulomb repulsion: components that must stay apart push each other away in the
embedding. `C_iso=21600.0` is the isolation calibration constant.

Reference: `constraint_weights.py:377-389`

#### 3.5 Clearance (Coulomb-like for net-class cross-product)

```
w_clearance = -C_iso / clearance_mm²   (cross-domain only)
```

Generalized clearance repulsion across all net-class cross-product pairs.
Same-domain pairs receive zero contribution. This strategy complements HV/LV
repulsion by covering all net-class boundaries uniformly.

Reference: `constraint_weights.py:467-479`

### 4. Laplacian Construction with Constraint Weights

The per-edge weight is the sum of base connectivity weight and constraint
contributions (`constraint_weights.py:702-763`):

```
w_ij = ∑_{net connecting i,j} (1 / (k-1)) + constraint_weight.get((i, j), 0)
```

The base weight uses the clique model: each net of degree k distributes
1/(k-1) weight to each edge in the clique. Constraint weights add or subtract
from this.

The resulting adjacency matrix A is used to compute the normalized Laplacian:

```
L = I - D^{-1/2} A D^{-1/2}
```

### 5. PSD Stabilization via Gershgorin Circle Theorem

Negative off-diagonal entries (from repulsion strategies) can make the Laplacian
indefinite. Eigendecomposition of an indefinite Laplacian produces complex
eigenvalues — breaking the spectral embedding. The system avoids full
eigendecomposition by bounding λ_min:

```
For each row i:
    center_i = L[i,i]
    radius_i = Σ_{j≠i} |L[i,j]|
    λ_min_bound = min_i (center_i - radius_i)
```

This is O(n²) — no eigendecomposition needed. If λ_min_bound < 0, a shift is
applied:

```
L_stable = L + |λ_min_bound| × I
```

The shift is capped at 50% of the estimated spectral radius (via Gershgorin
upper bound). If the shift would exceed this cap, the system falls back to an
attraction-only Laplacian (clamping all off-diagonals to non-negative).

Reference: `constraint_weights.py:610-694`

### 6. Wiring into the Initializer

`SpectralInitializer.initialize()` (`initialization.py:235-296`) accepts
`precomputed_laplacian: Array | None`:

```python
if precomputed_laplacian is not None:
    adjacency = precomputed_laplacian
    use_normalized = False  # already applied in constraint_weights
else:
    adjacency = build_adjacency_matrix(netlist)
    use_normalized = self.normalized_laplacian
```

The caller in `train.py` (`train.py:322-358`) orchestrates the full chain:

```
method == "constraint_weighted_spectral":
    if constraints:
        constraint_weights = compute_constraint_weight_dict(...)
        laplacian = compute_laplacian_from_weights(netlist, constraint_weights)
        laplacian = apply_psd_shift(laplacian)
    else:
        laplacian = None                        # plain spectral fallback
    initializer.initialize(netlist, board,
        precomputed_laplacian=laplacian)
```

When no constraints are loaded, the system falls back to plain spectral
initialization with a log message.

### 7. Calibration Knobs

| Constant | Default | Controls |
|----------|---------|----------|
| `K_HARD` | 100.0 | Proximity spring for HARD tier |
| `K_STRONG` | 10.0 | Proximity spring for STRONG tier |
| `K_SOFT` | 1.0 | Proximity spring for SOFT tier |
| `C_iso` | 21600.0 | Inverse-square isolation scaling |
| `alpha_coherence` | 2.0 | Group fraction amplification |
| `PSD_SHIFT_MAX_RATIO` | 0.5 | Max shift as fraction of spectral radius |

All constants are overridable per-design via `calibration` dict passed to
`compute_constraint_weight_dict()`.

### 8. Strategy Toggle Model

Strategies are individually toggleable:

```python
strategies = {
    "proximity": True,
    "group_coherence": True,
    "critical_loop": True,
    "hv_lv_repulsion": False,   # off by default (expensive)
    "clearance": False,          # off by default (expensive)
}
```

Repulsion strategies are off by default because they scan all net-class
cross-product pairs, which is O(N_nets × N_pins²). Enable only for boards
with heterogeneous voltage domains.

### 9. Verification

| Layer | What it proves | Technique |
|-------|---------------|-----------|
| Unit | Weight formula correctness, tier monotonicity, edge cases | `test_constraint_weights_unit.py` |
| Properties | Symmetry, non-negativity baseline, PSD preservation, idempotency, determinism | Hypothesis `@given` in `test_constraint_weights_properties.py` |
| Ablation | Per-strategy effect on placement quality vs. plain spectral | `test_constraint_weights_ablation.py` |
| Integration | End-to-end constraint passthrough from CLI config to initial positions | `test_constraint_passthrough_init.py` |

## Consequences

- **Positive weights** (proximity, group coherence, critical loop) act as
  attractive springs, clustering constrained components in the spectral embedding.
- **Negative weights** (HV/LV repulsion, clearance) push components apart,
  creating spatial separation in the eigenvector space.
- The Gershgorin-based PSD shift is O(n²) vs. O(n³) for full eigendecomposition
  validation — practical for netlists up to thousands of components.
- The 50% shift cap with attraction-only fallback guarantees stability even when
  repulsion weights dominate the adjacency.
- Declarative constraint-to-weight pipeline: changing a YAML constraint or tier
  automatically propagates into the Laplacian and the resulting embedding.
  No code changes needed for constraint edits.
- Fallback to plain spectral when no constraints are loaded preserves existing
  behavior and avoids unnecessary computation.

## Related

- `packages/temper-placer/src/temper_placer/placement/constraint_weights.py` — ConstraintMapper, 5 weight strategies, PSD shift, Laplacian construction
- `packages/temper-placer/src/temper_placer/optimizer/initialization.py` — `SpectralInitializer.initialize(precomputed_laplacian=...)`
- `packages/temper-placer/src/temper_placer/optimizer/train.py` — constraint_weighted_spectral orchestration in `_run_optimizer()`
- `packages/temper-placer/src/temper_placer/topological/graph.py` — `TopologicalGraph` for adjacency/separation edge representation (upstream of weight derivation)
- `packages/temper-placer/src/temper_placer/io/config_loader.py` — `CriticalLoop`, `PlacementConstraints`, `ComponentGroup` YAML schema
- `packages/temper-placer/tests/optimizer/test_constraint_weights_unit.py` — unit tests for all 5 strategies and PSD shift
- `packages/temper-placer/tests/optimizer/test_constraint_weights_properties.py` — Hypothesis PBT invariants
- `packages/temper-placer/tests/optimizer/test_constraint_weights_ablation.py` — ablation experiments
- `packages/temper-placer/tests/optimizer/test_constraint_passthrough_init.py` — end-to-end constraint passthrough tests
- `docs/solutions/architecture-patterns/pcl-constraint-system-triple-extension-2026-07-01.md` — sibling pattern (PCL constraint families, loss functions, semantic bridge)
