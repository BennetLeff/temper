# Benders Placement Optimization: Requirements Checklist

## Purpose

Before implementing the Benders decomposition approach, we need to gather and validate all inputs. This document tracks what we have, what we need, and open questions.

---

## 1. Component Data

### 1.1 Component Inventory

**Status:** ✅ COMPLETE - Data extracted to `packages/temper-placer/data/benders_input.json`

| Data Needed | Source | Status | Notes |
|-------------|--------|--------|-------|
| Component reference list | KiCad PCB | ✅ DONE | 33 components |
| Component dimensions (w, h) | Footprint data | ✅ DONE | Bounding boxes extracted |
| Current positions (x, y) | KiCad PCB | ✅ DONE | Initial positions |
| Rotation | KiCad PCB | ⚠️ PARTIAL | Not yet handling rotation |

**Board Dimensions:** 100mm × 150mm

### 1.2 Component Classification

**Status:** ✅ COMPLETE

| Category | Count | Components |
|----------|-------|------------|
| **FIXED** | 9 | J_AC_IN, J_COIL, J_DEBUG, J_NTC, J_USB, MH1, MH2, MH3, MH4 |
| **HV** | 8 | C_BOOT, C_BUS1, C_BUS2, D1, D2, Q1, Q2, U_GATE |
| **FREE** | 16 | C_CT_FILT, C_MCU_1-4, C_VCC, MAX31865, R_BURDEN, R_GATE_H, R_GATE_L, U_BUCK, U_CT, U_LDO_3V3, U_LDO_5V, U_MCU, U_OPAMP_CT |

**HV Nets Identified:**
- ACMains (6mm): AC_L, AC_N, PE
- HighVoltage (3mm): DC_BUS+, DC_BUS-, SWITCH_NODE
- HighVoltageIsolated (6mm): +5V_ISO, VBOOT_H, VBOOT_L
- Implicit HV (need assignment): SW_NODE, VCC_BOOT

**Open Questions:**
1. ⬜ Are there thermal constraints? (Keep MOSFETs Q1, Q2 near board edge for heatsinking?)
2. ⬜ Are there EMC constraints? (USB away from switching nodes?)
3. ⬜ Any components that MUST stay together? (U_MCU + C_MCU_1-4 decoupling?)

### 1.3 Component Dimensions Summary

**Extracted to:** `packages/temper-placer/data/benders_input.json`

| Component | Width (mm) | Height (mm) | Position (x, y) | Class |
|-----------|------------|-------------|-----------------|-------|
| Q1, Q2 | 14.4 | 3.5 | (25.4, 15), (50.5, 15) | HV |
| D1, D2 | 17.7 | 2.5 | (37.6, 30), (37.6, 45) | HV |
| C_BUS1, C_BUS2 | 10.5 | 3.0 | (28.8, 60), (48.8, 60) | HV |
| U_GATE | 11.0 | 9.5 | (35.0, 30.0) | HV |
| U_MCU | 7.7 | 6.8 | (80.0, 99.7) | FREE |
| J_AC_IN | 3.5 | 23.5 | (10.0, 85.0) | FIXED |
| J_USB | 5.0 | 1.0 | (95.0, 130.0) | FIXED |

---

## 2. Clearance Rules

### 2.1 Net Class Clearances

| Net Class | Clearance (mm) | Trace Width (mm) | Notes |
|-----------|----------------|------------------|-------|
| Default | 0.25 | 0.2 | General signals |
| Power | 0.5 | 1.0 | LV power rails |
| HighVoltage | 3.0 | 3.0 | DC bus |
| ACMains | 6.0 | 2.5 | IEC 62368-1 |
| HighVoltageIsolated | 6.0 | 2.0 | Isolation barrier |
| Differential | 0.3 | 0.35 | USB D+/D- |
| Ground | 0.3 | 0.5 | GND net |
| GateDrive | 0.5 | 0.5 | Gate signals |
| FinePitch | 0.1 | 0.127 | Fine-pitch ICs |

**Status:** ⬜ Verify these match temper.kicad_pro

### 2.2 Component-to-Component Clearances

**Question:** What clearances apply between component BODIES (not just traces)?

| From | To | Clearance | Source |
|------|----|-----------|--------|
| HV component | LV component | 6.0mm | IEC 62368-1 |
| Any component | Any component | 0.2mm | Manufacturing |
| Through-hole | Through-hole | 0.5mm | Drill tolerance |

**Open Questions:**
1. Do we use trace clearance or component clearance for ILP?
2. Should HV inflation apply to component bodies or just copper?

---

## 3. Board Constraints

### 3.1 Board Dimensions

**Status:** ✅ COMPLETE

| Parameter | Value | Source | Status |
|-----------|-------|--------|--------|
| Width | 100.0 mm | KiCad | ✅ Extracted |
| Height | 150.0 mm | KiCad | ✅ Extracted |
| Origin | (0.0, 0.0) | KiCad | ✅ Extracted |

### 3.2 Keep-Out Zones

**Question:** Are there any keep-out areas beyond component bodies?

| Zone | Location | Reason |
|------|----------|--------|
| ??? | ??? | ??? |

**TODO:** Check for explicit keep-out zones in KiCad.

### 3.3 Layer Stack

| Layer | Name | Type | Available for Routing |
|-------|------|------|----------------------|
| 0 | F.Cu | Signal | Yes |
| 1 | In1.Cu | Signal/Plane | ? |
| 2 | In2.Cu | Signal/Plane | ? |
| 3 | B.Cu | Signal | Yes |

**Open Questions:**
1. Are inner layers available for signal routing?
2. Are inner layers reserved for power planes?

---

## 4. Net Data

### 4.1 Net Inventory

**Question:** What nets need to be routed?

| Data Needed | Source | Status |
|-------------|--------|--------|
| Net names | KiCad | ⬜ TODO |
| Net class assignments | temper.kicad_pro | ✅ Available |
| Terminal positions (pads) | KiCad | ⬜ TODO |
| Terminal layers | KiCad | ⬜ TODO |

### 4.2 Critical Nets

From previous analysis:

| Net | Class | Priority | Notes |
|-----|-------|----------|-------|
| USB_D+ | Differential | High | Part of SCC conflict |
| USB_D- | Differential | High | Part of SCC conflict |
| AC_L | ACMains | Critical | HV safety |
| AC_N | ACMains | Critical | HV safety |
| +5V | Power | High | Part of SCC conflict |
| I_SENSE | FinePitch | Medium | Part of SCC conflict |
| GATE_L | GateDrive | Medium | Part of SCC conflict |
| PWM_L | FinePitch | Medium | Part of SCC conflict |

### 4.3 Net Terminal Positions

**TODO:** Extract for each net:
```python
{
    "USB_D+": [
        {"component": "J_USB", "pad": "A6", "x": 85.2, "y": 45.0, "layer": "F.Cu"},
        {"component": "U_MCU", "pad": "12", "x": 42.1, "y": 38.5, "layer": "F.Cu"},
    ],
    ...
}
```

---

## 5. Max-Flow Infrastructure

### 5.1 Existing Implementation

| Component | File | Status |
|-----------|------|--------|
| MaxFlowAnalyzer | analysis/max_flow.py | ✅ Implemented |
| 3D flow network | max_flow.py | ✅ Implemented |
| Min-cut extraction | max_flow.py | ⚠️ Partial |
| Bottleneck visualization | ??? | ⬜ Not implemented |

### 5.2 Required Extensions

| Feature | Purpose | Status |
|---------|---------|--------|
| Min-cut → component mapping | Identify which components block | ⬜ TODO |
| Min-cut → constraint generation | Create ILP cuts | ⬜ TODO |
| Incremental Max-Flow | Faster re-evaluation | ⬜ Optional |

---

## 6. ILP Solver Infrastructure

### 6.1 Solver Options

| Solver | License | Python API | Status |
|--------|---------|------------|--------|
| OR-Tools (SCIP) | Free | ortools | ⬜ Not installed |
| PuLP (CBC) | Free | pulp | ⬜ Not installed |
| Gurobi | Commercial | gurobipy | ⬜ Not available |

**Recommendation:** Start with OR-Tools (free, good performance).

### 6.2 Required Features

| Feature | OR-Tools | PuLP | Notes |
|---------|----------|------|-------|
| Continuous variables | ✅ | ✅ | Component positions |
| Binary variables | ✅ | ✅ | Disjunctive constraints |
| Big-M constraints | ✅ | ✅ | Non-overlap |
| Warm starting | ✅ | ⚠️ | Start from current placement |
| Incremental solving | ⚠️ | ⬜ | Add cuts without re-solving |

---

## 7. Validation Infrastructure

### 7.1 Existing

| Tool | Purpose | Status |
|------|---------|--------|
| Router V6 | Route the board | ✅ Available |
| KiCad DRC | Check design rules | ✅ Available |
| Max-Flow Analyzer | Check routability | ✅ Available |

### 7.2 Required

| Tool | Purpose | Status |
|------|---------|--------|
| Placement validator | Check ILP solution validity | ⬜ TODO |
| Overlap checker | Verify non-overlap constraints | ⬜ TODO |
| Clearance checker | Verify HV clearances | ⬜ TODO |

---

## 8. Open Questions Summary

### Critical (Block Implementation)

1. **Component dimensions:** How do we extract bounding boxes accounting for rotation?
2. **Fixed components:** Complete list of truly fixed components?
3. **HV component list:** Complete list of components requiring 6mm clearance?
4. **Inner layer usage:** Are In1.Cu and In2.Cu available for signal routing?

### Important (Affect Quality)

5. **Movement budget:** Is there a maximum acceptable movement per component?
6. **Grouping constraints:** Must certain components stay together (IC + caps)?
7. **Thermal constraints:** Any heat-dissipation placement requirements?
8. **EMC constraints:** Any signal integrity placement requirements?

### Nice to Have

9. **Visualization:** How do we visualize placement changes?
10. **Warm start effectiveness:** How much does warm starting help?

---

## 9. Data Collection Tasks

### Task 1: Extract Component Data

```bash
# Create script to extract from KiCad:
python scripts/extract_component_data.py pcb/temper.kicad_pcb > data/components.json
```

Output:
```json
{
  "components": [
    {
      "ref": "U1",
      "footprint": "QFN-56",
      "width_mm": 7.0,
      "height_mm": 7.0,
      "x_mm": 45.2,
      "y_mm": 32.1,
      "rotation_deg": 0,
      "layer": "F.Cu",
      "fixed": false,
      "hv": false
    }
  ],
  "board": {
    "width_mm": 100.0,
    "height_mm": 150.0,
    "origin_x": 0.0,
    "origin_y": 0.0
  }
}
```

### Task 2: Classify Components

Manual review to populate:
- `fixed_components.json` - List of fixed component refs
- `hv_components.json` - List of HV component refs
- `component_groups.json` - Components that should stay together

### Task 3: Extract Net Terminals

```bash
python scripts/extract_net_terminals.py pcb/temper.kicad_pcb > data/net_terminals.json
```

### Task 4: Verify Clearance Rules

Compare `temper.kicad_pro` against expected values in Section 2.1.

### Task 5: Test Max-Flow Min-Cut Extraction

Run Max-Flow on current placement, verify min-cut locations match known bottlenecks.

---

## 10. Implementation Order

| Phase | Task | Dependencies | Estimated Effort |
|-------|------|--------------|------------------|
| **P0** | Data collection (Tasks 1-5) | None | 1 day |
| **P1** | Answer critical questions | P0 | 0.5 day |
| **P2** | Install OR-Tools, basic ILP | P1 | 0.5 day |
| **P3** | Implement non-overlap constraints | P2 | 1 day |
| **P4** | Implement HV clearance constraints | P3 | 0.5 day |
| **P5** | Min-cut → component mapping | P0 | 1 day |
| **P6** | Cut constraint generation | P5 | 1 day |
| **P7** | Benders loop integration | P4, P6 | 1 day |
| **P8** | Validation & debugging | P7 | 1-2 days |

**Total estimated effort:** 7-8 days

---

## Sign-Off Checklist

Before starting implementation:

- [x] Component data extracted and validated (`data/benders_input.json`)
- [x] Fixed component list confirmed (9 components: connectors + mounting holes)
- [x] HV component list confirmed (8 components connected to HV nets)
- [ ] Inner layer policy decided (need to confirm In1.Cu/In2.Cu availability)
- [ ] OR-Tools installed and tested
- [ ] Max-Flow min-cut extraction working (partial - need component mapping)
- [ ] All critical questions answered (3 remaining: thermal, EMC, grouping)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-01-15 | Claude | Initial requirements draft |
| 0.2 | 2026-01-15 | Claude | Added extracted component data, updated status |
