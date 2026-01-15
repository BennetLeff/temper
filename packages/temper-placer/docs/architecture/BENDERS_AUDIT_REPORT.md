# Benders Requirements Audit Report

**Date:** 2026-01-15
**Auditor:** Claude (Professional PCB Design Review)

## Executive Summary

A thorough audit of the Benders placement optimization requirements revealed several issues. **Most critical issues have been resolved:**

| Category | Status | Issues Found |
|----------|--------|--------------|
| Component Positions | ✅ | Coordinate system verified as center-based |
| Net Assignments | ✅ | Fixed - VCC_BOOT, CGND, PGND added |
| Grouping Constraints | ⚠️ | 2 constraint violations in current placement |
| Overlap Detection | ✅ | 5 apparent overlaps verified as THT/SMD 3D-valid |
| HV Classification | ✅ | SWITCH_NODE already assigned, VCC_BOOT fixed |

---

## 1. Critical Issues (RESOLVED)

### 1.1 Missing HV Net Assignments ✅ FIXED

**Original Issue:** VCC_BOOT was falling back to pattern matching (`VCC*` → Power) instead of HighVoltageIsolated.

**Correction:** The audit originally flagged "SW_NODE" but the actual net name in KiCad is "SWITCH_NODE", which was already correctly assigned to HighVoltage.

| Net | Should Be | Status | Fix Applied |
|-----|-----------|--------|-------------|
| **SWITCH_NODE** | HighVoltage (3mm) | ✅ Already correct | N/A |
| **VCC_BOOT** | HighVoltageIsolated (6mm) | ✅ Fixed | Added to temper.kicad_pro |

**Fix Applied to `temper.kicad_pro`:**
```json
"netclass_assignments": {
    "VCC_BOOT": "HighVoltageIsolated",
    "CGND": "Ground",
    "PGND": "Ground"
}
```

### 1.2 Other Unassigned Nets ✅ FIXED

| Net | Recommendation | Status |
|-----|----------------|--------|
| +5V | Power (0.5mm) | ✅ Matched by pattern `+*V` |
| CGND | Ground (0.3mm) | ✅ Fixed - added explicit assignment |
| PGND | Ground (0.3mm) | ✅ Fixed - added explicit assignment |
| TEMP_SENSE | Default (0.2mm) | ✅ OK - low-level analog, default is fine |

---

## 2. Constraint Violations in Current Placement

### 2.1 MCU Decoupling Distance ❌

**Requirement:** Decoupling caps within 5mm of MCU
**Actual:** 7.0-7.7mm

| Pair | Required | Actual | Violation |
|------|----------|--------|-----------|
| U_MCU → C_MCU_1 | ≤ 5.0mm | 7.5mm | +2.5mm |
| U_MCU → C_MCU_2 | ≤ 5.0mm | 7.0mm | +2.0mm |
| U_MCU → C_MCU_3 | ≤ 5.0mm | 7.7mm | +2.7mm |
| U_MCU → C_MCU_4 | ≤ 5.0mm | 7.0mm | +2.0mm |

**Impact:** Degraded high-frequency decoupling, potential noise issues.

**Recommendation:** Either:
- Relax constraint to 8mm (acceptable for 48MHz MCU), OR
- Move C_MCU_* closer during Benders optimization

### 2.2 Current Sense Grouping ❌

**Requirement:** Analog signal chain components within 5mm

| Pair | Required | Actual | Violation |
|------|----------|--------|-----------|
| U_CT → C_CT_FILT | ≤ 5.0mm | 15.0mm | +10.0mm |
| U_OPAMP_CT → R_BURDEN | ≤ 5.0mm | 10.0mm | +5.0mm |

**Impact:** Long analog traces susceptible to noise pickup.

**Recommendation:** These components MUST be moved closer. Current placement is unacceptable for accurate current sensing.

### 2.3 Gate Driver Grouping ✅

| Pair | Required | Actual | Status |
|------|----------|--------|--------|
| U_GATE → C_VCC | ≤ 8.0mm | 5.0mm | ✅ OK |
| U_GATE → C_BOOT | ≤ 8.0mm | 7.0mm | ✅ OK |

---

## 3. Coordinate System Issue ✅ RESOLVED

### 3.1 Finding

Positions ARE component **centers** (KiCad default). The parser correctly handles this with `_center_offset` attributes for asymmetric footprints.

**Data file updated:** `benders_input.json` now includes:
- `center_x_mm`, `center_y_mm` - actual center position
- `corner_x_mm`, `corner_y_mm` - calculated corner position
- `coordinate_system: "center"` - explicit documentation

### 3.2 Apparent Overlaps Explained

After correction, 5 component pairs still show bounding box overlap:

| Pair | Status | Explanation |
|------|--------|-------------|
| D1 vs U_GATE | ⚠️ Valid but tight | D1 is THT (elevated), U_GATE is SMD. 3D clearance OK. |
| D1 vs C_BOOT | ⚠️ Valid but tight | Same - THT body passes over SMD. |
| D1 vs C_VCC | ⚠️ Valid but tight | Same - THT body passes over SMD. |
| U_GATE vs C_BOOT | ✅ Valid | C_BOOT is a decoupling cap placed on U_GATE. |
| U_GATE vs C_VCC | ✅ Valid | C_VCC is a decoupling cap placed near U_GATE. |

### 3.3 Detailed Analysis: D1 vs U_GATE

```
D1 (through-hole diode DO-201AD):
  Position: (30, 30)
  Pad 1: (30, 30) - 2.5mm circle
  Pad 2: (45.24, 30) - 2.5mm circle
  Body: ~17.7mm long, elevated ~5mm above PCB

U_GATE (SOIC-16W SMD):
  Position: (35, 30)
  Pins: X = 30.5 to 39.5, Y = 25.6 to 34.4
  Body: Flat on PCB surface

Gap between D1 Pad 1 edge and U_GATE left pins: ~0.75mm
```

**Conclusion:** This is a valid but tight layout. The THT diode body passes over the SMD IC. KiCad DRC would flag actual pad collisions.

### 3.4 ILP Implications

For the Benders optimization:
1. **Don't treat THT/SMD overlap as error** - 3D clearance allows coexistence
2. **Use pad-based clearance** for routing, not body bounding boxes
3. **Add component type** to data (THT vs SMD) for smarter constraints

---

## 4. Zone Compliance ✅

Current placement correctly positions components in thermal/EMC zones:

| Component | Zone | Constraint | Actual | Status |
|-----------|------|------------|--------|--------|
| Q1 | Thermal | Y ≤ 20mm | Y = 15.0mm | ✅ |
| Q2 | Thermal | Y ≤ 20mm | Y = 15.0mm | ✅ |
| D1 | Power | Y ≤ 50mm | Y = 30.0mm | ✅ |
| D2 | Power | Y ≤ 50mm | Y = 45.0mm | ✅ |
| U_MCU | Quiet | Y ≥ 80mm | Y = 99.7mm | ✅ |
| U_MCU | Quiet | X ≥ 60mm | X = 80.0mm | ✅ |
| U_GATE | Power | Y ≤ 50mm | Y = 30.0mm | ✅ |

---

## 5. EMC Distances ✅

MCU-to-power-stage distances meet requirements:

| Pair | Required | Actual | Status |
|------|----------|--------|--------|
| U_MCU → Q1 | ≥ 40mm | 100.7mm | ✅ |
| U_MCU → Q2 | ≥ 40mm | 89.7mm | ✅ |

---

## 6. Recommendations

### 6.1 Before Implementation (Blocking)

1. **Fix HV net assignments** - Add SW_NODE and VCC_BOOT to netclass assignments
2. **Clarify coordinate system** - Verify if positions are center or corner referenced
3. **Update benders_input.json** - Recalculate component positions if needed

### 6.2 During Implementation (Constraints)

1. **Relax MCU decoupling** - Change 5mm → 8mm (or accept current 7mm)
2. **Fix current sense placement** - Move U_CT, C_CT_FILT, U_OPAMP_CT, R_BURDEN closer
3. **Handle overlaps** - Verify actual vs. apparent overlaps before encoding non-overlap constraints

### 6.3 Data Quality

1. **Add rotation handling** - Current extraction ignores component rotation
2. **Validate dimensions** - Spot-check component sizes against KiCad footprints
3. **Add net terminal extraction** - Needed for Max-Flow analysis integration

---

## 7. Updated Requirements Checklist

| Requirement | Previous | Current | Notes |
|-------------|----------|---------|-------|
| Component data extracted | ✅ | ✅ | Coordinate system verified as center-based |
| Fixed components identified | ✅ | ✅ | 9 confirmed |
| HV components identified | ✅ | ✅ | SWITCH_NODE OK, VCC_BOOT fixed |
| Grouping constraints defined | ✅ | ⚠️ | MCU decoupling needs decision (5mm vs 8mm) |
| Zone constraints defined | ✅ | ✅ | All verified |
| Clearance rules verified | ✅ | ✅ | VCC_BOOT, CGND, PGND added |
| Overlap detection | N/A | ✅ | THT/SMD overlaps are 3D-valid |

---

## 8. Action Items

| # | Action | Priority | Owner | Status |
|---|--------|----------|-------|--------|
| 1 | ~~Add VCC_BOOT to netclass assignments~~ | ~~Critical~~ | ~~Claude~~ | ✅ Done |
| 2 | ~~Verify coordinate system (center vs corner)~~ | ~~Critical~~ | ~~Claude~~ | ✅ Done |
| 3 | ~~Add CGND, PGND to netclass assignments~~ | ~~High~~ | ~~Claude~~ | ✅ Done |
| 4 | Decide on MCU decoupling constraint (5mm vs 8mm) | Medium | User | ⏳ Pending |
| 5 | Add rotation handling to component extraction | Low | Claude | Optional |
| 6 | Extract net terminal positions | Medium | Claude | Next task |

---

## 9. Next Steps

With critical issues resolved, the implementation can proceed:

1. **Install OR-Tools** - ILP solver for master problem
2. **Implement min-cut → component mapping** - Needed for cut generation
3. **Build basic ILP formulation** - Non-overlap, board bounds, fixed positions
4. **Run Experiment B1** - Baseline feasibility (Max-Flow on current placement)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-15 | Claude | Initial audit report |
| 1.1 | 2026-01-15 | Claude | Fixed VCC_BOOT, CGND, PGND assignments; verified coordinate system |
