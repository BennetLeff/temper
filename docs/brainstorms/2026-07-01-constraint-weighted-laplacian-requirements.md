---
date: 2026-07-01
topic: constraint-weighted-laplacian
---

# Constraint-Weighted Spectral Laplacian Initialization

## Problem Statement

The spectral initializer in `placement/spectral.py` constructs a graph Laplacian from netlist connectivity where every net edge carries uniform weight (`1/(k-1)` for a k-pin net). This uniform weighting discards all domain knowledge: the gate-drive loop, HV/LV separation boundary, thermal coupling pairs, and critical current paths all look identical to the eigendecomposition. The resulting spectral embedding produces positions that minimize _wirelength_ for all nets equally — not positions that satisfy the most important constraints fastest.

Meanwhile, the PCL constraint system (`pcl/constraints.py`) already defines precise geometric requirements: `max_distance_mm` for adjacent pairs, `min_distance_mm` for separated pairs, `enclosing` zones with margin, and `loop_area` limits. The net class system (`design_rules.py:TMEPER_NET_CLASSES`) defines `safety_category` (HV/LV/AC/iso), `creepage_mm`, and `clearance` in physical millimeters. None of this reaches `SpectralPlacer.compute_placement()`.

The hypothesis: if edge weights in the Laplacian construction encode constraint semantics, the spectral embedding will naturally pull critical loops tight, push voltage domains apart, and pre-group functional clusters — reducing the optimization burden on the gradient-descent phase and improving convergence quality.

The approach replaces fully-arbitrary per-net weight multipliers with a smaller set of per-constraint-type calibration constants derived from physical reasoning. The constants (k_HARD, k_STRONG, k_SOFT, C_iso, α) have clear semantic meaning: force budgets for HARD/STRONG/SOFT constraint tiers, isolation repulsion strength, and coherence priority. They are calibrated once against the regression corpus (see Unknowns U1), then held fixed across all designs.

---

## Proposed Approach: Edge Weights from Constraint Definitions

### Core Idea

Instead of `weight = 1/(k-1)` for every net, compute a per-net weight from the union of constraints that reference the net's pins:

```
W_net = f(constraints, net_matadata, net_class_rules)
```

This replaces the single scalar `weight = 1/(k-1)` on line 76 of `placement/spectral.py` with a per-net scalar weight derived from constraint contributions.

### Constraint-to-Net Mapping Layer

A `ConstraintMapper` pre-processing step resolves PCL constraint component references to netlist nets. For each constraint pair (c1, c2), it iterates all nets, checks whether both components appear in the net's pin list, and builds a `{(c1, c2): [net1, net2, ...]}` mapping. This is a one-time O(N_nets × avg_pins²) precompute, producing a `dict[tuple[str, str], list[Net]]` consumed by all five weight-derivation strategies.

### Constraint-to-Weight Mapping Proposals

The central design question: **can weight magnitudes be derived analytically from physical parameters in the constraint definitions, rather than chosen as magic multipliers?**

#### 1. Proximity Constraints → Spring Constants (k = F / x)

`AdjacentConstraint.max_distance_mm` defines a maximum allowed separation. In physical terms, a spring with spring constant k exerts force F = kx when displaced by distance x. If the optimizer's task is to minimize x to at most `max_distance_mm`, we can set the edge weight proportional to the required spring constant:

```
k_spring = 2 * F_target / max_distance_mm
```

where `F_target` is the "force budget" allocated to this constraint (derived from the `ConstraintTier`: HARD ≈ 100 N, STRONG ≈ 10 N, SOFT ≈ 1 N). The factor 2 accounts for two springs in series.

A net with `max_distance_mm=5.0` (tight gate-drive loop) gets weight ∝ 1/(5.0) = 0.2 per unit force, while a net with `max_distance_mm=50.0` (loose thermal coupling) gets weight ∝ 1/(50.0) = 0.02. This is up to 10x difference — not from an arbitrary multiplier, but from the designer's own distance specification.

For nets with no explicit adjacency constraint, the "effective" max distance defaults to the board diagonal — producing a small baseline weight (~0.3% of the tightest constraint weight for a 300mm board diagonal).

**Open question**: Does `1/max_distance` actually produce the right spectral embedding? The Laplacian's smallest non-zero eigenvectors minimize the Rayleigh quotient Σ w_ij·(x_i - x_j)². A spring constant interpretation suggests this is equivalent to minimizing potential energy of a spring network. But spectral methods position components to minimize _squared_ displacement, while real springs minimize _linear_ displacement. The mapping from `k_spring` to `w_ij` in the Rayleigh quotient may need a square-root correction: `w_ij ∝ sqrt(F/max_distance)` to account for the quadratic energy landscape.

#### 2. Separation Constraints → Negative Weights (Repulsion)

`SeparatedConstraint.min_distance_mm` defines a minimum required separation. A pairwise repulsive force is needed, which maps to _negative_ edge weights in the adjacency matrix:

```
w_repulsion = -C_rep * (1 / min_distance_mm²)
```

where `C_rep` is a repulsion strength constant that must be determined. The `1/r²` form mirrors electrostatic repulsion (Coulomb's law), which is the closest physical analogy for "keep apart" constraints.

Alternatively, using clearance/creepage distance directly from `NetClassRules`:

When two nets belong to different safety categories (e.g., HV and LV), the required separation is the lattice-join clearance:
- HV-LV pairs require `max(HV.clearance, LV.clearance, HV.creepage_mm, LV.creepage_mm)` = 6mm (from `TEMPER_NET_CLASSES`)
- This is a **physical safety requirement**, not a preference
- Weight should scale with the severity of violation: `w = -C * (1 / clearance²) * voltage_difference`

The voltage difference factor makes HV-HV separation less repulsive (same domain) than HV-LV (dangerous cross-domain proximity). This is physically meaningful: HIPOT safety requirements care about voltage differential across barriers, not absolute voltage.

**Critical**: The stabilization problem (see Risk 1) means negative weights cannot be used naively. See below for PSD shift proposals.

#### 3. Group-Internal Nets (Coherence Boost)

Components within the same group (all members of a functional block, all components inside an `EnclosingConstraint.inner` list) share nets that should carry higher weight than nets crossing group boundaries. The rationale: the spectral embedding should pre-cluster functional blocks before optimizing their relative positions.

Proposed weight boost: `w_intra = w_base * (1 + α * group_coherence)`, where `group_coherence` is the fraction of a component's nets that stay within-group (a number in [0,1]). α = 2.0 makes intra-group nets up to 3x the base weight.

This is one of the few cases where a dimensionless multiplier is defensible: it encodes a ratio of _design intent_ (intra-group coherence priority) rather than a physical constant. However, the value of α should still be configurable per-design, not hardcoded.

#### 4. Critical Loop Nets (Vector Magnitude Boost)

For `LoopAreaConstraint`: the spectral embedding doesn't know what a "loop" is. But the nets that constitute the loop (identified by traversing `loop_name` → components in a `Loop` group → all nets between those components) are the most electrically critical paths. Their edge weights should dominate less critical nets.

Proposed weight: `w_loop = w_base * (1 / max_area_mm2) * I_loop_rms² * f_switching`

Where:
- `max_area_mm2` comes from the constraint itself (smaller allowed area → tighter pull)
- `I_loop_rms²` is the squared RMS current in the loop (proportional to stored magnetic energy E = ½LI²)
- `f_switching` is the switching frequency (di/dt rate)

This is _physically derived_: the stored magnetic energy in a loop is proportional to both the area (inductance) and the square of current. A commutation loop carrying 30A at 100kHz has 36,000× the energy-weight of a signal loop carrying 10mA at DC. This ratio is extreme but physically correct — the optimizer _should_ care 36,000× more about the gate-drive loop than a status LED.

The challenge: where does `I_loop_rms` come from? If it's not in the netlist or PCL, it must either be:
- Supplied by the designer in the constraint definition (add `loop_current_rms: float` to `LoopAreaConstraint`)
- Inferred from net class trace widths (wider trace → more current)
- Defaulted to 1.0 when unknown (fall back to pure area-driven weighting)

Components in a critical loop are resolved by checking the PCL configuration for a `components` list on the `LoopAreaConstraint`. When absent, the system falls back to group membership lookup (if a `ComponentGroup` named after the loop exists). When neither provides component references, the loop weight derivation is skipped and a warning is logged.

**Note on weight direction:** The weight `w_loop ∝ 1/max_area_mm2` means a TIGHTER constraint (smaller allowed area) produces a LARGER spectral weight — correctly pulling loop components closer together. The physical justification (stored magnetic energy) is separate from the weight magnitude: higher-energy loops have LARGER I²RMS and f_switching terms, further amplifying the weight. Both mechanisms push in the same direction: more electrically constrained loops get stronger spectral attraction.

#### 5. Safety-Category-Derived Weights

Net pairs that cross safety categories should receive modified weights based on the physical insulation requirement. Using `NetClassRules` data:

| Pair | Clearance from rules (mm) | Derived edge weight |
|------|--------------------------|---------------------|
| LV-LV (Signal-Signal) | 0.15 mm | `w_base` (no modification) |
| LV-HV | 6.0 mm (creepage) | `w_base - C_iso / 6.0²` |
| HV-AC | 6.0 mm (creepage) | `w_base - C_iso / 6.0²` |
| HV-HV | 6.0 mm (clearance) | `w_base` (same domain, no push-apart needed unless constrained) |

This table is derivable entirely from `TEMPER_NET_CLASSES` and the lattice join of `safety_category` values. No hardcoded multipliers.

The repulsion coefficient `C_iso` (isolation repulsion strength) still needs one free parameter to scale the physical clearance value into Laplacian space. This is the _single_ calibration constant the system requires. A candidate derivation: set `C_iso` such that the eigengap (λ₃ - λ₂) is maximized for a representative design, since a larger eigengap indicates stronger spectral clustering between voltage domains.

### Summary of Weight Derivation Strategy

| Constraint Type | Physical Input | Weight Formula | Free Parameters |
|----------------|---------------|----------------|-----------------|
| Adjacent (proximity) | `max_distance_mm`, `tier` | `w = k_tier / max_distance_mm` | `k_HARD`, `k_STRONG`, `k_SOFT` (force budget per tier) |
| Separated (repulsion) | `min_distance_mm`, voltage diff | `w = -C_iso / min_distance_mm² * (V_diff / V_ref)` | `C_iso` (single calibration constant) |
| Loop area | `max_area_mm2`, I², f | `w = w_base * I² * f / max_area_mm2` | None (fully determined by physics, modulo missing I data) |
| Group coherence | intra-group ratio | `w = w_base * (1 + α * coherence)` | `α` (coherence priority, dimensionless) |
| Base uniform | Net::weight field | `weight = 1/(k-1)` (unchanged for unconstrained nets) | None |

The total edge weight is the sum of all applicable constraint contributions: `w_total = w_base + Σ w_constraint_i`. For separated constraints, the contribution is negative.

The spectral Laplacian produces relative importance (attraction/repulsion strength), not absolute constraint enforcement. HARD constraints are encoded as very strong relative weights — typically 3+ orders of magnitude above SOFT weights in aggregate — but absolute violation prevention is the optimizer's responsibility, not the initializer's. The init provides a strong prior; the curriculum phases enforce the hard requirement through loss-term activation and weight scheduling.

**Note on proximity formula:** The `1/max_distance` mapping assumes linear scaling in the Rayleigh quotient. If empirical testing shows that `1/sqrt(max_distance)` produces better calibration (consistent with the quadratic energy landscape), the formula should be updated. This will be resolved during the proximity strategy's validation gate (see Implementation Priority).

---

### Implementation Priority

The five strategies are implemented incrementally with validation gates between each:

1. **Proximity (spring-constant)** — Simplest, directly maps to existing `AdjacentConstraint` data, validates the core weight-derivation mechanism.
2. **Group coherence** — Extends proximity to cluster-level scaling.
3. **Critical loops** — Requires new data fields (loop component enumeration, RMS current).
4. **HV/LV repulsion** — Requires PSD stabilization, highest implementation risk.
5. **Clearance weighting** — Generalizes HV/LV to arbitrary net-class pairs.

Each stage is validated against the regression corpus before proceeding to the next.

---

## Success Criteria

- **SC1. Spectral embedding separates HV and LV clusters without post-processing.** Given components with mixed `safety_category` assignments, the 2D spectral embedding from the weighted Laplacian naturally positions HV components in a distinct region from LV components, as measured by: At least 90% of HV-classified components are initialized on the correct side of the board's declared voltage-domain boundary (derived from `hv_clearance` zone geometry defined in `PlacementConstraints`), and this holds both before and after optimizer convergence. The boundary is defined by the board's physical isolation slot or, when no slot geometry is available, by the perpendicular bisector of HV and LV zone centroids.
- **SC2. Critical loop components are spectrally closer than uniform-weight baseline.** For nets belonging to a `LoopAreaConstraint`, the mean pairwise spectral distance between loop components is ≤70% of the mean distance under uniform weights, on the same netlist.
- **SC3. Weights are reproducible from constraint data alone.** Given the same netlist and constraint set, the computed weights are deterministic. No random seed, no hyperparameter tuning per design is required beyond the single calibration constant `C_iso`.
- **SC4. No regression in optimizer convergence.** A placement seeded with constraint-weighted spectral initialization converges to a final loss no worse than uniform-weight initialization, within the same iteration budget, on the existing regression corpus.
- **SC5. Negative-weight stabilization produces a PSD Laplacian.** The stabilized Laplacian is positive semi-definite (verified by checking that all eigenvalues are ≥ -1e-6), and the spectral embedding is numerically stable across repeated runs.

---

## Scope Boundaries

| In Scope | Out of Scope |
|----------|-------------|
| Modify `SpectralPlacer.compute_placement()` to accept constraint-derived edge weights instead of uniform `1/(k-1)` | Changing the eigendecomposition algorithm (still uses `scipy.sparse.linalg.eigsh`) |
| Compute per-net weights from `TopologicalGraph` + `NetClassRules` + `Net.weight` fields | Modifying PCL constraint definitions or adding new fields (unless needed for missing physical data like `loop_current_rms`) |
| Implement negative-weight Laplacian stabilization via PSD shift | Multi-objective Laplacian variants (e.g., normalized cut, random walk Laplacian) |
| Define the weight derivation rules enumerated in this document | Adding new constraint types to PCL |
| Validate on existing regression corpus with comparison to uniform-weight baseline | Running on designs outside the temper-placer corpus |
| Explode hyperedge (k-pin net) into clique with per-edge weight accounting for constraint-derived modifiers | Group-level constraints (e.g., Ungar's block model) — this is pairwise only |

---

## Rejected Alternatives

**Early curriculum loss activation:** Activating `GroupClusterLoss` and `ClearanceLoss` at epoch 0 with gradually ramping weights was evaluated. While this improves group cohesion and clearance satisfaction relative to the current epoch-3000 activation, the optimizer still requires hundreds of epochs to converge group member distances from spectral-init positions. Pre-weighted Laplacian embedding provides a convex initialization neighborhood that early loss activation alone cannot — gradient descent from scattered positions against quadratic penalties converges slowly regardless of weight magnitude. The constraint-weighted approach is complementary: it provides the initial positions; early loss activation provides the tighter convergence guarantee.

---

## Risks

### Risk 1: Negative Weights → Indefinite Laplacian → Non-PSD Stabilization

**Severity**: HIGH. A Laplacian with negative off-diagonal entries (from repulsion constraints) is not guaranteed to be positive semi-definite. `scipy.sparse.linalg.eigsh` requires symmetric PSD input for `which='SA'` (smallest algebraic eigenvalues). If the Laplacian has negative eigenvalues, `eigsh` may fail to converge or return spurious eigenvectors.

**Proposed stabilization**: Before eigendecomposition, apply a PSD shift:

```
L_stable = L + λ_min_shift * I
```

where `λ_min_shift = max(0, -λ_min(D^{-1/2} L D^{-1/2}))` is the magnitude of the most negative eigenvalue of the normalized Laplacian. This shift adds a uniform "ambient attraction" to all components (pulling them toward the origin), which dilutes the repulsion signal.

**Risk of over-damping**: If the shift is large (because many negative edges exist), the repulsion is weakened — the spectral embedding regresses toward the uniform-weight result. The shift magnitude must be monitored and reported. A design with many separation constraints may see negligible improvement over baseline.

If the required PSD shift exceeds 50% of the maximum positive eigenvalue of the normalized Laplacian, the approach falls back to the constraint-weighted adjacency WITHOUT repulsion (negative-weight) edges, and logs a warning that HV/LV separation was deferred to the optimizer. This cap prevents the worst-case scenario where the shift dominates the embedding and pulls all components toward the origin.

**Alternative**: Generalize the concept. A negative edge weight in a graph Laplacian means the eigenvalue problem is no longer a standard Laplacian problem. Consider framing this as a _generalized eigenvalue problem_ `Lx = λ M x` where M is a diagonal mass matrix that absorbs the negative contributions, or use a _signed Laplacian_ formulation from spectral clustering literature (Kunegis et al., 2010). Signed Laplacians naturally handle both attraction and repulsion without PSD shift, but require different eigendecomposition approaches.

Rather than computing λ_min via a full eigendecomposition (which fails on indefinite input), use Gershgorin's circle theorem for a cheap lower bound: for each row i of the normalized Laplacian, compute `center_i = L[i,i]` and `radius_i = sum(|L[i,j]| for j ≠ i)`. The minimum eigenvalue is bounded below by `min_i(center_i - radius_i)`. If this bound is negative, PSD-shift by its magnitude. Gershgorin is O(n²) in NumPy and requires no eigendecomposition — it runs before JAX loads.

**Performance note:** The Gershgorin λ_min bound (see above) avoids a full eigendecomposition for stabilization. Combined with the existing 3-vector eigendecomposition for embedding, total eigendecomposition cost is unchanged from the current spectral init. The Gershgorin bound is O(n²) in NumPy (~0.1ms for 200 components) and runs before the JAX eigendecomposition.

### Risk 2: Unary Constraints Don't Map to Pairwise Edges

**Severity**: MEDIUM. Several PCL constraint types have no natural pairwise edge representation:

- `OnSideConstraint`: "Component near board edge" — this is a unary constraint (apply to one component vs. a fixed geometry). It has no pairwise counterpart.
- `AnchoredConstraint`: "Component at specific position" — also unary.
- `AlignedConstraint`: Multi-way constraint (n components on same axis) that can be decomposed into `n·(n-1)/2` pairwise edges, but with a different semantics (alignment, not distance).
- `EnclosingConstraint`: "Components must be inside zone" — this is a set membership constraint relative to a geometric region.

**Mitigation**: 
- For `AlignedConstraint`, decompose into pairwise edges with alignment-axis-specific weights (e.g., high weight on X-axis similarity, zero on Y-axis). This is the only multi-way constraint that decomposes naturally.
- For `OnSideConstraint` and `AnchoredConstraint`, treat them as _seeds_: fix those components' positions to their constrained coordinates and remove them from the spectral embedding (they become boundary conditions). Alternatively, add a "phantom anchor node" at the constrained position with a strong attractive edge.
- For `EnclosingConstraint`, do not attempt to encode it in the Laplacian. Zone membership is better handled by the topological placement phase (`topological/initial_placement.py`), which already does zone-based layout.

### Risk 3: Physical Unit Mapping Is Incomplete for Induction Cooker Domain

**Severity**: MEDIUM. The formulas proposed in this document require physical quantities (current, frequency, voltage difference) that exist in `NetClassRules` and `LoopAreaConstraint` but may not always be populated. The `Net.weight` field exists but is always 1.0 in practice. The `Net.voltage_class` field exists but is a string ("LV"/"HV"), not a numeric voltage. The `NetClassRules.voltage_v` field exists (240V for ACMains, 400V for HighVoltage) but is not guaranteed for all classes.

If a design file is missing voltage ratings or current data, the weight formulas degrade to:
- Proximity: weight based on distance only (force budget is uniform per tier)
- Loop area: weight based on area only (current and frequency default to 1.0)
- Repulsion: weight based on clearance only (voltage difference defaults to clearance-proportional)

This degradation is acceptable as a fallback but must be logged explicitly so the designer knows the spectral init is running with incomplete physics.

---

## Unknowns

### U1: What Is the Right Value for C_iso?

The single free parameter `C_iso` (isolation repulsion strength) controls how strongly the spectral embedding pushes voltage domains apart. Too small → no noticeable separation. Too large → over-damping from PSD shift, or components pushed to board corners.

**Candidate calibration method**: Run a parameter sweep on 3 representative designs from the regression corpus. Measure the HV-LV convex hull separation distance (larger is better) and the PSD shift magnitude (smaller is better). Find the Pareto-optimal `C_iso` that maximizes separation while keeping shift below a threshold (e.g., <10% of the spectral radius).

**Candidate analytical derivation**: Set `C_iso` such that the repulsive force between two 1-unit test masses at distance `d = min_clearance` balances the attractive force from a unit-weight spring at the same distance. This gives `C_iso = k_tier * min_clearance³ / 2`, where `k_tier` is the force budget for HARD tier constraints. For `min_clearance = 6.0mm` and `k_HARD = 100` (arbitrary units in Laplacian space), `C_iso = 100 * 216 / 2 = 10,800`. Whether this yields useful embeddings is unknown.

Calibration procedure: vary k_HARD, k_STRONG, k_SOFT over [1, 10, 100, 1000] in a grid search while holding other constants at defaults. Select the combination that minimizes the epoch-count reduction metric (SC2) on the regression corpus without exceeding the PSD shift cap (see Risk 1) on any design. This is a one-time calibration, not a per-design tuning step.

The force budget constants (k_HARD, k_STRONG, k_SOFT) are the single largest source of free parameters. They govern ALL proximity and attraction weights. The calibration procedure (see U1) varies them in a 3D grid search over [1, 10, 100, 1000]³ (64 combinations, each validated on the regression corpus in under 1 minute). C_iso is calibrated separately since it governs repulsion strength, an independent dimension.

### U2: Does Weighting Actually Improve Spectral Initialization Quality?

The core assumption is that constraint-weighted Laplacian → better spectral embedding → faster optimizer convergence → better final placement. This is a three-link chain where every link could break:
- The spectral embedding may not respect weights proportionally (eigendecomposition is a global optimization that can "smear" local weight differences)
- A better spectral embedding may not translate to faster gradient descent (the optimizer may converge regardless of initialization quality, or may get stuck in a different local minimum)
- Faster convergence may not translate to better final quality (different initialization may lead to a different loss landscape basin)

**Validation plan**: Run an ablation with 3 variants on the regression corpus:
1. Uniform weights (baseline)
2. Constraint-weighted Laplacian with PSD stabilization
3. Constraint-weighted Laplacian _without_ negative weights (separation encoded only by de-weighting, not repulsion)

Compare: spectral embedding quality (HV-LV separation distance, loop component proximity), optimizer iterations to convergence, final wirelength and constraint violation counts.

**Go/no-go threshold:** The constraint-weighted approach SHALL produce at least 30% reduction in optimizer epochs to design-rule-zero (DRC zero) on at least 2/3 regression corpus boards compared to the uniform-weight baseline. If this threshold is not met, the approach is not merged and the uniform-weight spectral init remains the default. This gates the implementation effort on demonstrated, quantified benefit.

### U3: Is the Clique Model Adequate for Weighted Hypergraphs?

The current code transforms each k-pin net into k·(k-1)/2 pairwise edges with weight `1/(k-1)`. When we modify weights per net, the same clique expansion applies — but with a modified total weight. A net with boosted weight `w_boost` produces pairwise edges of weight `w_boost / (k-1)`.

Is there an alternative hypergraph Laplacian (e.g., Zhou et al., 2006) that would give better results? The clique model over-represents large nets: a 10-pin power net contributes 45 edges while a 2-pin gate-drive net contributes 1 edge. Even with constraint boosting, the power net's sheer connectivity may dominate.

**Potential fix**: Use the star-expansion model (add a virtual "net node" for each net, connect all pins to it, then eliminate the net node via Schur complement) rather than the clique model. This avoids the O(k²) edge explosion and may produce a sparser, more interpretable Laplacian.

Constraint-directed edge weights are stored separately from per-net weights to avoid distributing boosts across unintended component pairs. A `constraint_weight: dict[tuple[int,int], float]` stores per-edge overrides keyed by component index pairs. The total edge weight for pair (i,j) is: `w_total = w_base_net * (1/(k-1)) + constraint_weight.get((i,j), 0)`. This localizes constraint influence without changing the clique model.

### U4: Should Edge Weights Be Applied to Adjacency or Directly to the Laplacian?

The current code builds an adjacency matrix `A`, computes degrees `D`, then forms `L = D - A`. Negative edge weights produce negative entries in `A`, which affects both `A` and `D` (since `D[i,i] = Σ_j A[i,j]`). A negative edge reduces the degree of both endpoints — effectively making them "less connected" than their true connectivity.

Alternative: build a "signed Laplacian" directly: `L_pos = D_pos - A_pos` (attraction only), then add a "repulsion Laplacian" `L_neg` constructed from negative-weight edges separately. The total operator is `L = L_pos + L_neg`. This separates the PSD (attraction) and non-PSD (repulsion) contributions, making stabilization more targeted.

---

## Key Codebase Files

| File | Role | Required Change |
|------|------|-----------------|
| `placement/spectral.py:68-91` | Builds adjacency matrix with uniform clique weights | Receive per-net weights from caller instead of computing `1/(k-1)` |
| `core/netlist.py:104-123` | `Net` dataclass with `weight`, `net_class`, `voltage_class` | May need additional fields (`loop_current_rms`?) or no change (use existing `weight`) |
| `core/netlist.py:332-380` | `build_adjacency_matrix()` | Accept per-net weight dict as optional parameter; multiply by base weight |
| `core/design_rules.py:93-141` | `NetClassRules` with `safety_category`, `creepage_mm`, `voltage_v` | Used for safety-category-derived weights (read-only) |
| `pcl/constraints.py:252-406` | `AdjacentConstraint`, `SeparatedConstraint`, `LoopAreaConstraint` | Used for proximity/repulsion/loop weight derivation (read-only) |
| `topological/graph.py:54-327` | `TopologicalGraph` with adjacency/separation edges | Source of pairwise constraints mapped to net edges |
| `ml/learned_init.py` | GNN-based learned initializer | Unaffected (this is a separate initialization path) |

---

## Open Questions (Deferred to Planning)

- Should the weight derivation live in a new module (e.g., `placement/constraint_weights.py`) or be integrated into `SpectralPlacer`?
- Does the PSD shift need to be configurable per-design, or can one calibrated `C_iso` work everywhere?
- Should we store derived weights in the `Net.weight` field (mutating the netlist) or keep them in a separate lookup table passed to the spectral placer?
- For the clique vs. star-expansion question (U3), should we implement both and select based on net size threshold?
- **Resolved**: Constraint-derived weights SHALL be stored in a separate `dict[tuple[str,str], float]` keyed by component-index pairs as per the per-edge constraint_weight mechanism (see U3). They MUST NOT be written back to `Net.weight`, which remains the user-authored wirelength importance field consumed by downstream optimizers. This keeps the two weighting systems independent and prevents silent double-weighting of nets.
