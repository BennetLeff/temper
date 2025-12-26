# Correctness Framework for Production-Ready PCB Generation

**Version:** 1.0.0
**Last Updated:** 2025-12-25
**Status:** Foundational

---

## The Fundamental Question

> "What does it mean for a PCB to be correct, and how do we measure it?"

This document establishes a rigorous, hierarchical framework for defining and measuring PCB correctness. The goal is to transform a schematic (`.ato` files) into a **production-ready PCB** with provable correctness guarantees.

---

## The Hierarchy of Correctness

Correctness is not binary—it's a hierarchy. Each level is **necessary but not sufficient** for production readiness.

```
Level 5: FIELD PROVEN        ← The PCB works in real conditions for its lifetime
Level 4: MANUFACTURED        ← The PCB can be built by a fab house
Level 3: ELECTRICALLY VALID  ← The circuit will function as designed
Level 2: GEOMETRICALLY VALID ← Components fit without violating rules
Level 1: LOGICALLY VALID     ← Netlist is complete and correct
Level 0: SCHEMATIC CAPTURE   ← Design intent is captured
```

**Current temper-placer state:** Level 2 (partial)
**Target state:** Level 4 with Level 3 simulation validation

---

## Level 0: Schematic Capture

### Definition
The design intent is correctly captured in the source files.

### Validation Criteria

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| Component coverage | All BOM items in schematic | 100% | `ato verify` |
| Net completeness | All required connections exist | 0 floating pins | Netlist audit |
| Pin mapping | Footprint pins match symbol pins | 100% match | Library check |
| Constraint capture | Electrical rules in `.ato` | All critical nets | Manual review |

### Current State
- ✅ Schematic exists in `.ato` format
- ✅ Constraints defined for net classes
- ⚠️ No automated verification of schematic-to-constraint completeness

---

## Level 1: Logically Valid

### Definition
The netlist is complete, consistent, and implementable.

### Validation Criteria

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| Net connectivity | Every net has driver + load | 100% | Netlist analysis |
| Power integrity | Every power pin has source | 100% | Power net trace |
| Ground integrity | Every GND pin connected | 100% | Ground net trace |
| No floating pins | Unconnected pins intentional | 0 unintentional | Pin audit |
| ERC clean | Electrical rule check | 0 errors | ERC tool |

### Current State
- ⚠️ No automated netlist validation
- ⚠️ No ERC implementation
- 🔴 Gap: We assume the netlist is correct but don't verify

---

## Level 2: Geometrically Valid

### Definition
Components are placed such that they can be physically manufactured.

### Validation Criteria

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| **No overlaps** | Overlap area | 0 mm² | `compute_overlap_penalty()` |
| **Within boundary** | Boundary violations | 0 mm | `compute_boundary_penalty()` |
| **Zone compliance** | Components in assigned zones | 100% | Zone check |
| **HV-LV clearance** | Air gap distance | ≥10 mm | Clearance check |
| **Creepage distance** | Surface path | ≥6.5 mm (reinforced) | Path analysis |
| **Keepout respect** | Mounting hole clearance | 100% | Keepout check |
| **Component spacing** | Min courtyard gap | ≥0.2 mm (Class 2) | DRC |

### Current State
- ✅ Overlap, boundary, zone checks implemented
- ✅ HV-LV air clearance checked (10mm)
- ⚠️ Creepage not validated (depends on routing)
- ⚠️ No courtyard gap validation
- 🔴 Gap: Geometric validation is incomplete

---

## Level 3: Electrically Valid

### Definition
The circuit will function correctly when powered.

### 3.1 Signal Integrity

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| Wirelength ratio | HPWL / human baseline | ≤1.3 | HPWL calculation |
| Critical path timing | Propagation delay | Per spec | SPICE simulation |
| Impedance control | Trace Z₀ | ±10% of target | Stackup calculator |
| Crosstalk | Coupling coefficient | <5% | 3D field solver |

### 3.2 Power Integrity

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| **Gate loop inductance** | L_gate | ≤10 nH | Loop area × μ₀/h |
| **Bootstrap loop inductance** | L_boot | ≤20 nH | Loop area calculation |
| **Commutation loop inductance** | L_comm | ≤50 nH | Loop area calculation |
| DC bus ripple | ΔV at load | ≤20 V | SPICE simulation |
| Decoupling effectiveness | PDN impedance | ≤target at freq | Frequency sweep |
| Voltage drop | IR drop | ≤5% of rail | DC analysis |

### 3.3 EMC/EMI

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| **Loop area (gate)** | A_gate | ≤100 mm² | Polygon calculation |
| **Loop area (power)** | A_power | ≤400 mm² | Polygon calculation |
| Radiated emissions | dBμV/m at 3m | FCC Class A | Pre-compliance scan |
| Conducted emissions | dBμV | CISPR limits | LISN measurement |
| Common mode currents | I_cm | ≤1 mA | Current probe |

### 3.4 Safety

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| **Creepage (reinforced)** | Surface path | ≥6.5 mm | Trace analysis |
| **Clearance (reinforced)** | Air gap | ≥8.0 mm | 3D measurement |
| OCP response time | t_trip | ≤1 μs | Fault simulation |
| OVP response time | t_trip | ≤10 μs | Fault simulation |
| Thermal shutdown | T_trip | 85°C ± 5°C | Thermal test |

### Current State
- ⚠️ SPICE templates exist but not integrated with placement
- 🔴 Loop inductance calculated from placement, not validated
- 🔴 EMI not predicted or validated
- 🔴 Safety interlock timing not validated
- 🔴 Gap: **90% of Level 3 is missing**

---

## Level 4: Manufacturable

### Definition
A fabrication house can build the PCB with acceptable yield.

### 4.1 Design for Manufacturing (DFM)

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| Min trace width | w_min | ≥0.15 mm (6 mil) | DRC |
| Min trace space | s_min | ≥0.15 mm (6 mil) | DRC |
| Min drill size | d_min | ≥0.20 mm | Drill file check |
| Via aspect ratio | h/d | ≤10:1 | Stackup analysis |
| Annular ring | r_min | ≥0.10 mm | DRC |
| Solder mask clearance | c_sm | ≥0.05 mm | Gerber check |
| Copper balance | % per layer | 30-70% | Area calculation |

### 4.2 Design for Assembly (DFA)

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| Component orientation | Standard rotation | ✓ | Orientation check |
| Fiducial markers | Count | ≥3 board-level | Visual check |
| Thermal relief | Pad connections | All power pads | DRC |
| Via-in-pad | Filled/capped | Per design | Drill file check |
| Test point access | Coverage | ≥90% of nets | Probe analysis |
| Pick-and-place clearance | Component gap | ≥0.5 mm | Courtyard check |

### 4.3 Design for Test (DFT)

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| ICT access | Test points | All power rails | TP placement |
| Boundary scan | JTAG chain | Complete | Netlist check |
| Visual inspection | AOI access | 100% joints | 3D analysis |

### Current State
- 🔴 No DFM validation
- 🔴 No DFA validation
- 🔴 No DFT validation
- 🔴 Gap: **Level 4 is entirely missing**

---

## Level 5: Field Proven

### Definition
The PCB performs correctly under real-world conditions for its expected lifetime.

### Validation Criteria

| Criterion | Metric | Target | Validation Method |
|-----------|--------|--------|-------------------|
| Thermal cycling | Cycles to failure | >1000 (-10 to 80°C) | HALT test |
| Vibration | Fatigue life | >10⁶ cycles | Vibration test |
| Humidity | Moisture resistance | 85°C/85% RH | HAST test |
| ESD | Immunity | ±8kV contact | IEC 61000-4-2 |
| Surge | Immunity | 2kV line | IEC 61000-4-5 |
| Operational lifetime | MTBF | >50,000 hours | Field data |

### Current State
- 🔴 Not addressed (requires physical testing)

---

## The Measurement Gap

### What We Currently Measure

| Metric | Status | Confidence |
|--------|--------|------------|
| Overlap loss | ✅ Measured | High |
| Boundary violations | ✅ Measured | High |
| HV-LV clearance | ✅ Measured | High |
| Zone compliance | ✅ Measured | High |
| Wirelength (HPWL) | ✅ Measured | Medium |
| Loop area (geometric) | ✅ Measured | Low |
| DRC errors (KiCad) | ⚠️ Post-hoc | Medium |
| Routing completion | ⚠️ Post-hoc | Low |

### What We Must Measure (Priority Order)

| Metric | Level | Priority | Effort |
|--------|-------|----------|--------|
| Loop inductance (validated) | 3 | P0 | Medium |
| Creepage distance | 2 | P0 | Medium |
| Thermal junction temp | 3 | P0 | High |
| Gate drive timing | 3 | P1 | Medium |
| DFM compliance | 4 | P1 | Low |
| EMI prediction | 3 | P2 | High |
| Safety interlock timing | 3 | P2 | Medium |

---

## Proposed Validation Pipeline

```
┌─────────────────┐
│ Schematic (.ato)│
└────────┬────────┘
         ▼
┌─────────────────┐
│ Netlist Extract │ ─── Level 1 Validation (ERC)
└────────┬────────┘
         ▼
┌─────────────────┐
│ Placement       │ ─── Level 2 Validation (Geometric)
│ Optimization    │
└────────┬────────┘
         ▼
┌─────────────────┐
│ Placement       │ ─── Level 3.1 Validation (Loop Analysis)
│ Validation      │     • Loop area → inductance estimate
└────────┬────────┘     • Thermal path analysis
         ▼              • Creepage path analysis
┌─────────────────┐
│ Routing         │ ─── Level 3.2 Validation (Post-Route)
│ (Freerouting)   │     • Actual loop inductance
└────────┬────────┘     • Signal integrity
         ▼
┌─────────────────┐
│ Route           │ ─── Level 3.3 Validation (Simulation)
│ Validation      │     • SPICE gate drive
└────────┬────────┘     • SPICE power integrity
         ▼              • Thermal simulation
┌─────────────────┐
│ DFM/DFA Check   │ ─── Level 4 Validation
│                 │     • Fab capability check
└────────┬────────┘     • Assembly check
         ▼
┌─────────────────┐
│ PRODUCTION      │
│ READY           │
└─────────────────┘
```

---

## Concrete Success Criteria by Level

### Minimum Viable Product (MVP)

To claim "production ready", we must validate:

**Level 2 (Complete):**
- [ ] Zero overlap
- [ ] Zero boundary violations
- [ ] All components in zones
- [ ] HV-LV clearance ≥10mm
- [ ] Creepage ≥6.5mm (estimated)
- [ ] KiCad DRC = 0 errors

**Level 3 (Core):**
- [ ] Gate loop area ≤100 mm² → L ≤10 nH (estimated)
- [ ] Bootstrap loop area ≤50 mm² → L ≤5 nH (estimated)
- [ ] Commutation loop area ≤400 mm² → L ≤50 nH (estimated)
- [ ] IGBT edge distance ≤5 mm (thermal)
- [ ] Routing completion ≥90%
- [ ] SPICE gate drive: overshoot ≤20%
- [ ] SPICE power integrity: ripple ≤20V

**Level 4 (Basic):**
- [ ] Min trace width ≥0.15 mm
- [ ] Min trace space ≥0.15 mm
- [ ] Via aspect ratio ≤10:1
- [ ] Fiducials present

### Stretch Goals

- [ ] Loop inductance validated by PEEC (±4% accuracy)
- [ ] Thermal simulation: T_junction ≤150°C
- [ ] EMI pre-scan: meets FCC Class A
- [ ] Full DFM/DFA checklist passed

---

## The Proxy Problem

### Why Proxies Fail

We optimize **proxies** (loss functions) because we can't measure **actuals** (physical outcomes) until fabrication. The danger:

| Proxy | Actual | Correlation | Risk |
|-------|--------|-------------|------|
| Overlap loss | Physical overlap | ~1.0 | Low |
| HPWL | Routing success | ~0.5 | Medium |
| Loop area loss | Loop inductance | ~0.7 | Medium |
| Thermal loss | Junction temp | ~0.3 | High |
| Congestion loss | Routing completion | ~0.4 | High |

### Closing the Loop

To improve proxy accuracy:

1. **Measure actuals on reference designs**
   - Build the human-designed Temper PCB
   - Measure actual loop inductance, junction temps, EMI
   - Correlate with placement metrics

2. **Calibrate proxy models**
   - Adjust inductance formula based on measurements
   - Tune thermal model against FEA or measurements
   - Validate EMI prediction against pre-compliance scan

3. **Regression testing**
   - Every new loss function must show correlation with actuals
   - No loss accepted without validation data

---

## Measurement Infrastructure Required

### Immediate Needs

1. **Loop Inductance Estimator**
   - Input: Component positions, assumed routing
   - Output: Estimated L for each critical loop
   - Validation: Compare to PEEC on routed design

2. **Creepage Analyzer**
   - Input: Component positions, net assignments
   - Output: Minimum creepage path for HV-LV pairs
   - Note: Conservative estimate before routing

3. **Thermal Estimator**
   - Input: Component positions, power dissipation
   - Output: Estimated junction temperatures
   - Model: Simplified thermal resistance network

4. **DFM Checker**
   - Input: KiCad PCB file
   - Output: DFM violations (trace/space, drill, etc.)
   - Integration: Call after routing

### Future Needs

5. **EMI Predictor**
   - Input: Loop areas, currents, frequencies
   - Output: Estimated radiated emissions
   - Reference: CISPR 22 limits

6. **PEEC Validator**
   - Input: Routed PCB
   - Output: Accurate loop inductance (±4%)
   - Tool: Q3D, FastHenry, or analytical

---

## Definition of "Done"

### For Temper PCB to be Production Ready:

```yaml
production_ready:
  level_2_geometric:
    overlap: 0 mm²
    boundary_violations: 0 mm
    zone_compliance: 100%
    hv_lv_clearance: ≥10 mm
    creepage_estimate: ≥6.5 mm
    drc_errors: 0
    drc_warnings: ≤10

  level_3_electrical:
    gate_loop_area: ≤100 mm²
    gate_loop_inductance: ≤10 nH  # estimated
    bootstrap_loop_area: ≤50 mm²
    commutation_loop_area: ≤400 mm²
    igbt_edge_distance: ≤5 mm
    routing_completion: ≥90%
    spice_gate_overshoot: ≤20%
    spice_power_ripple: ≤20 V

  level_4_manufacturing:
    min_trace_width: ≥0.15 mm
    min_trace_space: ≥0.15 mm
    via_aspect_ratio: ≤10:1
    fiducials: ≥3

  robustness:
    failure_rate_100_seeds: ≤5%
    metric_cv: ≤15%
```

### Acceptance Test

A placement is **accepted** if and only if:

1. All Level 2 criteria pass (hard gate)
2. All Level 3 core criteria pass (hard gate)
3. All Level 4 basic criteria pass (hard gate)
4. Robustness criteria met across 30+ seeds

---

## Next Steps

### Immediate (This Week)

1. **Implement creepage estimator**
   - Conservative estimate from component positions
   - Add to loss function with high weight

2. **Implement loop inductance validator**
   - Calculate L from loop area using μ₀ formula
   - Add validation check post-optimization

3. **Add DFM checks to pipeline**
   - Parse KiCad DRC for trace/space violations
   - Block release if DFM fails

### Near-term (This Month)

4. **Build thermal estimator**
   - Simplified Rth model from placement
   - Validate against FEA on reference design

5. **Integrate SPICE validation**
   - Run gate drive simulation post-routing
   - Fail if overshoot >20%

6. **Calibrate proxy models**
   - Build reference PCB
   - Measure actuals
   - Update models

### Long-term (This Quarter)

7. **PEEC integration**
   - Accurate loop inductance post-routing
   - Use to validate placement-stage estimates

8. **EMI prediction**
   - Loop area + current → emissions estimate
   - Pre-compliance target

9. **Continuous improvement**
   - Track proxy-to-actual correlations
   - Improve models based on field data

---

## Summary

**Current state:** We validate geometry but not electricity, not thermal, not manufacturing.

**Target state:** A placement is "production ready" when it passes validation at Levels 2, 3, and 4 with measured confidence.

**The gap:** ~90% of correctness validation is missing.

**The path:** Build measurement infrastructure, calibrate against real boards, close the feedback loop.

---

*This framework is the foundation for all future validation work. Every new feature, loss function, or optimization must demonstrate how it improves correctness at one or more levels.*
