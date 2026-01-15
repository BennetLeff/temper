# Benders Placement Optimization: Design Constraints

## Overview

This document specifies the professional PCB design constraints that must be encoded into the ILP master problem for the Benders decomposition placement optimization.

These constraints represent industry best practices for mixed-signal, high-voltage PCB design and are derived from:
- IEC 62368-1 safety standards
- USB 2.0 signal integrity requirements
- Thermal management principles
- EMC design guidelines

---

## 1. Layer Stack Policy

### 1.1 Layer Assignment

| Layer | Name | Assignment | Signal Routing Allowed |
|-------|------|------------|------------------------|
| 0 | F.Cu | Primary signal routing | Yes (preferred) |
| 1 | In1.Cu | Solid GND plane | No (keep unbroken) |
| 2 | In2.Cu | Split power planes | Limited (in gaps only) |
| 3 | B.Cu | Secondary routing + GND pour | Yes |

### 1.2 Rationale

- **In1.Cu as solid GND:** Provides continuous return path for all signals, critical for USB differential impedance and EMI shielding between power stage and control section.
- **In2.Cu power split:** Separate regions for +15V (gate drive), +5V (isolated), +3.3V (MCU). Signal routing allowed in gaps between power islands.
- **B.Cu GND pour:** Thermal dissipation and additional shielding, but not a continuous plane.

### 1.3 Implementation Note

This is a **routing policy**, not an ILP constraint. The router should:
1. Prefer F.Cu for signal routing
2. Avoid routing on In1.Cu entirely
3. Allow In2.Cu routing only for non-critical nets
4. Use B.Cu as overflow

---

## 2. Thermal Constraints

### 2.1 Heat-Generating Components

| Component | Power Dissipation | Thermal Zone |
|-----------|-------------------|--------------|
| Q1 (High-side MOSFET) | High (switching losses) | Bottom edge (Y < 20mm) |
| Q2 (Low-side MOSFET) | High (switching + conduction) | Bottom edge (Y < 20mm) |
| D1 (Rectifier) | Medium (forward drop) | Power zone (Y < 50mm) |
| D2 (Rectifier) | Medium (forward drop) | Power zone (Y < 50mm) |
| U_LDO_3V3 | Low-Medium | Can be anywhere with copper pour |
| U_LDO_5V | Low-Medium | Can be anywhere with copper pour |

### 2.2 ILP Constraints

```
# MOSFETs must stay near bottom edge for heatsinking
y_Q1 ≤ 20.0 mm
y_Q2 ≤ 20.0 mm

# MOSFETs need thermal spacing to prevent coupling
|x_Q1 - x_Q2| ≥ 15.0 mm

# Rectifier diodes in power zone
y_D1 ≤ 50.0 mm
y_D2 ≤ 50.0 mm

# Electrolytic capacitors away from heat sources
y_C_BUS1 ≥ 50.0 mm  (or distance from Q1/Q2 ≥ 30mm)
y_C_BUS2 ≥ 50.0 mm
```

### 2.3 Rationale

- MOSFETs at board edge allow heatsink attachment or airflow
- Thermal spacing prevents hot spots and allows independent cooling
- Electrolytic capacitors have reduced lifetime at elevated temperatures (10°C rise = 50% life reduction)

---

## 3. EMC Constraints

### 3.1 Noise Sources and Sensitive Circuits

**Noise Sources (High dV/dt):**
- SW_NODE: Switches between DC_BUS+ and DC_BUS- at high speed
- GATE_H, GATE_L: Fast edges for MOSFET switching
- AC_L, AC_N: 50/60Hz but high voltage

**Sensitive Circuits:**
- USB_D+, USB_D-: 480Mbps differential, sensitive to noise coupling
- I_SENSE: Low-level analog signal
- SPI bus: Moderate speed digital

### 3.2 ILP Constraints

```
# USB/MCU section must stay in "quiet zone" (right side, upper area)
x_U_MCU ≥ 60.0 mm
y_U_MCU ≥ 80.0 mm

# Minimum distance from MCU to power MOSFETs
distance(U_MCU, Q1) ≥ 40.0 mm
distance(U_MCU, Q2) ≥ 40.0 mm

# Current sense circuitry away from switching noise
distance(U_CT, Q1) ≥ 30.0 mm
distance(U_CT, Q2) ≥ 30.0 mm
distance(U_OPAMP_CT, Q1) ≥ 30.0 mm
distance(U_OPAMP_CT, Q2) ≥ 30.0 mm
```

### 3.3 Board Zoning

```
+--------------------------------------------------+
|  MH3                                        MH4  |  Y=150
|                                                  |
|         QUIET ZONE (Control/Digital)             |  Y>80
|         U_MCU, J_USB, J_DEBUG                    |
|         MAX31865, U_CT, U_OPAMP_CT               |
|                                                  |
|  ------------------------------------------------|  Y=80 (EMC boundary)
|                                                  |
|         TRANSITION ZONE (Power Conversion)       |  50<Y<80
|         U_LDO_5V, U_LDO_3V3, U_BUCK              |
|         C_BUS1, C_BUS2                           |
|                                                  |
|  ------------------------------------------------|  Y=50 (Thermal boundary)
|                                                  |
|         HOT ZONE (Power Stage)                   |  Y<50
|  J_AC_IN   D1, D2, U_GATE                        |
|            Q1          Q2                        |
|  MH1                                        MH2  |  Y=0
+--------------------------------------------------+
   X=0                                         X=100
```

---

## 4. Component Grouping Constraints

### 4.1 Decoupling Capacitor Groups

Decoupling capacitors must remain close to their associated ICs for effective high-frequency bypass.

| IC | Capacitors | Max Distance | Priority |
|----|------------|--------------|----------|
| U_MCU | C_MCU_1, C_MCU_2, C_MCU_3, C_MCU_4 | 5.0 mm | Critical |
| U_GATE | C_VCC, C_BOOT | 8.0 mm | Critical |
| U_CT | C_CT_FILT | 5.0 mm | High |
| U_OPAMP_CT | R_BURDEN | 5.0 mm | High |

### 4.2 ILP Constraints

```
# MCU decoupling - all caps within 5mm of MCU
distance(U_MCU, C_MCU_1) ≤ 5.0 mm
distance(U_MCU, C_MCU_2) ≤ 5.0 mm
distance(U_MCU, C_MCU_3) ≤ 5.0 mm
distance(U_MCU, C_MCU_4) ≤ 5.0 mm

# Gate driver group
distance(U_GATE, C_VCC) ≤ 8.0 mm
distance(U_GATE, C_BOOT) ≤ 8.0 mm

# Current sense group
distance(U_CT, C_CT_FILT) ≤ 5.0 mm
distance(U_OPAMP_CT, R_BURDEN) ≤ 5.0 mm

# Gate resistors near gate driver
distance(U_GATE, R_GATE_H) ≤ 10.0 mm
distance(U_GATE, R_GATE_L) ≤ 10.0 mm
```

### 4.3 Group Movement Strategy

When the ILP moves a grouped IC, its associated passives should move proportionally:

```
# If U_MCU moves by (Δx, Δy), then C_MCU_* should move similarly
# This can be implemented as:
# Option A: Move as rigid group (same Δx, Δy)
# Option B: Constrain relative positions (maintain distance ≤ max)

# Recommended: Option B (more flexible, allows local optimization)
```

---

## 5. Movement Budget Constraints

### 5.1 Per-Component Limits

| Category | Components | Max Movement | Rationale |
|----------|------------|--------------|-----------|
| Fixed | J_AC_IN, J_COIL, J_DEBUG, J_NTC, J_USB, MH1-4 | 0 mm | Mechanical constraints |
| Thermal-Critical | Q1, Q2 | 5 mm | Must stay in thermal zone |
| HV-Critical | D1, D2 | 10 mm | Power stage topology |
| Bulk Capacitors | C_BUS1, C_BUS2 | 10 mm | Large, affects routing |
| Gate Driver Group | U_GATE, C_VCC, C_BOOT | 8 mm | Grouped movement |
| MCU Group | U_MCU, C_MCU_1-4 | 10 mm | Grouped movement |
| Free ICs | U_BUCK, U_LDO_3V3, U_LDO_5V, U_CT, U_OPAMP_CT | 15 mm | Flexible |
| Free Passives | R_GATE_H, R_GATE_L, R_BURDEN, C_CT_FILT | 15 mm | Most flexible |

### 5.2 ILP Constraints

```
# Per-component movement limits
|x_Q1 - x_Q1⁰| + |y_Q1 - y_Q1⁰| ≤ 5.0 mm
|x_Q2 - x_Q2⁰| + |y_Q2 - y_Q2⁰| ≤ 5.0 mm
|x_D1 - x_D1⁰| + |y_D1 - y_D1⁰| ≤ 10.0 mm
|x_D2 - x_D2⁰| + |y_D2 - y_D2⁰| ≤ 10.0 mm
# ... etc for all components

# Global movement budget (prevents radical redesign)
Σ_i (|x_i - x_i⁰| + |y_i - y_i⁰|) ≤ 100.0 mm

# Maximum single-component movement
max_i (|x_i - x_i⁰| + |y_i - y_i⁰|) ≤ 15.0 mm
```

### 5.3 Objective Function

```
minimize: Σ_i w_i × (|x_i - x_i⁰| + |y_i - y_i⁰|)

where w_i = weight for component i:
  - Thermal-critical: w = 2.0 (penalize movement)
  - HV-critical: w = 1.5
  - Grouped ICs: w = 1.2
  - Free: w = 1.0
```

---

## 6. High-Voltage Clearance Constraints

### 6.1 Clearance Requirements by Net Class

| Net Class | Clearance | Nets |
|-----------|-----------|------|
| ACMains | 6.0 mm | AC_L, AC_N, PE |
| HighVoltage | 3.0 mm | DC_BUS+, DC_BUS-, SW_NODE |
| HighVoltageIsolated | 6.0 mm | +5V_ISO, VBOOT_H, VBOOT_L |
| All others | 0.2-0.5 mm | (per net class) |

### 6.2 Component-to-Component HV Clearance

```
# Any component connected to ACMains must be 6mm from LV components
For each HV_component h connected to {AC_L, AC_N, PE}:
  For each LV_component l not connected to HV nets:
    distance(h, l) ≥ 6.0 mm

# Components connected to HighVoltage need 3mm clearance
For each HV_component h connected to {DC_BUS+, DC_BUS-, SW_NODE}:
  For each LV_component l not connected to HV nets:
    distance(h, l) ≥ 3.0 mm
```

### 6.3 HV Components List

| Component | HV Nets | Required Clearance to LV |
|-----------|---------|--------------------------|
| J_AC_IN | AC_L, AC_N | 6.0 mm (FIXED - can't move) |
| D1 | AC_L, DC_BUS+ | 6.0 mm (due to AC_L) |
| D2 | AC_N, DC_BUS- | 6.0 mm (due to AC_N) |
| Q1 | DC_BUS+, SW_NODE | 3.0 mm |
| Q2 | DC_BUS-, SW_NODE | 3.0 mm |
| C_BUS1 | DC_BUS+ | 3.0 mm |
| C_BUS2 | DC_BUS- | 3.0 mm |
| U_GATE | SW_NODE, VCC_BOOT | 3.0 mm |
| C_BOOT | SW_NODE, VCC_BOOT | 3.0 mm |
| J_COIL | SW_NODE | 3.0 mm (FIXED) |

---

## 7. Non-Overlap Constraints

### 7.1 Basic Non-Overlap

All components must not physically overlap:

```
For each pair (i, j) where i ≠ j:
  (x_i + w_i ≤ x_j) OR (x_j + w_j ≤ x_i) OR
  (y_i + h_i ≤ y_j) OR (y_j + h_j ≤ y_i)
```

### 7.2 Manufacturing Clearance

Minimum 0.2mm clearance between component bodies for manufacturability:

```
For each pair (i, j) where i ≠ j:
  (x_i + w_i + 0.2 ≤ x_j) OR (x_j + w_j + 0.2 ≤ x_i) OR
  (y_i + h_i + 0.2 ≤ y_j) OR (y_j + h_j + 0.2 ≤ y_i)
```

---

## 8. Board Boundary Constraints

```
# All components must fit within board
For each component i:
  x_i ≥ 0
  y_i ≥ 0
  x_i + w_i ≤ 100.0 mm (board width)
  y_i + h_i ≤ 150.0 mm (board height)

# Keep components away from mounting holes (3mm clearance)
For each component i, for each mounting hole MH at (mx, my):
  distance(i, MH) ≥ 3.0 mm
```

---

## 9. Constraint Summary Table

| Constraint Type | Count | Priority |
|-----------------|-------|----------|
| Fixed positions | 9 | Hard |
| Non-overlap | C(33,2) = 528 pairs | Hard |
| Board bounds | 33 × 4 = 132 | Hard |
| HV clearance | ~80 pairs | Hard |
| Thermal zones | 4 components | Hard |
| EMC zones | 6 components | Hard |
| Component grouping | 12 pairs | Hard |
| Movement budget | 33 + 2 global | Soft (in objective) |

**Total hard constraints:** ~760
**Variables:** 48 continuous (24 movable components × 2 coordinates) + ~500 binary (for disjunctions)

---

## 10. Validation Checklist

Before accepting an ILP solution, verify:

- [ ] No component overlaps (including 0.2mm manufacturing clearance)
- [ ] All components within board bounds
- [ ] HV clearances satisfied (6mm for ACMains, 3mm for HighVoltage)
- [ ] Thermal-critical components in thermal zone (Y < 20mm for Q1/Q2)
- [ ] EMC-sensitive components in quiet zone (Y > 80mm for MCU)
- [ ] All grouping constraints satisfied (decoupling caps near ICs)
- [ ] Total movement within budget (< 100mm)
- [ ] No single component moved > 15mm
- [ ] Max-Flow ≥ net demand (routability verified)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-15 | Claude | Initial professional design constraints |
