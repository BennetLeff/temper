# Unconnected Items Analysis - Temper Deterministic Pipeline

**Board**: `pcb/temper_deterministic_final.kicad_pcb`
**Date**: 2026-01-09
**Total Unconnected Items**: 109
**Nets Affected**: 23
**Components Involved**: 29

## Executive Summary

The deterministic pipeline achieves **partial routing** on most power nets but **fails to route many critical signal nets**. The failure pattern suggests:

1. **Power Distribution**: Router attempts power nets but doesn't complete connections (vias placed, traces missing)
2. **Signal Routing**: Critical signals (gate drive, SPI, USB) not attempted or failed early
3. **HV Traces**: Some HV nets have partial traces but disconnected endpoints

## Critical Issues (10 nets)

### Ground Planes (CRITICAL)
Must be fully connected for proper operation and EMI.

| Net | Status | Pads | Vias | Components |
|-----|--------|------|------|------------|
| **GND** | ⚠️ Partial | 20 | 23 | C_CT_FILT, C_MCU_*, J_*, MAX31865, R_BURDEN, U_* (17 total) |
| **PGND** | ⚠️ Partial | 5 | 2 | C_BUS1, C_BUS2, Q2, U_GATE |
| **CGND** | ⚠️ Partial | 3 | 3 | C_VCC, U_GATE |

**Diagnosis**: Vias placed but traces not connecting all pads. Likely insufficient routing iterations or clearance violations blocking completion.

### HV Power Path (CRITICAL)
High voltage/current traces, safety critical.

| Net | Status | Pads | Tracks | Components |
|-----|--------|------|--------|------------|
| **AC_L** | ⚠️ Tracks exist | 2 | 2 | D1, J_AC_IN |
| **AC_N** | ❌ Not routed | 2 | 0 | D2, J_AC_IN |
| **DC_BUS+** | ⚠️ Tracks exist | 4 | 2 | C_BUS1, C_BUS2, D1, Q1 |
| **SW_NODE** | ⚠️ Tracks exist | 4 | 1 | C_BOOT, J_COIL, Q1, Q2 |

**Diagnosis**: Router creates traces but fails to connect endpoints. May be pin orientation or pad access issues.

### Gate Drive (CRITICAL)
IGBT/MOSFET control, timing sensitive.

| Net | Status | Pads | Components |
|-----|--------|------|------------|
| **GATE_H** | ❌ Not routed | 4 | Q1, R_GATE_H, U_GATE |
| **GATE_L** | ⚠️ Partial | 4 | Q2, R_GATE_L, U_GATE |
| **VCC_BOOT** | ❌ Not routed | 2 | C_BOOT, U_GATE |

**Diagnosis**: Critical control signals not routed. May be net ordering issue (routed too late, no space remaining).

## High Priority Issues (5 nets)

### Power Rails
| Net | Status | Pads | Vias | Components |
|-----|--------|------|------|------------|
| **+3V3** | ⚠️ Partial | 10 | 12 | C_MCU_*, J_DEBUG, MAX31865, U_CT, U_LDO_3V3, U_MCU |
| **+5V** | ⚠️ Partial | 7 | 10 | U_BUCK, U_LDO_3V3, U_LDO_5V, U_OPAMP_CT |
| **+15V** | ⚠️ Partial | 3 | 7 | C_VCC, U_BUCK, U_LDO_5V |

### Analog Sensing
Current/voltage measurement, affects control loop.

| Net | Status | Pads | Components |
|-----|--------|------|------------|
| **I_SENSE** | ❌ Not routed | 8 | C_CT_FILT, R_BURDEN, U_MCU, U_OPAMP_CT |
| **TEMP_SENSE** | ❌ Not routed | 2 | J_NTC, MAX31865 |

## Medium Priority Issues (5 nets)

### SPI Bus (MEDIUM)
MCU communication with sensors - **all 3 SPI nets failed to route**.

| Net | Status | Components |
|-----|--------|------------|
| **SPI_CLK** | ❌ Not routed | MAX31865, U_CT, U_MCU |
| **SPI_MOSI** | ❌ Not routed | MAX31865, U_CT, U_MCU |
| **SPI_MISO** | ❌ Not routed | MAX31865, U_CT, U_MCU |

### USB Interface (MEDIUM)
Differential pair, impedance controlled - **both USB signals failed**.

| Net | Status | Components |
|-----|--------|------------|
| **USB_D+** | ❌ Not routed | J_USB, U_MCU |
| **USB_D-** | ❌ Not routed | J_USB, U_MCU |

## Root Cause Analysis

### Pattern 1: Partial Power Net Routing
**Nets**: GND, +3V3, +5V, +15V, PGND, CGND
**Symptom**: Vias placed but traces don't connect all pads
**Likely Causes**:
- Router runs out of iterations before completing
- Clearance violations prevent final connections
- Net ordering causes later power connections to fail
- Zone boundaries restrict routing paths

### Pattern 2: Completely Failed Signal Routing
**Nets**: GATE_H, VCC_BOOT, I_SENSE, SPI_*, USB_*
**Symptom**: No traces or vias created at all
**Likely Causes**:
- Net ordering places these last when space exhausted
- Component placement makes these nets impossible to route
- Missing escape routing for fine-pitch components (U_MCU, U_CT)
- Differential pair handling not implemented for USB

### Pattern 3: Disconnected HV Traces
**Nets**: AC_L, DC_BUS+, SW_NODE
**Symptom**: Traces exist but don't reach pads
**Likely Causes**:
- PTH pad access issues (large pads, wrong layer)
- Trace width constraints prevent final approach
- Via placement blocks pad access

## Recommended Fixes

### Priority 1: Fix Net Ordering (CRITICAL)
**Issue**: Critical nets routed last, fail due to congestion
**Fix**: Update `NetOrderingStage` to prioritize:
1. HV power path (AC_L, AC_N, DC_BUS+, SW_NODE)
2. Gate drive (GATE_H, GATE_L, VCC_BOOT)
3. Ground planes (GND, PGND, CGND)
4. Power rails (+3V3, +5V, +15V)
5. Critical signals (I_SENSE)
6. Communication buses (SPI, USB)

### Priority 2: Increase Routing Iterations
**Issue**: Router quits before completing power nets
**Fix**: Increase max iterations per net in `SequentialRoutingStage`

### Priority 3: Improve Power Plane Routing
**Issue**: Ground/power nets need special handling
**Fix**: Implement power plane routing strategy (polygon pours or star routing)

### Priority 4: Add Escape Routing
**Issue**: Fine-pitch MCU pads not accessible
**Fix**: `FinePitchEscapeStage` may need tuning for U_MCU (ESP32)

### Priority 5: Differential Pair Support
**Issue**: USB differential pairs not routed
**Fix**: Already implemented in config but may not be applied correctly

## Next Steps

1. **Create issues for each priority fix**
2. **Run feedback loop** (temper-8hxh) to iteratively improve
3. **Tune zone geometry** to give more space for critical nets
4. **Validate with DRC after each fix**

## Appendix: Full Component List

Components involved in unconnected items:
```
C_BOOT, C_BUS1, C_BUS2, C_CT_FILT, C_MCU_1, C_MCU_2, C_MCU_3, C_MCU_4,
C_VCC, D1, D2, J_AC_IN, J_COIL, J_DEBUG, J_NTC, J_USB, MAX31865, Q1, Q2,
R_BURDEN, R_GATE_H, R_GATE_L, U_BUCK, U_CT, U_GATE, U_LDO_3V3, U_LDO_5V,
U_MCU, U_OPAMP_CT
```

This represents **29 of ~45 components** on the board, showing widespread routing failures.
