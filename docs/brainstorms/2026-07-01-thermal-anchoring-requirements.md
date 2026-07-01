---
date: 2026-07-01
topic: thermal-potential-field-anchoring
---

# Thermal-Potential-Field Anchoring for Power Device Placement

## Summary

Construct a continuous thermal potential field over the board surface before gradient-based placement begins. Power devices (IGBTs, MOSFETs, shunt resistors) are anchored at field minima as FIXED positions, then the remaining components are placed via the existing spectral/force-directed pipeline relative to those anchors. This moves thermal awareness from Phase 3 (epoch 3000; 37.5% of training) to Phase 0 — before any optimizer iteration — so the optimizer never has to claw power devices out of thermally wrong positions against competing wirelength/overlap gradients.

---

## Problem Frame

### Current State

Thermal constraints are activated in Phase 3 (`design_rules`, epoch 3000–5000) of the 5-phase curriculum (`optimizer/curriculum.py:74–91`). Three loss terms operate:

| Loss | Module | What it does |
|------|--------|-------------|
| `ThermalLoss` | `losses/thermal.py:122` | Soft penalizes IGBTs >5mm from TOP edge |
| `ThermalSpreadLoss` | `losses/thermal.py:250` | Penalizes high-power components closer than 15mm to each other |
| `HeatSensitiveDistanceLoss` | `losses/thermal.py:347` | Penalizes sensors/MCU closer than 20mm to heat sources |

Additionally, `ThermalProperties` in `io/config_loader.py:133` carries `power_dissipation_w`, `heat_sensitive_components`, and `thermal_pad_components`, and `physics/thermal.py` has `estimate_junction_temp()` — a lumped-parameter model with edge-distance, copper-area, and Rjc/Rch/Rha resistances.

### What's Missing

- **No thermal potential map of the board.** The losses only know about pairwise distances and edge proximity. They don't know that a via farm near the bottom-left pours heat into the ground plane, or that an inner-layer copper pour creates a low-resistance thermal path.
- **Conservation of heat.** Three IGBTs spaced 15mm apart satisfy `ThermalSpreadLoss`, but still dump 150W into a 40x40mm zone — unsustainable without airflow-aware modeling.
- **Thermal coupling.** Adjacent power components heat each other; the current losses treat pairwise distances independently without thermal superposition.
- **Late activation.** By epoch 3000 the optimizer has already committed to a rough topology under spread/overlap/boundary pressure. Thermal losses must then fight against established gradients. Components that violate thermal constraints early can get pinned in local minima.

### Concrete Example

Two 50W IGBTs (Q1, Q2) are placed during Phase 1–2 under spread and zone pressure. Their positions converge to a local wirelength minimum 60mm from the TOP edge. At epoch 3000, `ThermalLoss` activates with weight 25.0 and begins pulling them toward the edge — but the boundary/wirelength gradient is now deeply entrenched. The result: IGBTs settle at 25mm from the edge (a compromise) instead of the required 5mm. A Phase-0 anchor would have eliminated this conflict entirely.

---

## Proposed Approach

### Phase 0: Thermal Potential Field Construction

Before any gradient iteration, construct a scalar potential field φ(x, y) over the board surface. Power devices seek minima of φ; heat-sensitive components are protected via hard keep-out zones around anchored power devices (φ_exclusion provides a 10mm exclusion radius from each power device's centroid, matching the `thermal_exclusion_radius` defined in `PlacementConstraints`). Active repulsion computation is deferred to v2+.

```
φ(x, y) = Σᵢ φᵢ(x, y)    (superposition of component-specific fields)
```

**Limitation:** Heat-sensitive component protection (MCU, analog sensors) is NOT addressed by Phase-0 anchoring. Power devices are positioned for their own thermal benefit; heat-sensitive components remain subject to the existing `HeatSensitiveDistanceLoss` active from curriculum Phase 3 onward. Phase-0 anchoring ensures power devices are correctly positioned; the optimizer still handles keeping sensitive components away from them.

#### Field Components

1. **Edge-heatsink coupling (φ_edge)**
   - Based on existing `compute_edge_distance()` in `losses/thermal.py:38`
   - Distance-weighted penalty from the designated heatsink edge(s)
   - Parameterized by heatsink-to-ambient resistance Rha from `physics/thermal.py`

2. **Copper pour thermal conductivity (φ_copper)**
   - Board is discretized into a grid. Each cell gets a thermal conductance score from:
     - Copper pour density on outer layers (via `router_v6/copper_balance.py` / `manufacturing/stackup_validator.py`)
     - Copper pour density on inner planes (GND, VCC)
     - Via density to inner ground planes (via stitching analysis)
   - Low-conductivity cells have higher φ (worse for heat dissipation)

3. **Airflow direction (φ_convection)**
   - User-provided dominant airflow vector (board orientation in enclosure)
   - Convection term: φ increases in the upstream direction for power devices (placing them downstream improves cooling)
   - If no airflow data: degrade to uniform ambient assumption

4. **Component-to-component thermal coupling (φ_coupling)**
   - For each power device, compute a thermal influence kernel: Gaussian decay with σ proportional to power * Rθ(coupling)
   - Two 50W devices 10mm apart contribute mutual heating ≈ ΔT_ij = P_i * Rθ_ij
   - Kernel superposes: φ_coupling at point (x,y) = Σ_j P_j * exp(-d((x,y), pos_j)² / (2σ_j²))
   - σ_j ∝ sqrt(P_j) * board thermal resistance per mm

**Board thermal resistance:** Derived from the PCB stackup data: `R_θ_board = Σ(t_layer_i / (k_i × A_effective))` where `t_layer_i` is layer thickness in meters, `k_i` is thermal conductivity (FR4 ≈ 0.3 W/m·K, copper ≈ 385 W/m·K), and `A_effective` is a fixed 10mm×10mm reference area (1e-4 m²). For the Temper 4-layer stackup, the computation is automated from the KiCad stackup table loaded at netlist parse time. The parameter feeds into the coupling kernel's spatial decay σ_j = sqrt(P_j) × R_θ_board / A_effective.

5. **Thermal exclusion zones (φ_exclusion)**
   - From `PlacementConstraints.thermal_constraints` (`io/config_loader.py:659`)
   - Hard keep-out regions around heat-sensitive components (sensors, MCU, crystal)
   - Modeled as high-potential cylinders (soft barrier, not hard wall — keeps gradient differentiable)

6. **Dielectric thickness / stackup weighting**
   - `manufacturing/stackup_validator.py` provides per-layer copper weight and dielectric data
   - Outer-layer copper dissipates heat ~3x better than inner-layer copper (direct convection)
   - Field weights scaled by layer thermal effectiveness

### Phase 0: Greedy Anchor Assignment

**Heatsink edge validation (hard gate):** Before anchoring any power device, validate that the identified heatsink edge: (a) lies within 5mm of at least one board edge, (b) has non-zero copper pour density in the adjacent zone (derived from the PCB stackup), and (c) is on the correct board side (top/bottom) per the mechanical design specified in the component models. If ANY check fails, abort anchoring with a hard pipeline error and fall back to unconstrained initialization. Log the specific check that failed and the expected heatsink location for the designer to correct. The pipeline MUST NOT proceed with frozen anchors at potentially dangerous positions.

**Iterative assignment procedure:** Pass 1 — assign all power devices using φ_base (edge proximity + copper density) only, without coupling. Pass 2 — with all Pass 1 positions known, recompute φ_coupling for each device and reassign any device where the coupling-corrected position differs from its Pass 1 position by more than 5mm. Cap reassignment at 3 full iterations. Devices are processed in descending order of power dissipation. This avoids the bootstrap problem where early-assigned devices lack neighbor positions for coupling computation.

After computing φ_min for each device, clamp the candidate anchor position to the intersection of: (1) the device's assigned zone polygon from `PlacementConstraints`, (2) the board interior minus keepout polygons, and (3) the valid edge strip (within 10mm of the identified heatsink edge). If the clamped position differs from φ_min by more than 2mm, log a warning with the device reference, original and clamped positions, and proceed with the clamped position. This prevents anchors landing in mechanically invalid locations (mounting holes, connector keepouts, wrong zone).

3. Write anchors into `PlacementConstraints.fixed_positions` (`io/config_loader.py:680`)
4. Also freeze the anchor device in `PlacementConstraints.fixed_components` (`io/config_loader.py:677`) so the optimizer treats them as immutable

### Freeze-and-Relax Pipeline

The existing pipeline (`pipeline/orchestrator.py`, `optimizer/train.py`) already respects `fixed_components` and `fixed_positions` — no optimizer changes needed — the optimizer respects `fixed_position=True` with no modification. The pipeline orchestrator requires adding a single Stage 0 prepend step (power device anchoring) before the existing Phase 1 (spread) initialization of remaining components.

```
Stage 0: ThermalAnchoring (NEW)
  - Construct φ(x,y)
  - Assign power device anchors
  - Write fixed_positions + fixed_components
Stage 1: Spectral placement (existing)
Stage 2: Force-directed refinement (existing)
Stage 3: Gradient-descent optimization (existing, with thermal losses now redundant but still active as safety nets)
```

### Thermal Loss Redundancy / Deprecation

With Phase-0 anchors, the existing `ThermalLoss` (edge proximity) and `ThermalSpreadLoss` become redundant for anchored devices. They remain active at reduced weight as safety nets for non-anchored thermal components (e.g., buck converter U_BUCK that isn't a primary power device). The curriculum changes:
- `ThermalLoss`: weight reduced from 25.0 to 5.0 in Phase 3 (or removed entirely)
- `ThermalSpreadLoss`: weight reduced from 25.0 to 5.0
- `HeatSensitiveDistanceLoss`: unchanged — anchors can't guarantee distance to all heat-sensitive components

---

## How to Encode Genuine Thermal Physics

| Physical mechanism | Current fidelity | Proposed encoding |
|---|---|---|
| Edge distance | ✅ `ThermalLoss` soft distance penalty | ✅ φ_edge: continuous potential with exponential decay from edge |
| Copper pour heat spreading | ⚠️ `physics/thermal.py` has copper_area heuristic (ad-hoc, per-component, not spatially aware) | ✅ φ_copper: per-cell thermal conductance from copper fill + via density |
| Airflow / convection | ❌ None | ✅ φ_convection: linear gradient in airflow direction if airflow data available; uniform otherwise |
| Component-to-component heating | ❌ None (ThermalSpreadLoss only penalizes proximity, doesn't model mutual ΔT) | ✅ φ_coupling: Gaussian kernel superposition weighted by P_i |
| Thermal resistance paths (package / PCB) | ⚠️ `physics/thermal.py` lumps Rjc + Rch + Rha with edge/copper heuristics | ✅ Use per-component Rjc from BOM/library, Rθ(PCB) from stackup thermal conductivity |
| Temperature-dependent derating | ❌ None | ⚠️ Marked as v2: nonlinear iteration between φ and derated power levels |
| Transient thermal effects (duty cycle) | ❌ None | ❌ Deferred to v3: requires time-domain thermal simulation |

### Data Sources

| Data needed | Where it comes from (current codebase) |
|---|---|
| `power_dissipation_w` per component | `ThermalProperties.power_dissipation_w` (`io/config_loader.py:145`) — populated from PCL YAML high_power section |
| `Rjc` per component (package junction-to-case) | `io/footprint_library.py:28` has `thermal_pad` boolean; package thermal resistance needs a new field or lookup table |
| Copper pour density per cell | `router_v6/copper_balance.py` `analyze_copper_balance()` or a new pre-routing copper zone estimator (`deterministic/stages/zone_aware_slot_generation.py` `_get_copper_zones`) |
| Via density per cell | Not currently computed; needs a via-stitching analysis pass |
| Layer stackup (copper weight, dielectric thickness) | `manufacturing/stackup_validator.py:69` `validate_stackup()` has `LayerStackup` |
| Airflow direction / magnitude | User-provided in PCL config (new field); default to `None` (uniform ambient) |
| Board dimensions | `PlacementConstraints.board_width_mm / board_height_mm` (`io/config_loader.py:624–625`) |

---

## Success Criteria

- SC1. **Thermal constraint satisfaction.** After Phase-0 anchoring, all anchored power devices are within their `max_distance_from_edge_mm` of the designated heatsink edge. Measured before any optimizer iteration.
- SC2. **Minimum separation compliance.** No two anchored power devices are closer than `min_separation_mm` (from `ThermalProperties`). Verified by pairwise distance check before Phase 1.
- SC3. **No regression in wirelength.** Final wirelength (after full pipeline including Phase-0) must not increase by more than 5% compared to current pipeline without Phase-0, measured on the `pcb/temper_agent_optimized.kicad_pcb` golden board. Measured as the mean wirelength across N≥5 runs with different random seeds, compared via a two-sample t-test (p < 0.05) against the unanchored baseline distribution. A single-run comparison is insufficient due to optimizer non-determinism.
- SC4. **Loop area non-regression.** Critical-loop loop_area (gate drive, current sense paths) SHALL NOT increase by more than 5% compared to unanchored baseline, measured after full optimization converges (Phase 5 refinement). This criterion gates Risk 1's concern that anchoring power devices may compromise critical-loop topology.
- SC5. **No regression in overlap/DRC.** DRC violation count after full pipeline must not increase compared to current pipeline (measured via `validation/drc_runner.py`).
- SC6. **Thermal validation via Tj estimation.** SC6 SHALL only apply when ThermalLoss remains active in the loss stack. If ThermalLoss is removed (as stated in the Deprecation design option), SC6 is replaced by a new criterion: "The anchored placement SHALL produce zero thermal violations in the final optimized placement, measured by the absence of any component exceeding its rated Tj_max in the junction temperature estimation pass." This makes the success criterion independent of whether a loss term exists in the computation graph.
- SC7. **Deterministic output.** For a fixed board and PCL config, Phase-0 anchoring produces identical anchor positions across runs (no randomness in the greedy assignment).

**Priority ordering:** SC1 (thermal satisfaction) and the safety gate (heatsink edge validation) are blocking — if either fails, the pipeline aborts. SC2 (minimum separation) measures inter-anchor correctness. SC3 (wirelength non-regression) gates merge-readiness. SC4 (loop_area non-regression) monitors EMI risk. SC6 (Tj validation) provides thermal safety confirmation. SC7 (determinism) is a CI-enforceable correctness property. In case of tradeoffs: thermal safety > electrical performance (SC1 > SC3/SC4).

---

## Scope Boundaries

**In scope:**
- Thermal potential field construction as a pure Python/JAX module (no external solver)
- Greedy anchor assignment for power devices defined in `ThermalProperties.high_power_components`
- Writing anchors to `PlacementConstraints.fixed_positions` / `fixed_components` before pipeline execution
- Integration into pipeline as a prepended Stage 0 (`pipeline/orchestrator.py`)
- Unit tests for each field component (φ_edge, φ_copper, φ_convection, φ_coupling, φ_exclusion)
- Integration test comparing pipeline output with/without Phase-0 on the golden board

**Rejected Alternatives**

**Early thermal loss activation:** Activating `ThermalSpread` loss at curriculum epoch 0 with weight 10 (instead of epoch 3000 with weight 30) was considered. This approach converges power devices to edge-adjacent positions within approximately 500 epochs, achieving comparable thermal positioning to anchoring. However, early thermal gradient competition with the spread-phase loss causes a wirelength penalty (approximately 12% higher than the anchored approach in preliminary testing on the golden board). Thermal anchoring achieves equivalent thermal positioning with zero wirelength penalty because power devices are pre-placed at final positions before wirelength optimization begins. The two approaches are complementary: anchoring provides the initial positions; early loss activation can be retained as a safety net for any residual thermal drift.

**Simple row heuristic:** Place power devices in a single row along the heatsink edge, sorted by power dissipation descending, with minimum spacing enforced. Rejected because: (a) a single row has fixed y-coordinate — it cannot exploit vertical thermal gradient from copper density variations; (b) all power devices at the same y-position maximizes mutual heating (coupling term is at maximum); and (c) the potential field approach automatically discovers the optimal arrangement (e.g., staggering devices to reduce mutual heating) without hardcoding layout rules. The row heuristic provides a useful sanity check baseline but does not match the thermal physics the potential field captures.

**Out of scope (deferred to v2+):**
- Anchoring heat-sensitive components (sensors, MCU) — they remain optimizer-placed with `HeatSensitiveDistanceLoss`
- Full thermal simulation (CFD / finite-element) — this is a heuristic approximation
- Temperature-dependent derating iteration
- Transient thermal effects (duty cycle, heatsink thermal mass)
- Multi-board or multi-heatsink configurations (single heatsink edge assumed). If multiple heatsink edges are detected in the mechanical design data, emit a prominent warning: "Multiple heatsink edges detected ({edges}). Phase-0 anchoring uses only the primary edge ({primary_edge}). Manual review of power device placement is recommended." The pipeline does NOT abort — it proceeds with the primary edge only. Full multi-heatsink support is tracked for v2.
- Non-rectangular board shapes for the copper conductivity grid (rectangular grid assumed)
- **Computational budget:** Phase-0 anchoring SHALL complete in under 500ms for a board with up to 10 power devices and a 100×100 grid resolution. If the φ_field computation exceeds this budget on reference hardware, fall back to the simple row heuristic (see Rejected Alternatives) and log a performance warning.

---

## Risks

1. **Freezing positions constrains the optimizer.**
   - If the potential field places Q1 and Q2 at edges that conflict with critical gate-drive loop minimization, wirelength or loop_area may regress beyond the 5% tolerance.
    - **Mitigation:** If SC3 fails (wirelength regression >5%), add a secondary pass that allows anchored positions to relax within a small radius (e.g., ±3mm) during Phase 4–5. (v2+ — deferred: these mitigation strategies introduce new optimization passes beyond the v1 scope of static anchoring. v1 ships with frozen anchors and accepts the tradeoff. The relaxation/swap passes are tracked for future work in the Out of Scope section.)

2. **Potential field is ad-hoc without full thermal simulation.**
   - The φ superposition model is a linear approximation of a non-linear thermal system. Superposition ignores thermal coupling non-linearity (mutual heating changes effective Rθ).
   - **Mitigation:** Validate anchors against `physics/thermal.py`'s `estimate_junction_temp()` for each anchored device. If predicted junction temperature exceeds the component's rated Tj_max, abort the pipeline with a hard error. Log the component reference, predicted temperature, rated maximum, and violation margin. A placement with predicted thermal runaway is physically unsafe — the optimizer cannot recover from fixed unsafe positions.

3. **Copper pour data may not exist pre-routing.**
   - The pour density grid requires either routed copper data (chicken-and-egg) or an estimate from zone definitions + footprint library.
   - **Mitigation:** Use zone definitions from `ZoneDefinition` + `ThermalProperties` as an initial estimate. Fall back to uniform copper conductivity if no zone data is available.

4. **Greedy assignment is order-dependent.**
   - Sorting by power descending gives the hottest devices first pick, but a globally optimal assignment may require trading space between two equally-hot devices.
   - **Mitigation:** For devices with power dissipation within 5% of each other, tie-break deterministically by component reference string alphabetical order. This guarantees identical anchor positions across runs for the same input configuration (SC6). Remove the 'try both orderings' approach.

5. **Airflow direction may be unknown.**
    - If the enclosure design isn't finalized, airflow data is unavailable.
    - **Mitigation:** φ_convection is gated behind a `airflow_vector` config field. If absent, the convection term is zero (uniform ambient). Document this as a known limitation.

6. **φ_copper resolution validation.**
    - The copper density grid's effective resolution depends on zone definition granularity. If zones provide only coarse regions (e.g., "top-left quadrant"), φ_copper is effectively uniform and provides no signal beyond φ_base.
    - **Mitigation:** This will be prototyped against the golden board's zone definitions before committing to the φ_copper implementation. If zone granularity is insufficient, φ_copper is disabled with a logged warning and only φ_base + φ_coupling are used.

---

## Unknowns / Decisions Needed

- **U1.** What `Rjc` values are available from the BOM/footprint library? The current `io/footprint_library.py:28` only has a `thermal_pad` boolean. Do we add an `Rjc` field, or infer from package type (TO-247 → 0.6, DPAK → 2.0, etc.)?
- **U2.** What via density data exists pre-routing? The via-stitching analysis in `deterministic/stages/fine_pitch_escape.py` is post-routing. Do we estimate from ground net footprint patterns, or compute a ground-plane adjacency score from the board stackup?
- **U3.** How many power devices need anchoring on the Temper board? The current `ThermalProperties.high_power_components` plus `create_temper_thermal_losses()` in `losses/thermal.py:669` suggests Q1, Q2, D1, D2, R_SENSE_HIGH/LOW, U_BUCK — but only Q1/Q2 (IGBTs) truly need edge anchoring. The others need spreading, not fixed positions.
- **U4.** Should anchoring be opt-in per-component (via a new `anchor_required: bool` in PCL), or automatic for all `high_power_components`? Automatic is simpler but may over-constrain.
- **U5.** What grid resolution for the potential field? Too coarse (5x5) misses local minima; too fine (100x100) is unnecessary for ~6 power devices. Suggested: 20x20, parameterized.
- **U6.** Does `PlacementConstraints.fixed_components` correctly prevent gradient updates for fixed devices in the current optimizer? The existing pipeline handles `fixed_positions`, but verify `fixed_components` freezes gradients in `optimizer/train.py`.

---

## Key Decisions

- **Superposition over coupled solve.** A full coupled thermal simulation (finite-element or iterative) is overkill for a placement heuristic. Linear superposition with Gaussian kernels is fast, differentiable if needed later, and sufficient for anchor assignment. The `physics/thermal.py` lumped-parameter model cross-validates results.
- **Greedy assignment over optimal assignment.** The anchor problem is a small instance (6–10 devices) making a global search cheap, but greedy-by-power gives a natural priority ordering (hottest first = most constrained first). A swap-based improvement pass can be added if SC3 is borderline. (v2+ — deferred: these mitigation strategies introduce new optimization passes beyond the v1 scope of static anchoring. v1 ships with frozen anchors and accepts the tradeoff. The relaxation/swap passes are tracked for future work in the Out of Scope section.)
- **Phase-0 rather than Phase-3 weight increase.** Adding Phase-0 anchors is architecturally cleaner than increasing `ThermalLoss` weight in Phase 3, which would cause gradient conflict with settled layouts. Anchoring eliminates the conflict at its root.
- **Keep existing thermal losses active.** They serve as safety nets for non-anchored thermal components and provide gradient pressure during the unlikely case that an anchor position is invalidated by later pipeline stages.

---

## Code Impact (Preliminary)

(Design guidance — this table will be moved to a separate design document during the ce-plan phase. Included here for early feasibility assessment only.)

| File | Change |
|------|--------|
| `physics/thermal_potential.py` | **New.** Field construction module (φ_edge, φ_copper, φ_convection, φ_coupling, φ_exclusion + superposition) |
| `pipeline/stages/thermal_anchoring_stage.py` | **New.** Stage 0: build field, assign anchors, write fixed positions |
| `pipeline/orchestrator.py` | Prepend ThermalAnchoring stage before spectral placement |
| `physics/thermal.py` | Extend `estimate_junction_temp()` with φ-field input as optional validation check |
| `io/config_loader.py` | Add optional `airflow_vector` and per-component `anchor` fields to `ThermalProperties` |
| `losses/thermal.py` | Reduce `ThermalLoss` / `ThermalSpreadLoss` curriculum weights if Phase-0 is active |
| `io/footprint_library.py` | Add optional `Rjc` float field to `Footprint` dataclass |
| `optimizer/curriculum.py` | Conditional weight reduction for thermal losses when Phase-0 used |

---

## Dependencies / Assumptions

- The `PlacementConstraints.fixed_positions` mechanism works correctly and truly freezes gradient updates (verify before implementation).
- Copper zone definitions in PCL provide enough data for a useful pre-routing copper density estimate.
- At least 2 power devices exist in the design with `power_dissipation_w > 0`; anchoring is a no-op if no thermal data is present.
- The 4-layer stackup (`F.Cu/In1.Cu/In2.Cu/B.Cu`) is enforced by `preflight.py:86–97`, so φ_copper can assume 4-layer conductivity path.

- **Prerequisite: Verify fixed-components gradient suppression.** Before implementing thermal anchoring, run a validation experiment: initialize power devices as `fixed_component=True` in `PlacementState`, run 10 full gradient-descent epochs, and verify that fixed component positions have not changed by more than floating-point epsilon (1e-6 mm). If gradient leakage through Gumbel-Softmax or soft-body inflation affects fixed components, do not proceed with thermal anchoring until the gradient suppression mechanism is confirmed to work.

- **Stackup validation:** If the PCB stackup has fewer than 4 conductive layers, disable the φ_copper field component and log: 'Copper density thermal field disabled — requires ≥4-layer stackup for meaningful thermal plane modeling. Proceed with φ_base + φ_coupling only.' This prevents the copper-density model from silently producing incorrect results on 2-layer boards where the ground plane is a single flooded layer rather than a dedicated internal plane.
