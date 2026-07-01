---
title: "feat: Constraint-Weighted Spectral Laplacian Initialization"
type: feat
status: draft
date: 2026-07-01
origin: docs/brainstorms/2026-07-01-constraint-weighted-laplacian-requirements.md
depends_on:
  - "#1: Constraint-Passthrough (PCL constraints usable at init time)"
---

# feat: Constraint-Weighted Spectral Laplacian Initialization

## Summary

Replace the uniform `1/(k-1)` edge weight in the spectral initializer's Laplacian construction with constraint-derived per-edge weights. Five weight-derivation strategies (proximity, group coherence, critical loop, HV/LV repulsion, clearance) map existing PCL constraint data into Laplacian edge weights, pulling critical loops tight and pushing voltage domains apart before gradient descent begins. The feature ships behind a config flag (`initialization.method: constraint_weighted_spectral`), composes with an existing constraint-passthrough dependency, and includes property-based tests, a regression ablation, and an A/B comparison framework.

---

## Problem Frame

The spectral initializer in `optimizer/initialization.py:SpectralInitializer.initialize()` and `placement/spectral.py:SpectralPlacer.compute_placement()` constructs a graph Laplacian where every net edge carries uniform weight. The `build_adjacency_matrix()` function in `core/netlist.py:332` adds `+1` for each net connecting two components — a pure connectivity count with no constraint semantics.

Meanwhile, the PCL constraint system (`pcl/constraints.py`) defines precise geometric requirements: `AdjacentConstraint.max_distance_mm`, `SeparatedConstraint.min_distance_mm`, `LoopAreaConstraint.max_area_mm2`, and `EnclosingConstraint.inner` sets. The net class system (`core/design_rules.py:TEMPER_NET_CLASSES`) defines `safety_category` (HV/LV/AC/iso) and physical creepage distances. The `TopologicalGraph` (`topological/graph.py`) already builds adjacency/separation edges from PCL constraints. None of this reaches the spectral init.

**Specific gaps:**
- The gate-drive commutation loop and a status LED pull-up carry identical spectral influence.
- HV/LV domain separation is deferred entirely to the optimizer's `ClearanceLoss` (activated at epoch 3000), forcing gradient descent to restructure positions the spectral init didn't hint at.
- Component groups defined in `PlacementConstraints.component_groups` have zero influence on spectral embedding.

**Hypothesis:** If Laplacian edge weights encode constraint physics, the spectral embedding will naturally pre-cluster critical loops, pre-separate voltage domains, and pre-group functional blocks — reducing optimizer burden and improving convergence quality.

---

## Scope Boundaries

### In Scope

| Item | Detail |
|------|--------|
| New module `placement/constraint_weights.py` | Constraint-to-weight mapper; five strategy implementations; `compute_constraint_weight_dict()` entry point |
| Modify `SpectralInitializer.initialize()` | Accept optional `constraint_weights` dict; pass to `build_adjacency_matrix()`; apply PSD stabilization before eigendecomposition |
| Modify `SpectralPlacer.compute_placement()` | Accept optional weighted adjacency; apply same stabilization path |
| Config flag `initialization.method: constraint_weighted_spectral` | Placed in `PlacementConstraints.placer` dict; triggers weighted path |
| `ConstraintMapper` class | Precompute `(c1, c2) -> list[Net]` mapping from PCL constraints to netlist nets (O(N_nets * avg_pins^2), one-time) |
| PSD stabilization via Gershgorin circle theorem | Compute λ_min bound from normalized Laplacian; shift L_stable = L + |λ_min|*I if λ_min < 0 |
| Five weight derivation strategies (incremental delivery) | Proximity, group coherence, critical loop, HV/LV repulsion, clearance |
| Per-edge `constraint_weight: dict[tuple[int,int], float]` storage | Separate from `Net.weight`; keyed by component index pairs |
| Physical calibration constants | `k_HARD`, `k_STRONG`, `k_SOFT`, `C_iso`, `alpha_coherence` — one-time grid-search against regression corpus |

### Deferred

| Item | Reason |
|------|--------|
| Star-expansion hypergraph model | Clique model retained; star model evaluated post-launch (U3) |
| Signed Laplacian formulation | PSD shift approach shipped first; signed Laplacian as follow-up optimization |
| `OnSideConstraint` / `AnchoredConstraint` encoding | Unary constraints; already seeded via fixed positions; Laplacian encoding not needed |
| `EnclosingConstraint` encoding | Zone membership handled by `topological/initial_placement.py`; not in Laplacian |
| Multi-objective Laplacian variants | Normalized cut, random walk Laplacian out of scope |

### Out of Scope

| Item | Reason |
|------|--------|
| Modifying PCL constraint definitions or adding new fields | Constraint definitions are read-only input; missing data (e.g., loop_current_rms) gracefully degrades |
| Changing the eigendecomposition algorithm | Still uses `scipy.sparse.linalg.eigsh` / `jnp.linalg.eigh` |
| Writing constraint-derived weights back to `Net.weight` | `Net.weight` remains user-authored wirelength importance; constraint weights are separate |
| New constraint types | Only existing `AdjacentConstraint`, `SeparatedConstraint`, `LoopAreaConstraint`, `EnclosingConstraint`, and `ComponentGroup` are consumed |
| Running on designs outside the temper-placer regression corpus | Validation only on corpus boards |

---

## Implementation Units

### U1: Constraint-Mapper Precompute (`placement/constraint_weights.py`)

**Description:** Build `ConstraintMapper` class that resolves PCL constraint component references to netlist nets. For each adjacency constraint pair `(c1, c2)`, iterate all nets, check whether both component refs appear in the net's pin list, and build a mapping. For each loop constraint, resolve `loop_name` to component references via `ComponentGroup` lookup with fallback to `CriticalLoop.nets` enumeration. Produce `dict[tuple[str,str], list[Net]]` consumed by all weight strategies.

**Edge cases:**
- Component ref not found in netlist → log warning, skip constraint
- Multiple nets between same component pair → all nets receive the weight contribution
- `LoopAreaConstraint` with no component references and no matching `ComponentGroup` → log warning, skip loop weight derivation
- Empty constraint configuration → return empty mapping; spectral init behaves identically to baseline

**Files:**
- `packages/temper-placer/src/temper_placer/placement/constraint_weights.py` (new)

### U2: Weight Derivation Strategies

**Description:** Implement five weight-derivation functions, each consuming `ConstraintMapper` output and `PlacementConstraints` / `NetClassRules` data, producing a `dict[tuple[int,int], float]` of per-edge weight contributions.

**U2.1: Proximity (Spring-Constant)**

`w_proximity(i, j) = k_tier / max_distance_mm`

Where `k_tier` is chosen from `{k_HARD, k_STRONG, k_SOFT}` based on constraint tier. For nets with no explicit adjacency constraint, effective `max_distance` defaults to board diagonal → negligible baseline weight. Factor 2 accounts for spring series (two springs per edge). Alpha-validated during validation gate against `1/sqrt(max_distance)` alternative.

**U2.2: Group Coherence**

`w_coherence(i, j) = w_base * (1 + alpha_coherence * group_fraction)`

Where `group_fraction` = fraction of component i's nets that stay within its containing `ComponentGroup`. Components in same `EnclosingConstraint.inner` list also receive boost. `alpha_coherence` default = 2.0 (configurable). Only active when both endpoints share at least one group.

**U2.3: Critical Loop**

`w_loop(i, j) = w_base * I_rms^2 * f_switching / max_area_mm2`

Where `I_rms` defaults to 1.0 if not provided in constraint data, `f_switching` computed from `CriticalLoop` metadata. Loop components resolved via `ConstraintMapper`. Tighter `max_area_mm2` → larger weight (correct direction: tighter constraint = stronger spectral pull). When loop nets cannot be resolved to component pairs, weight derivation is skipped with a log warning.

**U2.4: HV/LV Repulsion**

`w_repulsion(i, j) = -C_iso / clearance_mm^2 * (V_diff / V_ref)`

Where `clearance_mm` is the lattice-join maximum of creepage/clearance between the two nets' safety categories (from `NetClassRules`), `V_diff` is the absolute voltage difference, and `V_ref = 400V` (normalization). Required for strategy activation: at least one of the two nets must have `safety_category != None` in `NetClassRules`. When absent, skip and fall back to uniform weight for affected nets.

**U2.5: Clearance (Generalized Net-Class Pair)**

Generalizes U2.4 to arbitrary `NetClassRules` cross-product. Weight is subtracted from base (negative contribution) for cross-category pairs (e.g., HV-LV, HV-AC). Same-domain pairs (LV-LV, HV-HV) receive no modification. Table-driven from `TEMPER_NET_CLASSES` lattice join. Activation requires `NetClassRules` populated with `safety_category` fields; if absent, no clearance-based weights applied.

**Strategy activation triggers:**

| Strategy | Required Data | Graceful Degradation |
|----------|--------------|---------------------|
| Proximity | `AdjacentConstraint` entries in PCL config | Missing → uniform weight for unconstrained nets |
| Group Coherence | `ComponentGroup` entries or `EnclosingConstraint.inner` | Missing → weight = w_base |
| Critical Loop | `LoopAreaConstraint` with resolvable components | Missing → skip; log warning |
| HV/LV Repulsion | `NetClassRules` with `safety_category` field | Missing → skip; no negative weights |
| Clearance | `NetClassRules` fully populated across net classes | Missing → skip; degrade to basic repulsion if HV/LV data present |

**Files:**
- `packages/temper-placer/src/temper_placer/placement/constraint_weights.py` (new, all strategies)

### U3: PSD Stabilization via Gershgorin Circle Theorem

**Description:** After negative repulsion weights are incorporated into the Laplacian, the resulting matrix may not be positive semi-definite. Apply Gershgorin's circle theorem to compute a cheap lower bound on λ_min without requiring eigendecomposition.

**Algorithm:**
```
For each row i of normalized Laplacian L_norm:
  center_i = L_norm[i, i]
  radius_i = sum(|L_norm[i, j]| for j != i)
  lambda_min_bound = min_i(center_i - radius_i)

If lambda_min_bound < -1e-6:
  L_stable = L_norm + |lambda_min_bound| * I
else:
  L_stable = L_norm
```

**Over-damping cap:** If the required shift exceeds 50% of the maximum positive eigenvalue (spectral radius), fall back to constraint-weighted adjacency WITHOUT negative-weight edges, and log a warning that HV/LV separation was deferred to the optimizer. This prevents the "all components pulled to origin" failure mode.

**Mathematical induction:**
- Base case (uniform weights): All A[i,j] >= 0, L = D - A is positive semi-definite (standard graph Laplacian property). Shift = 0, PSD property holds trivially.
- Inductive step: Adding a single constraint type that produces non-negative edge weights preserves the non-negativity of A, so L remains PSD by the same argument. Adding a constraint type that produces negative entries in A requires the Gershgorin bound check. If the bound is negative, shifting by its magnitude restores PSD: `L_stable = L + |λ| * I` has eigenvalues λ_i + |λ| >= 0 for all i.

**Edge weight contributing to Laplacian induction:**
`w_ij = w_base_net * (1/(k-1)) + constraint_weight.get((i,j), 0)`

Where `w_base_net = 1.0` (uniform) and `constraint_weight` accumulates Σ strategy contributions. The base term is always non-negative. Negative contributions come only from repulsion/clearance strategies.

**Locations modified:**
- `optimizer/initialization.py:compute_spectral_coordinates()`: add `stab_shift` parameter; apply before `eigh`
- `placement/spectral.py:SpectralPlacer.compute_placement()`: add same stabilization before `eigsh`

### U4: Config Flag and Pipeline Integration

**Description:** Add `initialization.method` field to the YAML config schema under `placer:` block, consumed by `PlacementConstraints.placer` dict. Pipeline integration hooks into `SpectralInitializer.initialize()` and optionally `SpectralPlacer.compute_placement()`.

**Config schema:**
```yaml
placer:
  initialization:
    method: constraint_weighted_spectral  # or "uniform" (default)
    calibration:
      k_HARD: 100.0
      k_STRONG: 10.0
      k_SOFT: 1.0
      C_iso: 21600.0
      alpha_coherence: 2.0
    strategies:
      proximity: true
      group_coherence: true
      critical_loop: true
      hv_lv_repulsion: false   # Requires PSD stabilization; default off until validated
      clearance: false          # Requires PSD stabilization; default off until validated
    psd_shift_max_ratio: 0.5   # Cap on shift / spectral_radius
```

**Activation flow:**
1. `PlacementConstraints` parsing reads `placer.initialization.method`
2. If `method == "constraint_weighted_spectral"` and constraint data is present:
   a. `ConstraintMapper` precomputes constraint-to-net mapping
   b. `compute_constraint_weight_dict()` runs active strategies
   c. Result passed to `SpectralInitializer.initialize(constraint_weights=...)` or `SpectralPlacer.compute_placement(constraint_weights=...)`
3. If `method == "uniform"` or constraint data missing: current behavior preserved exactly

**Graceful degradation chain:**
- No constraints in config → `ConstraintMapper` returns empty mapping → all weights uniform → identical to baseline
- PCL constraints present but `NetClassRules` incomplete → strategies that require net-class data skip; others proceed
- All strategies individually degrade on missing data (see U2 activation triggers table)

**Files:**
- `packages/temper-placer/src/temper_placer/io/config_loader.py`: parse `placer.initialization` block
- `packages/temper-placer/src/temper_placer/optimizer/initialization.py`: accept and route `constraint_weights`

### U5: Calibration Grid Search

**Description:** One-time calibration of force-budget constants (`k_HARD`, `k_STRONG`, `k_SOFT`) and repulsion strength (`C_iso`) against the regression corpus. This is a parameter sweep, not per-design tuning.

**Procedure:**
1. Grid search `k_HARD`, `k_STRONG`, `k_SOFT` over `[1, 10, 100, 1000]^3` (64 combinations)
2. For each combination, run constraint-weighted spectral init on 3 representative corpus boards
3. Measure: epoch-count reduction to DRC-zero (SC2), HV-LV convex hull separation, PSD shift magnitude
4. Select Pareto-optimal combination that minimizes epochs while keeping PSD shift < 10% spectral radius
5. Calibrate `C_iso` separately: sweep over `[100, 1000, 10000, 50000, 100000]`, same metrics
6. `alpha_coherence` calibrated as a separate 1D sweep over `[0.5, 1.0, 2.0, 3.0, 5.0]`

**Output:** Default calibration constants committed as module-level constants in `constraint_weights.py`.

**Per-design override:** Calibration constants are configurable via `placer.initialization.calibration` YAML block.

**Files:**
- `packages/temper-placer/scripts/calibrate_laplacian_weights.py` (new, one-time use)
- `packages/temper-placer/src/temper_placer/placement/constraint_weights.py` (constants)

### U6: Testing & Validation Suite

**Description:** Comprehensive test suite covering property-based invariants, unit tests, regression corpus ablation, and A/B comparison.

**U6.1: Property-Based Tests (Hypothesis)**
- `tests/test_constraint_weights_properties.py` (new)
- Invariants:
  - **Symmetry:** `constraint_weight[(i,j)] == constraint_weight[(j,i)]` for all (i,j)
  - **Non-negativity:** For proximity/coherence/loop strategies, all weights >= 0
  - **Monotonicity:** Tighter proximity constraint (smaller `max_distance_mm`) → strictly larger weight for same component pair
  - **PSD preservation:** Laplacian constructed from constraint weights is PSD after Gershgorin shift (all eigenvalues >= -1e-6)
  - **Baseline equivalence:** Empty constraint config → constraint weights dict is empty → Laplacian identical to uniform baseline
  - **Idempotency:** Running constraint weight computation twice on same input produces identical output
  - **Determinism:** No random seed in weight computation path
- Generate random constraint configurations (component counts, adjacency pairs, tier assignments, net-class assignments)
- Verify each invariant with `@given(...)` decorators

**U6.2: Unit Tests per Strategy**
- `tests/test_constraint_weights_unit.py` (new)
- Test `proximity_weight()`: valid distance input, tier mapping, board-diagonal fallback, zero-distance guard
- Test `group_coherence_weight()`: intra-group vs inter-group differentiation, alpha scaling, empty group fallback
- Test `critical_loop_weight()`: area-inverse scaling, I²*f amplification, missing loop data skip, correct direction (tighter = larger weight)
- Test `hv_lv_repulsion_weight()`: voltage-difference scaling, clearance selection from NetClassRules lattice join, missing category skip
- Test `clearance_weight()`: same-domain no-op, cross-domain subtraction, table consistency with TEMPER_NET_CLASSES
- Test `apply_psd_shift()`: Gershgorin bound computation, shift magnitude, over-damping cap, fallback to attraction-only
- Test `compute_laplacian_from_weights()`: adjacency construction, degree computation, Laplacian = D - A identity

**U6.3: Regression Corpus Ablation**
- `tests/test_constraint_weights_ablation.py` (new)
- Three variants on 3 regression corpus boards:
  - **Baseline:** uniform-weight spectral init (current behavior)
  - **Variant A:** constraint-weighted with all 5 strategies active
  - **Variant B:** proximity-only (MVP tier)
- Metrics tracked: optimizer epochs to DRC-zero, final wirelength, group cohesion at epoch 0, HV-LV separation at epoch 0, PSD shift magnitude
- Go/no-go threshold: Variant A must produce >=30% reduction in epochs to DRC-zero on >=2/3 boards vs baseline
- Results recorded in `tests/data/ablation_results.json`

**U6.4: A/B Comparison Script**
- `packages/temper-placer/scripts/ab_test_laplacian.py` (new)
- Run baseline and constraint-weighted variants side-by-side
- Output CSV of per-design metrics for CI dashboard integration
- Automatically compute epoch-count reduction, wirelength delta, cohesion improvement
- Generate comparison report to stdout

**Files:**
- `packages/temper-placer/tests/test_constraint_weights_properties.py` (new)
- `packages/temper-placer/tests/test_constraint_weights_unit.py` (new)
- `packages/temper-placer/tests/test_constraint_weights_ablation.py` (new)
- `packages/temper-placer/scripts/ab_test_laplacian.py` (new)
- `packages/temper-placer/tests/data/ablation_results.json` (new, gitignored except baseline)

---

## Key Technical Decisions

### 1. New Module: `placement/constraint_weights.py` (Not Inline in SpectralPlacer)

**Rationale:** The weight derivation logic involves 5 independent strategies, each with physical formulas and fallback paths. Embedding this in `SpectralInitializer` or `SpectralPlacer` would bloat those classes. A separate module allows independent testing of each strategy and makes the weight derivation pipeline swappable.

**Trade-off**: An extra module adds import complexity. The import-linter boundary check (`core/` ⊥ `placement/`) may need an allowlist entry if `constraint_weights.py` imports from `core/`.

### 2. Per-Edge `constraint_weight` Dict (Not per-Net Weight Multipliers)

**Rationale:** Per-net multipliers distribute boost across all clique pairs of a k-pin net, which (a) weakens the boost for large nets (10-pin power net: 45 edges), and (b) applies constraint semantics to nets that aren't the constrained pair. Per-edge storage localizes constraint influence exactly where intended. The requirements doc also mandates separation from `Net.weight`.

### 3. Gershgorin Bound over Full Eigendecomposition for λ_min

**Rationale:** Computing λ_min via `eigsh` defeats the purpose — the indefinite matrix may cause eigsh to fail or converge slowly. Gershgorin is O(n^2) in NumPy (~0.1ms for 200 components), requires no eigendecomposition, and provides a safe lower bound. Combined with the existing 3-vector eigendecomposition, total cost is unchanged.

### 4. PSD Shift (Not Signed Laplacian) for Negative Weights

**Rationale:** Signed Laplacians (Kunegis et al., 2010) handle negative edges natively but require a different eigendecomposition approach and introduce additional free parameters. The PSD shift is simpler, well-understood, and ships faster. The over-damping cap prevents pathological cases. Signed Laplacian is deferred for evaluation post-launch.

### 5. Calibration Constants over Per-Design Tuning

**Rationale:** The requirement is reproducible, deterministic initialization from constraint data alone (SC3). Per-design hyperparameter tuning violates this. A one-time grid search against the regression corpus produces fixed, committed constants. Per-design overrides are configurable but not required — the defaults must work out-of-the-box.

### 6. Uniform-Weight Clique Model Retained for Hypergraph Representation

**Rationale:** The current clique model (`build_adjacency_matrix()`) transforms k-pin nets into k*(k-1)/2 pairwise edges. The star-expansion model (U3 in requirements) avoids O(k^2) edge explosion but requires Schur complement elimination that's complex for weighted Laplacians. The clique model is retained for initial delivery; star-expansion evaluated post-launch.

---

## Risks & Dependencies

### Dependencies

| Dependency | Status | Impact if Not Met |
|-----------|--------|-------------------|
| **D1: Constraint-Passthrough (#1)** | Not yet landed | Constraint-weighted Laplacian cannot access PCL constraints at init time. Blocking. |
| **D2: PCL parser emits `ConstraintCollection`** | Operational (`pcl/parser.py:ConstraintCollection`) | ConstraintMapper consumes this. No change needed. |
| **D3: `NetClassRules` has `safety_category` field** | Operational (`design_rules.py:141`) | HV/LV repulsion and clearance strategies depend on it. |
| **D4: Regression corpus has 3+ boards** | Operational (existing corpus) | Ablation validation requires corpus boards. |

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **R1: Negative weights produce indefinite Laplacian → eigsh failure** | HIGH | Gershgorin PSD shift (U3) with over-damping cap at 50% spectral radius. Fallback to attraction-only weights if cap exceeded. |
| **R2: `1/max_distance` produces wrong spectral scaling** | MEDIUM | Alpha-validate during proximity gate (U2.1): test `1/max_distance` vs `1/sqrt(max_distance)` on regression corpus. Select empirically. |
| **R3: Physical data missing for critical loops** | MEDIUM | `I_rms` and `f_switching` default to 1.0; log warning. Weight degrades to pure area-driven. |
| **R4: Weight derivation doesn't improve convergence (U2 hypothesis)** | MEDIUM | Go/no-go threshold (U6.3): >=30% epoch reduction on >=2/3 boards. If not met, feature not merged. |
| **R5: Clique model over-represents large nets** | LOW | Constraint weights are per-edge and additive to base weight, not multiplicative on net weight. Large nets get uniform base edges + targeted constraint boosts on specific pairs. |
| **R6: Calibration constants overfit to regression corpus** | LOW | Three distinct corpus boards + configurable overrides per design. Defaults work out-of-the-box; per-design tuning available. |

---

## Verification Strategy

### Build & Type Check

```bash
# Type checking
uv run mypy packages/temper-placer/src/temper_placer/placement/constraint_weights.py

# Import boundary check
uv run python scripts/import_linter_gate.py
```

### Unit Tests

```bash
# Per-strategy unit tests
uv run pytest packages/temper-placer/tests/test_constraint_weights_unit.py -v

# Property-based tests (Hypothesis)
uv run pytest packages/temper-placer/tests/test_constraint_weights_properties.py -v --hypothesis-show-statistics

# Eigenvalue correctness
uv run pytest packages/temper-placer/tests/test_constraint_weights_unit.py -v -k "psd_shift"
```

### Regression Ablation

```bash
# Full ablation (baseline vs variant A vs variant B)
uv run pytest packages/temper-placer/tests/test_constraint_weights_ablation.py -v --ablation-runs=3

# Quick smoke test (one board, one variant)
uv run pytest packages/temper-placer/tests/test_constraint_weights_ablation.py -v -k "smoke"
```

### A/B Comparison

```bash
# Side-by-side comparison
uv run python packages/temper-placer/scripts/ab_test_laplacian.py --design temper --variants baseline,weighted

# Output: per-design metrics CSV, epoch reduction %, wirelength delta
```

### CI Integration

- **Type check gate**: `mypy` on `constraint_weights.py` (same job as existing type check)
- **Strategy unit tests**: Fast (<5s), run on every PR
- **Property-based tests**: Run on PRs touching `placement/` or `constraint_weights.py` (Hypothesis takes ~30s)
- **Ablation suite**: Nightly only (runs full optimizer convergence, ~10 min per board per variant)
- **Import boundary gate**: Must pass; add allowlist entry if `constraint_weights.py` crosses `core/` ⊥ `placement/` boundary

### Manual Verification Checklist

- [ ] Config flag `initialization.method: constraint_weighted_spectral` activates weighted path
- [ ] Config flag `initialization.method: uniform` (or absent) uses baseline path identically
- [ ] Missing constraint data → uniform weights (no crash)
- [ ] Gershgorin shift computed and applied for designs with separation constraints
- [ ] Log warning emitted when shift exceeds over-damping cap
- [ ] Log warning emitted when loop_current_rms is missing from CriticalLoop
- [ ] Log warning emitted when safety_category is missing from NetClassRules
- [ ] Deterministic: same netlist + same constraints → identical weights
- [ ] Per-design calibration override works via YAML config
- [ ] Strategy toggles (`strategies.proximity: false`) correctly skip individual strategies
