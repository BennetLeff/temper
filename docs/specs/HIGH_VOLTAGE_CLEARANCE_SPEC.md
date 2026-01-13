# High-Voltage Clearance and Creepage Specification

**Document ID:** REQ-ELEC-04  
**Version:** 1.0  
**Date:** 2025-12-16  
**Status:** Implemented  
**Standard:** IEC 60335-1, IEC 60335-2-6, IEC 61010-1

## 1. Overview

This document defines clearance (through air) and creepage (along surface) requirements for the Temper induction cooker PCB to ensure safety compliance with household appliance standards.

## 2. Voltage Domains

### 2.1 Domain Definitions

| Domain | ID | Reference | Working Voltage | Peak/Transient | Classification |
|--------|-----|-----------|-----------------|----------------|----------------|
| AC Mains | A | Earth/Neutral | 120-240V RMS | 340V | Hazardous |
| DC Bus | B | DC_BUS- | 170-340V DC | 400V (transient) | Hazardous |
| Gate Drive Isolated | C | IGBT Source | 15V (floating at 340V) | 355V to earth | Hazardous |
| Low Voltage Control | D | CGND | 3.3-15V | 20V | SELV |
| Protective Earth | PE | Earth | 0V | Fault current | Safety |

### 2.2 Domain Locations on PCB

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TEMPER PCB (100mm × 150mm)                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐        ┌──────────────────────────────────┐   │
│  │                  │        │                                  │   │
│  │   DOMAIN A       │        │         DOMAIN B                 │   │
│  │   AC MAINS       │        │         DC BUS                   │   │
│  │                  │        │                                  │   │
│  │  • AC input      │        │  • Bridge rectifier              │   │
│  │  • EMI filter    │        │  • Bus capacitors                │   │
│  │  • Fuse          │        │  • IGBTs (collector)             │   │
│  │                  │        │  • Switch node                   │   │
│  └────────┬─────────┘        └──────────────┬───────────────────┘   │
│           │                                  │                       │
│           │ 6mm clearance                    │ 8mm clearance         │
│           │ (basic insulation)               │ (reinforced)          │
│           ▼                                  ▼                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                                                              │   │
│  │                    ISOLATION BARRIER                         │   │
│  │              (2mm routed slot in PCB)                        │   │
│  │                                                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│           │                                  │                       │
│           │                                  │                       │
│           ▼                                  ▼                       │
│  ┌──────────────────┐        ┌──────────────────────────────────┐   │
│  │                  │        │                                  │   │
│  │   DOMAIN D       │        │         DOMAIN C                 │   │
│  │   LOW VOLTAGE    │        │         GATE DRIVE ISOLATED      │   │
│  │                  │        │                                  │   │
│  │  • ESP32-S3      │        │  • UCC21550 output side          │   │
│  │  • MAX31865      │◄──────►│  • Bootstrap supply              │   │
│  │  • UI circuits   │ I2C    │  • IGBT gates/sources            │   │
│  │  • ADC sensing   │(ADUM)  │                                  │   │
│  │                  │        │                                  │   │
│  └──────────────────┘        └──────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 3. IEC 60335 Requirements

### 3.1 Applicable Standards

| Standard | Title | Application |
|----------|-------|-------------|
| IEC 60335-1 | Safety of household appliances - General | General safety requirements |
| IEC 60335-2-6 | Particular requirements for cooking ranges | Induction hob specific |
| IEC 61010-1 | Safety for measurement equipment | Control/sensing circuits |
| IEC 60664-1 | Insulation coordination | Clearance/creepage basis |

### 3.2 Environmental Parameters

| Parameter | Value | Justification |
|-----------|-------|---------------|
| **Pollution Degree** | 2 | Normal indoor environment, condensation possible |
| **Overvoltage Category** | III | Equipment connected to mains distribution |
| **Material Group** | IIIb | FR4 CTI 175-249V |
| **Altitude** | ≤2000m | Standard household use |
| **Working Temperature** | 60°C max ambient | Kitchen environment near cooking |

### 3.3 Insulation Types

| Type | Description | Test Voltage | Application |
|------|-------------|--------------|-------------|
| **Functional** | Minimum for operation | None required | Within same voltage domain |
| **Basic** | Single fault protection | 1500V AC 1 min | Mains to accessible parts |
| **Supplementary** | Second layer over basic | 1500V AC 1 min | Double insulation systems |
| **Reinforced** | Equivalent to double | 3000V AC 1 min | HV to SELV isolation |

## 4. Clearance Requirements

### 4.1 Clearance Table (Through Air)

Based on IEC 60664-1 Table F.2 for Overvoltage Category III, Pollution Degree 2:

| Working Voltage (V) | Basic (mm) | Reinforced (mm) | Design Value (mm) |
|--------------------|------------|-----------------|-------------------|
| 50 | 0.5 | 1.0 | 1.5 |
| 100 | 0.7 | 1.4 | 2.0 |
| 150 | 1.0 | 2.0 | 2.5 |
| 200 | 1.3 | 2.6 | 3.0 |
| 300 | 2.0 | 4.0 | 5.0 |
| 400 | 2.5 | 5.0 | 6.0 |
| 600 | 4.0 | 8.0 | 10.0 |

### 4.2 Design Clearances

| Boundary | Insulation | Working V | Min Required | Design Value |
|----------|------------|-----------|--------------|--------------|
| AC Mains (L/N) to PE | Basic | 340V pk | 2.5mm | 4.0mm |
| AC Mains to SELV (Domain D) | Reinforced | 340V pk | 5.0mm | 8.0mm |
| DC Bus to SELV (Domain D) | Reinforced | 400V pk | 5.0mm | 8.0mm |
| DC Bus to Gate Iso (Domain C) | Functional | 15V | 0.5mm | 1.0mm |
| Gate Iso to SELV (Domain D) | Reinforced | 355V | 5.0mm | 8.0mm |
| Within SELV (Domain D) | Functional | 15V | 0.2mm | 0.5mm |
| Any HV to Exposed Metal | Basic | 400V | 2.5mm | 4.0mm |

## 5. Creepage Requirements

### 5.1 Creepage Table (Along Surface)

Based on IEC 60335-1 Table 16, Pollution Degree 2, Material Group IIIb:

| Working Voltage (V) | Basic (mm) | Reinforced (mm) | Design Value (mm) |
|--------------------|------------|-----------------|-------------------|
| 50 | 1.2 | 2.4 | 3.0 |
| 100 | 1.6 | 3.2 | 4.0 |
| 150 | 2.0 | 4.0 | 5.0 |
| 200 | 2.5 | 5.0 | 6.0 |
| 300 | 4.0 | 8.0 | 10.0 |
| 400 | 5.0 | 10.0 | 12.0 |

### 5.2 Design Creepage

| Boundary | Insulation | Working V | Min Required | Design Value |
|----------|------------|-----------|--------------|--------------|
| AC Mains to SELV | Reinforced | 340V pk | 8.0mm | 10.0mm |
| DC Bus to SELV | Reinforced | 400V pk | 10.0mm | 12.0mm |
| Across UCC21550 | Reinforced | 400V | 10.0mm | Per device spec |
| IGBT tab to LV trace | Reinforced | 400V | 10.0mm | 12.0mm |
| Within SELV | Functional | 15V | 0.5mm | 1.0mm |

## 6. Isolation Barrier Design

### 6.1 PCB Slot Specification

A routed slot in the PCB creates a physical barrier between high-voltage and low-voltage domains.

**Slot Parameters:**
- **Width:** 2.0mm minimum
- **Depth:** Full board thickness (1.6mm)
- **Location:** Between Domain B/C and Domain D
- **Length:** Full board width where domains meet

**Creepage Enhancement:**
```
Without slot:  Creepage = surface distance only
With slot:     Creepage = 2 × slot width + surface across slot
               Effective creepage = 2 × 2.0mm + 4.0mm = 8.0mm minimum
```

### 6.2 Slot Routing Rules

```
                    SLOT CROSS-SECTION
                    
     HV Side                          LV Side
    (Domain B)                       (Domain D)
        │                                │
        │◄──── 6mm min ────►│◄── 6mm min ──►│
        │                    │              │
   ─────┴────────────────────┴──────────────┴─────  L1 (Top)
                    ║        ║
                    ║ 2.0mm  ║                      Slot (routed)
                    ║  slot  ║
   ─────────────────╨────────╨────────────────────  L4 (Bottom)
        │                    │              │
        │                    │              │
    No copper            No copper      No copper
    within 2mm          in slot        within 2mm
```

### 6.3 Under-Component Clearances

**UCC21550 Isolated Gate Driver:**
- Minimum 1.0mm clearance between primary and secondary pins
- No traces on any layer under the isolation barrier
- Ground plane cutout under transformer region (center of package)
- Per UCC21550 datasheet Figure 34 layout recommendation

**ADUM1250 I2C Isolator:**
- 4.0mm minimum between Side 1 and Side 2 pins
- No ground plane under center of package
- Place isolation slot under device if possible

### 6.4 Conformal Coating Zones

For additional creepage in tight areas, apply conformal coating:

**Coating Type:** Silicone or Acrylic (IPC-CC-830)
**Thickness:** 25-75 µm
**Creepage Multiplier:** ×1.5 for coated surfaces

**Coating Zones:**
1. Around IGBT TO-247 mounting pads
2. UCC21550 package perimeter
3. High-voltage connector area
4. Bootstrap diode/capacitor area

## 7. Component-Specific Clearances

### 7.1 IGBT (IKW40N120H3) TO-247

**Hazard:** Collector tab at DC bus potential (340V)

| Clearance Path | Requirement | Design |
|----------------|-------------|--------|
| Tab to nearest LV trace | 8mm clearance, 12mm creepage | 12mm |
| Tab to mounting hole | 4mm (to chassis ground) | 5mm |
| Gate pin to collector tab | Per package (internal) | N/A |
| Emitter to collector tab | Per package (internal) | N/A |

**PCB Layout:**
- No LV traces within 12mm radius of collector tab
- Dedicated copper pour for collector (DC bus)
- Thermal pad connected via thermal vias to internal plane

### 7.2 Rectifier Bridge

**Hazard:** AC pins at mains potential, DC pins at bus potential

| Clearance Path | Requirement | Design |
|----------------|-------------|--------|
| AC pins to SELV | 8mm clearance | 10mm |
| DC+ to PE connection | 4mm clearance | 5mm |
| Between AC pins | Per device | Functional |

### 7.3 Bus Capacitors

**Hazard:** Terminals at 340V DC, stored energy hazard

| Clearance Path | Requirement | Design |
|----------------|-------------|--------|
| Terminals to SELV | 8mm clearance | 10mm |
| Terminals to chassis | 4mm clearance | 5mm |
| Between terminals | 2mm clearance | 3mm |

### 7.4 Current Transformer (CT)

**Hazard:** Primary at DC bus current, secondary isolated

| Clearance Path | Requirement | Design |
|----------------|-------------|--------|
| Primary to secondary | Per device isolation | Verify spec |
| Secondary to SELV | Functional (galvanically isolated) | 2mm |

## 8. Verification Matrix

### 8.1 Clearance Verification Checklist

| Location | Required | Actual | Status |
|----------|----------|--------|--------|
| AC_L to CGND | 8.0mm | ___mm | ☐ Pass |
| AC_N to CGND | 8.0mm | ___mm | ☐ Pass |
| DC_BUS+ to CGND | 8.0mm | ___mm | ☐ Pass |
| DC_BUS- to CGND | 8.0mm | ___mm | ☐ Pass |
| SWITCH_NODE to CGND | 8.0mm | ___mm | ☐ Pass |
| IGBT Q1 tab to LV | 8.0mm | ___mm | ☐ Pass |
| IGBT Q2 tab to LV | 8.0mm | ___mm | ☐ Pass |
| UCC21550 Pin 1-8 to 9-16 | 1.0mm | ___mm | ☐ Pass |
| ADUM1250 Side1 to Side2 | 4.0mm | ___mm | ☐ Pass |
| Isolation slot width | 2.0mm | ___mm | ☐ Pass |

### 8.2 Creepage Verification Checklist

| Location | Required | Actual | Status |
|----------|----------|--------|--------|
| AC Mains to SELV | 10.0mm | ___mm | ☐ Pass |
| DC Bus to SELV | 12.0mm | ___mm | ☐ Pass |
| IGBT tab to nearest trace | 12.0mm | ___mm | ☐ Pass |
| Across isolation barrier | 8.0mm | ___mm | ☐ Pass |

### 8.3 Hi-Pot Test Requirements

| Test | Voltage | Duration | Leakage Limit |
|------|---------|----------|---------------|
| Mains to SELV | 3000V AC | 1 minute | <5mA |
| Mains to PE | 1500V AC | 1 minute | <5mA |
| DC Bus to SELV | 3000V AC | 1 minute | <5mA |
| Isolation barrier | 5700V RMS | 1 minute | Per UCC21550 |

## 9. KiCad Design Rules

### 9.1 Custom DRC Rules

Add to project design rules (`.kicad_dru` or inline):

```
# High-voltage clearance rules for IEC 60335 compliance

# AC Mains to SELV (reinforced insulation)
(rule "HV_AC_to_SELV"
  (condition "A.NetClass == 'ACMains' && B.NetClass == 'Default'")
  (constraint clearance (min 8.0mm)))

(rule "HV_AC_to_SELV_creepage"
  (condition "A.NetClass == 'ACMains' && B.NetClass == 'Default'")
  (constraint creepage (min 10.0mm)))

# DC Bus to SELV (reinforced insulation)
(rule "HV_DC_to_SELV"
  (condition "A.NetClass == 'HighVoltage' && B.NetClass == 'Default'")
  (constraint clearance (min 8.0mm)))

# Isolation barrier - HV-Isolated to SELV
(rule "Isolation_barrier"
  (condition "A.NetClass == 'HighVoltageIsolated' && B.NetClass == 'Default'")
  (constraint clearance (min 6.0mm)))
```

### 9.2 Zone Definitions

Create keep-out zones in KiCad:
1. **HV Zone** - Contains AC mains, DC bus, switch node
2. **LV Zone** - Contains ESP32, MAX31865, user interface
3. **Isolation Zone** - 2mm slot + 6mm keep-out on each side

## 10. References

- IEC 60335-1:2020 - Safety of household appliances - General
- IEC 60335-2-6:2020 - Particular requirements for cooking ranges
- IEC 60664-1:2020 - Insulation coordination
- IEC 61010-1:2010 - Safety for measurement equipment
- UCC21550 Datasheet - Layout guidelines (Section 11)
- GROUNDING_EMI_STRATEGY.md - Ground domain definitions
- NET_CLASS_SPECIFICATION.md - Net class clearances

## 11. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-16 | AI Agent | Initial specification |
