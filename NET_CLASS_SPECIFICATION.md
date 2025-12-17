# Temper PCB Net Class Specification

**Document ID:** REQ-ELEC-01  
**Version:** 1.0  
**Date:** 2025-12-16  
**Status:** Implemented

## 1. Overview

This document defines the net class hierarchy for the Temper induction cooker PCB. Each net class specifies trace width, clearance, and via properties appropriate for the electrical characteristics of the signals/power in that class.

## 2. Net Class Summary

| Net Class | Trace Width | Clearance | Via Pad/Drill | Current | Color |
|-----------|-------------|-----------|---------------|---------|-------|
| Default | 0.2mm | 0.2mm | 0.6/0.3mm | 0.5A | Black |
| Power | 1.0mm | 0.5mm | 1.0/0.5mm | 3A | Red |
| HighVoltage | 3.0mm | 2.0mm | 1.2/0.6mm | 22A pk | Orange |
| GateDrive | 0.5mm | 0.5mm | 0.8/0.4mm | 1.5A pk | Purple |
| HighVoltageIsolated | 2.0mm | 6.0mm | 1.0/0.5mm | 2A | Magenta |
| ACMains | 2.5mm | 3.0mm | 1.2/0.6mm | 16.7A | Yellow |

## 3. Net Class Definitions

### 3.1 Default (Signal Class)

**Purpose:** General digital and analog signals with low current requirements.

**Electrical Properties:**
- Trace Width: 0.2mm (8 mil) minimum
- Clearance: 0.2mm (8 mil)
- Via: 0.6mm pad / 0.3mm drill
- Current Rating: 0.5A continuous

**Assigned Nets:**
- SPI bus: SPI_MOSI, SPI_MISO, SPI_SCK, RTD_CS
- I2C bus: I2C_SCL, I2C_SDA
- User interface: BTN_UP, BTN_DOWN, BTN_SELECT, ENCODER_A, ENCODER_B
- Control signals: SHUTDOWN_N, MCU_ENABLE, WDT_KICK, PGOOD
- Sensing: I_SENSE, V_SENSE, ZCD
- Status: FAULT_STATUS, TEMP_FAULT

**Design Guidelines:**
- Keep signal traces short where possible
- Route over continuous ground plane
- Use 45° or arc corners (no 90° bends)
- Avoid routing parallel to high-current traces

### 3.2 Power (Low Voltage Rails)

**Purpose:** DC power distribution for control electronics.

**Electrical Properties:**
- Trace Width: 1.0mm (40 mil) minimum
- Clearance: 0.5mm (20 mil)
- Via: 1.0mm pad / 0.5mm drill
- Current Rating: 3A continuous

**Assigned Nets:**
- +15V (gate driver supply)
- +3.3V (MCU, digital)
- GND (control ground)

**Design Guidelines:**
- Use via arrays for layer transitions (minimum 2 vias for power)
- Provide local decoupling at each IC (100nF minimum)
- Star topology for ground connections preferred
- Keep power traces away from sensitive analog signals

### 3.3 HighVoltage (DC Bus and Switch Node)

**Purpose:** High-power conductors carrying rectified mains and switching currents.

**Electrical Properties:**
- Trace Width: 3.0mm (120 mil) minimum, prefer copper pour
- Clearance: 2.0mm (80 mil) minimum
- Via: 1.2mm pad / 0.6mm drill
- Current Rating: 15A RMS, 22A peak

**Assigned Nets:**
- DC_BUS+ (rectified mains positive, 170-340V)
- DC_BUS- (rectified mains return)
- SWITCH_NODE (half-bridge output)

**Design Guidelines:**
- **Use copper pours, not traces** for all high-voltage conductors
- Multiple via arrays (5+ vias) for any layer transition
- Minimize loop area between DC_BUS+ and DC_BUS-
- Keep switch node area as small as possible (EMI source)
- 8mm minimum clearance to any low-voltage net
- Do not route under or near MCU

**IEC 60335 Requirements:**
- Reinforced insulation to LV circuits
- Minimum creepage: 8mm (340V, pollution degree 2)
- Minimum clearance: 4mm through air

### 3.4 GateDrive (IGBT Gate Control)

**Purpose:** High-current pulse signals from gate driver to IGBT gates.

**Electrical Properties:**
- Trace Width: 0.5mm (20 mil) minimum
- Clearance: 0.5mm (20 mil)
- Via: 0.8mm pad / 0.4mm drill
- Current Rating: 1.5A peak (gate charge current)

**Assigned Nets:**
- PWM_H (high-side PWM input to gate driver)
- PWM_L (low-side PWM input to gate driver)
- GATE_H (high-side gate output, if separate from driver)
- GATE_L (low-side gate output, if separate from driver)

**Design Guidelines:**
- **Keep gate traces as short as possible** (<25mm recommended)
- Route gate and gate return as differential pair
- Minimize loop area (gate + gate return)
- Place gate resistor immediately at gate driver output
- Shield from switch node coupling
- Use ground stitching vias around gate traces

### 3.5 HighVoltageIsolated (Bootstrap and Isolated Supplies)

**Purpose:** Floating power domains with reinforced isolation requirements.

**Electrical Properties:**
- Trace Width: 2.0mm (80 mil) minimum
- Clearance: 6.0mm (240 mil) to low-voltage domains
- Via: 1.0mm pad / 0.5mm drill
- Current Rating: 2A

**Assigned Nets:**
- +5V_ISO (isolated 5V for gate driver secondary)
- VBOOT_H (high-side bootstrap supply)
- VBOOT_L (low-side bootstrap supply)

**Design Guidelines:**
- **6mm isolation gap is mandatory** (IEC 60335 reinforced insulation)
- No ground plane under isolation gap
- Route only on outer layers in isolation region
- Physical slot in PCB at isolation barrier recommended
- Keep bootstrap capacitors close to gate driver
- Bootstrap diode close to driver VCC pin

**Safety Critical:**
- This clearance is a safety requirement, not optional
- Violation will fail hi-pot testing
- Must withstand 3000VAC for 1 minute

### 3.6 ACMains (AC Input)

**Purpose:** 120VAC mains input conductors.

**Electrical Properties:**
- Trace Width: 2.5mm (100 mil) minimum
- Clearance: 3.0mm (120 mil)
- Via: 1.2mm pad / 0.6mm drill
- Current Rating: 16.7A (2000W @ 120V)

**Assigned Nets:**
- AC_L (line)
- AC_N (neutral)
- PE (protective earth)

**Design Guidelines:**
- Use copper pours, not traces
- Route on inner layer if possible (shielding)
- Keep AC mains physically separated from control circuits
- Provide EMI filtering at entry point (common mode choke, Y-caps)
- PE connection must be reliable (multiple vias, no fuse in PE)
- Minimum 3mm from any other net class

**Regulatory Requirements:**
- Comply with IEC 60335-1 for mains circuits
- Y-capacitor leakage: <3.5mA total
- Fusing on L only (never N or PE)
- Thermal relief must not compromise current capacity

## 4. Net Class Assignment Patterns

The following wildcard patterns automatically assign nets to classes:

| Pattern | Net Class |
|---------|-----------|
| `+*V` | Power |
| `VCC*` | Power |
| `VDD*` | Power |
| `DC_BUS*` | HighVoltage |
| `GATE_*` | GateDrive |
| `PWM_*` | GateDrive |
| `VBOOT_*` | HighVoltageIsolated |
| `AC_*` | ACMains |

## 5. Inter-Class Clearance Matrix

Clearance requirements between different net classes (in mm):

| From \ To | Default | Power | HV | Gate | HV-Iso | AC |
|-----------|---------|-------|-----|------|--------|-----|
| Default | 0.2 | 0.3 | 8.0 | 0.3 | 6.0 | 3.0 |
| Power | 0.3 | 0.5 | 8.0 | 0.5 | 6.0 | 3.0 |
| HighVoltage | 8.0 | 8.0 | 2.0 | 2.0 | 2.0 | 3.0 |
| GateDrive | 0.3 | 0.5 | 2.0 | 0.5 | 0.5 | 3.0 |
| HV-Isolated | 6.0 | 6.0 | 2.0 | 0.5 | 2.0 | 6.0 |
| ACMains | 3.0 | 3.0 | 3.0 | 3.0 | 6.0 | 3.0 |

**Notes:**
- HV to LV clearance (8mm) based on IEC 60335, 340V working voltage
- HV-Iso to LV clearance (6mm) based on reinforced insulation requirement
- ACMains clearances based on IEC 60335-1 Table 16

## 6. Verification Checklist

- [ ] All nets assigned to appropriate class (no orphan nets)
- [ ] DRC configured with net class clearances
- [ ] Inter-class clearance rules defined
- [ ] Track widths verified for current capacity at 40°C rise
- [ ] Via current capacity verified (parallel vias where needed)
- [ ] High-voltage zones marked on PCB
- [ ] Isolation barriers clearly defined in layout

## 7. References

- IEC 60335-1:2020 - Household appliances - Safety (General)
- IEC 60335-2-6:2020 - Cooking appliances
- IPC-2221B - Generic Standard on Printed Board Design
- IPC-2152 - Standard for Determining Current Carrying Capacity
- UCC21550 Datasheet - Layout guidelines
- PCB_SPECIFICATION.md - Board mechanical specification
- GROUNDING_EMI_STRATEGY.md - Grounding and EMI design

## 8. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-16 | AI Agent | Initial specification |
