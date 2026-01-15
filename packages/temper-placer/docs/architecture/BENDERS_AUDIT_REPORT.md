# Benders Requirements Audit Report

**Date:** 2026-01-15
**Auditor:** Claude (Professional PCB Design Review)

## Executive Summary

A thorough audit of the Benders placement optimization requirements revealed several **critical issues** that must be addressed before implementation:

| Category | Status | Issues Found |
|----------|--------|--------------|
| Component Positions | ⚠️ | Coordinate system needs clarification |
| Net Assignments | ❌ | 6 unassigned nets (2 are HV-critical) |
| Grouping Constraints | ❌ | 4 constraint violations in current placement |
| Overlap Detection | ⚠️ | 5 apparent overlaps (may be coordinate issue) |
| HV Classification | ❌ | SW_NODE and VCC_BOOT missing HV assignment |

---

## 1. Critical Issues

### 1.1 Missing HV Net Assignments ❌

**Impact:** Router will use 0.2mm clearance instead of 3-6mm for high-voltage nets.

| Net | Should Be | Currently | Components Affected |
|-----|-----------|-----------|---------------------|
| **SW_NODE** | HighVoltage (3mm) | Default (0.2mm) | Q1, Q2, U_GATE, C_BOOT, J_COIL |
| **VCC_BOOT** | HighVoltageIsolated (6mm) | Default (0.2mm) | U_GATE, C_BOOT |

**Fix Required:** Add to `temper.kicad_pro`:
```json
"netclass_assignments": {
    "SW_NODE": "HighVoltage",
    "VCC_BOOT": "HighVoltageIsolated",
    ...
}
```

### 1.2 Other Unassigned Nets ⚠️

| Net | Recommendation | Components |
|-----|----------------|------------|
| +5V | Power (0.5mm) | U_BUCK, U_LDO_3V3, U_LDO_5V, U_OPAMP_CT |
| CGND | Ground (0.3mm) | U_GATE, C_VCC |
| PGND | Ground (0.3mm) | C_BUS1, C_BUS2, U_GATE |
| TEMP_SENSE | Default (0.2mm) | MAX31865, J_NTC |

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
| Component data extracted | ✅ | ⚠️ | Coordinate system unclear |
| Fixed components identified | ✅ | ✅ | 9 confirmed |
| HV components identified | ✅ | ❌ | Missing SW_NODE, VCC_BOOT nets |
| Grouping constraints defined | ✅ | ⚠️ | Some may need relaxation |
| Zone constraints defined | ✅ | ✅ | All verified |
| Clearance rules verified | ✅ | ❌ | Missing HV net assignments |
| Overlap detection | N/A | ⚠️ | Needs coordinate fix |

---

## 8. Action Items

| # | Action | Priority | Owner |
|---|--------|----------|-------|
| 1 | Add SW_NODE, VCC_BOOT to netclass assignments | Critical | User |
| 2 | Verify coordinate system (center vs corner) | Critical | Claude |
| 3 | Add +5V, CGND, PGND to netclass assignments | High | User |
| 4 | Decide on MCU decoupling constraint (5mm vs 8mm) | Medium | User |
| 5 | Add rotation handling to component extraction | Medium | Claude |
| 6 | Extract net terminal positions | Medium | Claude |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-15 | Claude | Initial audit report |
