# Temper vs. PowerSynth: Systematic Review and Pipeline Decisions

**Last Updated:** 2025-12-25 (Deep Analysis)

---

## 1. Executive Summary

This document provides a comprehensive comparison between the `temper-placer` pipeline (JAX-based gradient descent + NSGA-II) and the methodologies in the "PowerSynth v1.9" paper (Hierarchical Corner Stitch + Constraint Graph).

### Key Conclusions

1. **Keep the temper-placer architecture** - The continuous optimization approach with soft constraints is more flexible and allows gradient-based refinement of complex objectives like loop area.

2. **Adopt PowerSynth's hierarchical philosophy** - Use strong component groups as "virtual macro-blocks" without switching to a constraint graph.

3. **Critical gap identified: Loop inductance vs. Loop area** - PowerSynth uses a validated PEEC model for actual inductance; temper-placer approximates with polygon area (reasonable proxy but ~20-30% error expected).

4. **Fixed components strategy validated** - Only mechanical interfaces (connectors, mounting holes) should be fixed. ALL electrical components (including IGBTs) should be optimizer-placed with strong constraints.

---

## 2. Detailed Comparison of Approaches

### 2.1 Layout Representation

| Aspect | PowerSynth | Temper-Placer | Analysis |
|--------|------------|---------------|----------|
| **Geometry** | Rectangles in Manhattan grid | Continuous (x,y) + 4-rotation Gumbel-Softmax | Temper is more flexible but harder to guarantee DRC |
| **Data Structure** | Hierarchical Corner Stitch | Flat array with component groups | PowerSynth's tree structure enables better sub-module reuse |
| **Constraint Handling** | Constraint Graph (guaranteed satisfaction) | Loss functions (soft satisfaction) | Trade-off: flexibility vs. guarantees |

**Recommendation:** Keep continuous representation. Add log-barrier penalties if overlaps persist after 5000 epochs.

### 2.2 DRC Compliance

| Metric | PowerSynth | Temper-Placer |
|--------|------------|---------------|
| **Success Rate** | 100% DRC-clean by construction | Variable (depends on loss weights) |
| **Approach** | Design rules encoded in constraint graph edges | OverlapLoss, BoundaryLoss, ClearanceLoss |

**Recommendation:** Accept soft constraints. Final DRC validation via KiCad DRC post-export. If overlap rate > 1% at epoch 8000, implement log-barrier loss.

### 2.3 Optimization Algorithms

| Algorithm | PowerSynth | Temper-Placer | Use Case |
|-----------|------------|---------------|----------|
| **NSGA-II** | ✓ (primary) | ✓ (implemented) | Pareto exploration of thermal vs. electrical |
| **Randomization** | ✓ (larger space, slower) | - | Not needed with gradient descent |
| **Gradient Descent** | ✗ | ✓ (Adam + curriculum) | Fine-grained continuous optimization |
| **Solution Count** | 20,000-30,000 | 8,000 epochs (~100-500 solutions) | Temper faster convergence |

**Recommendation:** Use gradient descent as primary, NSGA-II for final Pareto exploration when user wants trade-off curves.

### 2.4 Hierarchy Strategy

| Approach | PowerSynth | Temper-Placer | Trade-off |
|----------|------------|---------------|-----------|
| **Physical Hierarchy** | Optimize sub-modules (half-bridge) → compose | Global optimization | PowerSynth: 12x faster for 2.5D |
| **Constraint Propagation** | Bottom-up from leaves to root | Flat loss aggregation | PowerSynth: better scaling |

**Recommendation:** Implement "virtual hierarchy" via strong ComponentGroupLoss:
```yaml
groups:
  - name: "half_bridge_power_stage"
    components: ["Q1", "Q2", "D1", "D2", "C_BUS1", "C_BUS2"]
    max_spread_mm: 25.0  # Treat as rigid block
    internal_weights: 100.0  # CRITICAL
```

### 2.5 Performance Models

| Model | PowerSynth | Temper-Placer | Gap |
|-------|------------|---------------|-----|
| **Loop Inductance** | PEEC-based (validated, ~4% error) | Polygon area proxy | **~20-30% less accurate** |
| **Thermal** | FEM-based (Gmsh/Elmer, <10% error) | Edge distance + spreading proxy | Similar accuracy for placement |
| **Mutual Coupling** | Considered in PEEC | Not modeled | Gap for parallel traces |

**Recommendation:**
- For loop inductance: Use routing_factor=1.3 in LoopAreaLoss to approximate trace detours
- Consider PEEC integration for post-optimization validation

---

## 3. Constraints: Which to Use

### 3.1 Tier 1 - CRITICAL (Must Satisfy)

| Constraint | Weight | PowerSynth Equivalent | Implementation |
|------------|--------|----------------------|----------------|
| **Overlap** | 200+ | Guaranteed by construction | `OverlapLoss` with log-barrier fallback |
| **HV-LV Clearance** | 100 | Spacing constraint edges | `ClearanceLoss` (10mm reinforced) |
| **Zone Membership** | 50 | Floorplan bounds | `ZoneMembershipLoss` |
| **Gate Drive Loop** | 100 | Loop inductance objective | `LoopAreaLoss` (max 100mm²) |
| **Commutation Loop** | 150 | Loop inductance objective | `LoopAreaLoss` (max 500mm²) |

### 3.2 Tier 2 - IMPORTANT (Strong Preference)

| Constraint | Weight | Reason |
|------------|--------|--------|
| **Q1-Q2 Proximity** | 80 | Minimize commutation loop, shared heatsink |
| **Gate Driver to Q1** | 80 | Gate loop inductance |
| **Bus Cap to Switch** | 60 | Decoupling effectiveness |
| **Thermal Edge** | 30 | Q1, Q2 within 5mm of TOP edge |

### 3.3 Tier 3 - AESTHETIC (Nice to Have)

| Constraint | Weight | Reason |
|------------|--------|--------|
| **Alignment** | 10 | Clean rows/columns |
| **Symmetry** | 5 | Visual balance |
| **Grid Snap** | 2 | Manufacturing convenience |

---

## 4. Fixed vs. Dynamic Components

### 4.1 FIXED (Use `fixed_mask = True`)

| Component | Reason | Position Strategy |
|-----------|--------|-------------------|
| **MH1-MH4** | Mechanical constraint (enclosure) | Corners: (3.5, 3.5), (96.5, 3.5), etc. |
| **J_AC_IN** | Mains entry (safety, cable routing) | Left edge, power zone |
| **J_COIL** | High-current output (cable routing) | Top edge center |
| **J_USB** | User interface (accessibility) | Bottom edge |
| **J_DEBUG** | Development access | Bottom edge |
| **J_NTC** | External sensor (wire routing) | Near AC input |

**Total Fixed:** 9 components (mechanical interfaces only)

### 4.2 DYNAMIC (Optimizer Places with Constraints)

| Component | Constraint | Rationale |
|-----------|------------|-----------|
| **Q1, Q2** | TOP edge (≤5mm), min spacing 15mm | PowerSynth optimizes IGBT positions for thermal |
| **D1, D2** | Power zone, near IGBTs | Freewheeling path |
| **U_GATE** | ≤15mm from Q1, driver zone | Gate loop minimization |
| **C_BOOT** | ≤5mm from U_GATE.VCC2 | Bootstrap charging loop |
| **C_BUS1, C_BUS2** | ≤8mm from switches | Commutation loop |
| **U_MCU** | Control zone, ≥30mm from Q1/Q2 | Noise immunity |
| **MAX31865** | Driver zone, ≥40mm from Q1 | RTD accuracy |
| **All Passives** | Follow their IC leaders | Decoupling |

**Key Insight from PowerSynth:** They optimize IGBTs positions to balance thermal and electrical. Their best solution (Layout B) was NOT at the edge but ~15mm in for better inductance. We should NOT fix IGBT positions.

---

## 5. Optimization Workflow Decision

### 5.1 PowerSynth Approach (NOT Recommended for Temper)

```
1. Define floorplan (fixed size or variable)
2. Place hierarchically (half-bridge → full-bridge)
3. Generate 10,000-30,000 random solutions
4. Evaluate loop inductance + temperature
5. Select from Pareto front
```

**Why Not:** Slower, requires large solution population, doesn't leverage gradient information.

### 5.2 Temper Approach (RECOMMENDED)

```
PHASE 1 - SPREAD (epochs 0-1000)
├── High: spread_loss (explore), boundary
├── Medium: zone_membership
├── Low: overlap (allow initial tangling)
└── Temperature: 5.0 (exploration)

PHASE 2 - FEASIBILITY (epochs 1000-3000)
├── High: overlap (200), boundary (100), clearance (100)
├── Medium: zone_membership (50)
├── Low: wirelength
└── Temperature: 3.0 → 1.0

PHASE 3 - DESIGN RULES (epochs 3000-5000)
├── High: loop_area (100), thermal_edge (50)
├── Medium: decoupling (30), grouping (50)
├── Low: wirelength (20)
└── Temperature: 1.0

PHASE 4 - PERFORMANCE (epochs 5000-7000)
├── High: loop_area (150), power_path (80)
├── Medium: wirelength (40), congestion (20)
├── Low: alignment (10)
└── Temperature: 0.5

PHASE 5 - REFINEMENT (epochs 7000-8000)
├── All losses at final weights
├── GradNorm balancing ON
└── Temperature: 0.1 → 0.01 (exploitation)
```

### 5.3 Why NOT "Place Then Optimize"

PowerSynth generates thousands of solutions because each is a discrete layout. Temper's gradient descent continuously improves a single solution. The curriculum approach achieves the same phased refinement:

- **Phase 1-2** ≈ "Place" (establish structure)
- **Phase 3-5** ≈ "Optimize" (refine for objectives)

---

## 6. Specific Recommendations

### 6.1 Immediate Actions

1. **Verify Loop Pin Ordering** (CRITICAL)
   - Audit `create_temper_loop_constraints()` in `loop_area.py`
   - Current ordering: `U_GD.OUTA → Q1.G → Q1.E → U_GD.VSSA`
   - Verify against schematic current flow
   - Test with `validate_loop_ordering()` utility

2. **Enable Decoupling + Power Path Losses**
   ```bash
   # Already done in recent commit (9adabb6)
   temper-placer optimize --enable-decoupling --enable-power-path
   ```

3. **Tune Loop Area Weights**
   ```yaml
   critical_loops:
     - name: "gate_drive_high"
       max_area_mm2: 100.0
       weight: 10.0  # Was 2.0, increase for stronger enforcement
   ```

### 6.2 Configuration Updates

```yaml
# Recommended loss_weights for power electronics:
loss_weights:
  # Hard constraints (Tier 1)
  overlap: 200.0
  boundary: 100.0
  clearance: 100.0
  zone_membership: 50.0

  # Loop area (PowerSynth-inspired, Tier 1)
  loop_area: 100.0

  # Thermal (Tier 2)
  thermal: 30.0
  thermal_spread: 25.0

  # Electrical (Tier 2)
  decoupling: 30.0
  power_path: 40.0
  wirelength: 20.0

  # Hierarchy (Tier 2)
  grouping: 50.0

  # Aesthetics (Tier 3)
  alignment: 5.0
  grid: 2.0
```

### 6.3 Fixed Positions (Final)

```yaml
fixed_positions:
  # ONLY mechanical - let optimizer handle all electrical
  MH1: [3.5, 3.5]
  MH2: [96.5, 3.5]
  MH3: [3.5, 146.5]
  MH4: [96.5, 146.5]
  J_AC_IN: [10.0, 147.0]   # Top-left edge
  J_COIL: [50.0, 147.0]    # Top center
  J_NTC: [25.0, 147.0]     # Top left-of-center
  J_USB: [50.0, 3.0]       # Bottom center
  J_DEBUG: [75.0, 3.0]     # Bottom right
```

### 6.4 Component Groups (Virtual Hierarchy)

```yaml
groups:
  # CRITICAL: Power stage as rigid block
  - name: "power_stage"
    components: ["Q1", "Q2", "D1", "D2", "C_BUS1", "C_BUS2"]
    max_spread_mm: 30.0
    zone: "power_zone"
    internal_weight: 100.0  # Very tight coupling

  # Gate driver cluster
  - name: "gate_driver"
    components: ["U_GATE", "C_BOOT", "C_VCC", "R_GATE_H", "R_GATE_L"]
    max_spread_mm: 20.0
    zone: "driver_zone"
    proximity_to: "Q1"
    proximity_distance_mm: 15.0

  # MCU cluster
  - name: "mcu_system"
    components: ["U_MCU", "C_MCU_1", "C_MCU_2", "C_MCU_3", "C_MCU_4", "Y1"]
    max_spread_mm: 20.0
    zone: "control_zone"
    separation_from: ["Q1", "Q2"]
    separation_distance_mm: 35.0
```

---

## 7. Validation Checklist (Pre-Fabrication)

Based on PowerSynth's validation methodology:

| Check | Target | Method |
|-------|--------|--------|
| Commutation loop area | < 500 mm² | Loss breakdown inspection |
| Gate drive loop area | < 100 mm² | Loss breakdown inspection |
| Q1-Q2 distance | 10-25 mm (optimal trade-off) | Post-placement measurement |
| HV-LV clearance | ≥ 10 mm | KiCad DRC |
| Max junction temp | < 150°C (with heatsink) | Thermal simulation (ANSYS/Elmer) |
| Loop inductance | < 20 nH | PEEC or Q3D (post-route) |

---

## 8. Conclusion

The `temper-placer` architecture is fundamentally sound and offers advantages over PowerSynth for our use case:

1. **Gradient-based optimization** enables faster convergence than pure randomization
2. **Curriculum learning** provides the staged refinement that PowerSynth achieves through hierarchical placement
3. **Soft constraints** offer more flexibility than hard constraint graphs

**Key gaps to address:**
- Loop inductance accuracy (use routing_factor=1.3 as proxy)
- Formal validation against hardware (future work)

**No architectural changes required.** Focus on:
1. Tuning loss weights per recommendations above
2. Verifying loop pin ordering
3. Post-optimization validation with KiCad DRC + thermal simulation
