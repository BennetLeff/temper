# Pre-Power-On Safety Test Checklist

**Project:** Temper Induction Cooker
**Document Version:** 1.0
**Date:** 2025-12-17
**Status:** Required Before First Power-On

---

## ⚠️ CRITICAL SAFETY NOTICE

**DO NOT apply mains voltage until ALL items in this checklist are verified and signed off.**

Failure to complete these checks can result in:
- Equipment damage
- Fire hazard
- Electric shock
- Personal injury

---

## Test Equipment Required

- [ ] Digital multimeter (DMM) with continuity beeper
- [ ] Megohmmeter (insulation tester) capable of 500V DC
- [ ] Visual inspection tools (magnifier, flashlight)
- [ ] ESD protection (wrist strap, mat)
- [ ] Test log (see template at end of document)

---

## 1. Visual Inspection

**Purpose:** Identify assembly defects before electrical testing
**Test Condition:** Power OFF, unplugged

### 1.1 Component Orientation

- [ ] All ICs correctly oriented (pin 1 markers aligned)
- [ ] ESP32-S3-WROOM module correctly oriented
- [ ] UCC21550 gate driver correctly oriented
- [ ] MAX31865 RTD interfaces correctly oriented
- [ ] All diodes correctly oriented (cathode markings verified)
  - [ ] D1, D2 (MUR1560 rectifiers)
  - [ ] D_BOOT (UJ3D1210TS bootstrap diode)
  - [ ] D_DESAT_HS, D_DESAT_LS (STTH1R06)
  - [ ] D_RECT1-4 (1N4148WS signal diodes)
- [ ] All electrolytic capacitors correctly oriented (polarity marks verified)
  - [ ] C_BUS1, C_BUS2 (3300µF/250V bus caps)
  - [ ] C_BOOT (10µF/50V bootstrap cap)

### 1.2 IGBTs and Power Components

- [ ] Q1, Q2 (IKW40N120H3) correctly oriented (C-E-G pinout verified)
- [ ] Heatsinks properly mounted with NO thermal interface material voids
- [ ] Heatsink mounting screws torqued to spec (if applicable)
- [ ] No damage to IGBT packages or leads
- [ ] Thermal interface material applied uniformly, no air bubbles

### 1.3 Solder Joint Quality

- [ ] No cold solder joints (dull, rough, or cracked appearance)
- [ ] No solder bridges between adjacent pins or pads
- [ ] All through-hole leads properly wetted
- [ ] All SMD pads properly wetted with good fillet
- [ ] No excess flux residue (clean if necessary)

### 1.4 Mechanical Assembly

- [ ] All connectors fully seated and latched
- [ ] No loose wires or flying leads
- [ ] No debris, loose screws, or metal particles on PCB
- [ ] PCB mounting standoffs installed (no shorts to chassis)
- [ ] All strain relief clamps secure

### 1.5 High-Voltage Clearances

- [ ] Visual inspection of creepage/clearance at isolation boundaries:
  - [ ] AC mains to SELV (≥6mm clearance verified)
  - [ ] DC bus to SELV (≥6mm clearance verified)
  - [ ] Gate driver isolated side to SELV (≥4mm clearance verified)
- [ ] No foreign material bridging isolation barriers

---

## 2. Continuity Tests (Power Off)

**Purpose:** Verify critical safety connections
**Test Condition:** Power OFF, unplugged, DMM in continuity mode

### 2.1 Protective Earth (PE) Continuity

- [ ] PE (earth) to chassis: **< 0.1Ω** (Record: _______ Ω)
- [ ] PE to heatsink: **< 0.1Ω** (Record: _______ Ω)
- [ ] PE to all exposed metal parts: **< 0.1Ω**
  - [ ] Connector shells
  - [ ] Mounting brackets
  - [ ] Enclosure (if metal)

### 2.2 Power Rail Continuity

- [ ] 5V rail continuity to all ICs requiring 5V (< 1Ω)
- [ ] 3.3V rail continuity to ESP32-S3 (< 1Ω)
- [ ] Ground continuity across entire board (< 0.5Ω)
- [ ] No continuity between isolated sides of UCC14140 gate driver power supply
- [ ] No continuity between isolated sides of ADUM1250 I2C isolator

---

## 3. Isolation Tests (Megohmmeter & Hi-Pot)

**Purpose:** Verify isolation barriers meet safety requirements (IEC 60335-1)
**Test Condition:** Power OFF, unplugged
**Equipment:** 500V DC megohmmeter + Hi-Pot Tester (optional for prototype, required for final)

**CRITICAL:** Remove ESP32 module and sensitive ICs before testing.

### 3.1 Insulation Resistance (Megger)

- [ ] AC mains (L, N) to SELV (3.3V, 5V rails): **> 10 MΩ** at 500V DC
      (Record: _______ MΩ)
- [ ] AC mains to chassis/PE: **> 10 MΩ** at 500V DC
      (Record: _______ MΩ)

### 3.2 Dielectric Strength (Hi-Pot) - Production Only

*Warning: High Voltage. Qualified personnel only.*

- [ ] AC Mains to Chassis (Basic Insulation): 
  - Test Voltage: **1250V AC** or **1768V DC**
  - Duration: **60 seconds**
  - Leakage Current Limit: **< 5 mA**
  - Result: **PASS** (No breakdown/arc)

- [ ] AC Mains to SELV (Reinforced Insulation):
  - Test Voltage: **3000V AC** or **4242V DC**
  - Duration: **60 seconds**
  - Leakage Current Limit: **< 0.25 mA**
  - Result: **PASS** (No breakdown/arc)

### 3.2 High-Voltage DC Bus Isolation

- [ ] DC bus (+ and -) to SELV (3.3V, 5V rails): **> 10 MΩ** at 500V DC
      (Record: _______ MΩ)
- [ ] DC bus to chassis/PE: **> 10 MΩ** at 500V DC
      (Record: _______ MΩ)

### 3.3 Gate Driver Isolation

- [ ] UCC14140 primary side to secondary side: **> 10 MΩ** at 500V DC
      (Record: _______ MΩ)
- [ ] Gate driver outputs to SELV: **> 10 MΩ** at 500V DC
      (Record: _______ MΩ)

### 3.4 I2C Isolator

- [ ] ADUM1250 primary side to secondary side: **> 10 MΩ** at 500V DC
      (Record: _______ MΩ)

---

## 4. Polarity Checks

**Purpose:** Prevent component damage from reverse polarity
**Test Condition:** Power OFF, unplugged, visual and continuity verification

### 4.1 Electrolytic Capacitors

Verify polarity markings and connections:

- [ ] C_BUS1 (3300µF/250V): Positive to DC+, Negative to DC-
- [ ] C_BUS2 (3300µF/250V): Positive to DC+, Negative to DC-
- [ ] C_BOOT (10µF/50V): Positive to bootstrap high-side, Negative to SW node
- [ ] All other electrolytic capacitors correctly oriented per schematic

### 4.2 Diodes

Verify cathode orientation (band marking):

- [ ] D1, D2 (MUR1560): Cathode to DC+
- [ ] D_BOOT (UJ3D1210TS): Cathode to V_BOOT, Anode to SW node
- [ ] D_DESAT_HS, D_DESAT_LS: Per schematic

### 4.3 IGBT Pin Assignment

Verify Collector-Emitter-Gate connections using DMM diode test:

- [ ] Q1 (high-side): C to DC+, E to SW node, G to gate driver output A
- [ ] Q2 (low-side): C to SW node, E to DC-, G to gate driver output B
- [ ] Diode drop from G to E: **2-3V** (indicates gate-emitter junction intact)
- [ ] Infinite resistance C to E (both directions): **> 10 MΩ** (no short)

---

## 5. Resistance Checks (Power Off)

**Purpose:** Detect shorts and gross assembly errors
**Test Condition:** Power OFF, unplugged, DMM in resistance mode

### 5.1 Power Rail Shorts

- [ ] DC bus (+) to GND: **> 1 MΩ** (Record: _______ MΩ)
- [ ] DC bus (-) to GND: **> 1 MΩ** (Record: _______ MΩ)
- [ ] 5V rail to GND: **> 100 kΩ** (Record: _______ kΩ)
- [ ] 3.3V rail to GND: **> 100 kΩ** (Record: _______ kΩ)

**Note:** Lower resistance may indicate correct decoupling capacitors. Values below 10 kΩ indicate possible short.

### 5.2 Gate Drive Outputs

- [ ] Gate driver output A to power rails: **> 10 kΩ**
- [ ] Gate driver output B to power rails: **> 10 kΩ**
- [ ] No short between gate driver outputs A and B: **> 10 kΩ**

### 5.3 PWM Input Signals

- [ ] UCC21550 INA, INB to GND: **> 10 kΩ** (weak pull-down expected)
- [ ] No short between INA and INB

### 5.4 Resonant Tank

- [ ] C_TANK1, C_TANK2 series resistance: **< 1 Ω** (low ESR film caps)
- [ ] Induction coil DC resistance: **0.05 - 0.2 Ω** (Litz wire)

---

## 6. Initial Power-On Sequence (Low Voltage First)

**Purpose:** Verify auxiliary power supply before applying mains voltage
**Prerequisite:** ALL CHECKS ABOVE MUST PASS

### 6.1 Bench Power Supply Test (24V Input)

- [ ] Connect bench power supply to LMR51430 input (24V, current limit 500mA)
- [ ] **DO NOT** connect AC mains yet
- [ ] Power on and verify:
  - [ ] 5V output: **4.9 - 5.1V** (Record: _______ V)
  - [ ] 3.3V output: **3.25 - 3.35V** (Record: _______ V)
  - [ ] Current draw: **< 200 mA** (Record: _______ mA)
  - [ ] No excessive heating of components (touch test)
  - [ ] ESP32 boots (LED activity or UART output)

### 6.2 Gate Driver Bias Verification

- [ ] UCC14140 isolated 5V output present: **4.9 - 5.1V**
- [ ] UCC14140 isolated -5V output present: **-4.9 to -5.1V**
- [ ] No load current excessive: **< 50 mA**

---

## 7. First AC Mains Power-On (With Extreme Caution)

**Purpose:** Verify full power supply operation
**Prerequisite:** Section 6 must pass completely

### 7.1 Precautions

- [ ] Variac (variable autotransformer) set to 50V AC (25% of 120V mains)
- [ ] Isolation transformer installed
- [ ] Current-limited bench supply (5A max)
- [ ] Safety observer present
- [ ] Fire extinguisher nearby (Class C - electrical)
- [ ] Hands clear of circuit, non-conductive probe only

### 7.2 Slow Ramp-Up Test

- [ ] Apply 50V AC, verify:
  - [ ] No smoke, sparks, or unusual sounds
  - [ ] DC bus voltage: **~70V** (50V AC × √2 × 2 for voltage doubler)
  - [ ] 5V and 3.3V rails stable
- [ ] Increase to 85V AC (70% mains), verify:
  - [ ] DC bus voltage: **~120V**
  - [ ] No abnormal heating
  - [ ] All rails stable
- [ ] Increase to 120V AC (100% mains), verify:
  - [ ] DC bus voltage: **320 - 340V** (Record: _______ V)
  - [ ] NTC inrush limiter bypass relay engages after 1-2 seconds
  - [ ] All rails stable
  - [ ] No unusual heating or sounds

### 7.3 No-Load Monitoring

- [ ] Monitor for 5 minutes:
  - [ ] DC bus voltage stable: **320 - 340V**
  - [ ] Quiescent current draw: **< 500 mA** from mains
  - [ ] All ICs and power components cool to touch
  - [ ] No audible noise (transformer hum, switching whine)

---

## 8. Functional Tests (Gate Drive Disabled)

**Purpose:** Verify sensing and control before enabling power stage
**Prerequisite:** Section 7 must pass

- [ ] RTD temperature sensors (MAX31865) readable via SPI
  - [ ] RTD1 reading: **~25°C** (room temperature)
  - [ ] RTD2 reading: **~25°C** (room temperature)
- [ ] NTC thermistor (IGBT heatsink) readable via ADC
  - [ ] NTC reading: **~25°C** (room temperature)
- [ ] Current transformer output: **~0V** (no coil current)
- [ ] DC bus voltage monitoring: **320 - 340V**
- [ ] Safety interlocks:
  - [ ] OCP threshold check (inject test current)
  - [ ] OVP threshold check (adjust threshold or use voltage divider)
  - [ ] Thermal trip check (heat NTC to 85°C)
  - [ ] Watchdog timeout check (halt MCU firmware)

---

## 9. Sign-Off

### Test Results Summary

| Section | Status | Notes |
|---------|--------|-------|
| 1. Visual Inspection | ☐ PASS ☐ FAIL | ________________ |
| 2. Continuity Tests | ☐ PASS ☐ FAIL | ________________ |
| 3. Isolation Tests | ☐ PASS ☐ FAIL | ________________ |
| 4. Polarity Checks | ☐ PASS ☐ FAIL | ________________ |
| 5. Resistance Checks | ☐ PASS ☐ FAIL | ________________ |
| 6. Low-Voltage Power-On | ☐ PASS ☐ FAIL | ________________ |
| 7. AC Mains Power-On | ☐ PASS ☐ FAIL | ________________ |
| 8. Functional Tests | ☐ PASS ☐ FAIL | ________________ |

### Final Approval

**ALL sections must show PASS before proceeding to gate drive testing.**

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Technician/Builder | ____________ | ____________ | ________ |
| Engineer/Reviewer | ____________ | ____________ | ________ |

---

## 10. Failure Response Procedure

If ANY test fails:

1. **STOP** - Do not proceed to next section
2. **DISCONNECT** all power sources (mains and bench supply)
3. **DISCHARGE** high-voltage capacitors (use insulated 10kΩ resistor)
4. **DOCUMENT** the failure mode and readings
5. **INVESTIGATE** root cause using schematic and BOM
6. **REPAIR** or replace defective components
7. **RESTART** checklist from Section 1

---

## 11. Test Log Template

**PCB Serial Number:** _________________
**Build Date:** _________________
**Tester Name:** _________________
**Test Date:** _________________

### Detailed Measurements

| Test Point | Expected | Measured | Pass/Fail |
|------------|----------|----------|-----------|
| PE to Chassis | < 0.1Ω | _______ Ω | ☐ |
| AC to SELV Isolation | > 10MΩ | _______ MΩ | ☐ |
| DC Bus to SELV Isolation | > 10MΩ | _______ MΩ | ☐ |
| 5V Rail to GND | > 100kΩ | _______ kΩ | ☐ |
| 3.3V Rail to GND | > 100kΩ | _______ kΩ | ☐ |
| DC Bus Voltage (120V AC) | 320-340V | _______ V | ☐ |
| 5V Rail Output | 4.9-5.1V | _______ V | ☐ |
| 3.3V Rail Output | 3.25-3.35V | _______ V | ☐ |
| RTD1 Temperature | ~25°C | _______ °C | ☐ |
| RTD2 Temperature | ~25°C | _______ °C | ☐ |
| NTC Temperature | ~25°C | _______ °C | ☐ |

### Notes and Observations

```
___________________________________________________________________________
___________________________________________________________________________
___________________________________________________________________________
___________________________________________________________________________
```

---

## Related Documents

- `SAFETY_INTERLOCK_DESIGN.md` - Hardware safety interlock specification
- `BOM.md` - Bill of materials with part numbers
- `REQUIREMENTS.md` - REQ-SAFETY-04: Testing Requirements
- `IGBT_DESATURATION_PROTECTION.md` - DESAT circuit details

---

**Document Status:** MANDATORY PRE-POWER-ON CHECKLIST
**Revision:** 1.0
**Last Updated:** 2025-12-17

