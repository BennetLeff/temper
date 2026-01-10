# Temper Induction Cooker - PCB Design Specification

**Project:** Temper - Production-grade Induction Cooker  
**Target Chassis:** RCA 12A3 (vintage tube amp enclosure)  
**Version:** 1.0  
**Date:** 2025-12-14  
**Status:** Design Phase

---

## 1. Executive Summary

This document specifies the PCB design requirements for the Temper induction cooker, targeting installation in an RCA 12A3 vintage tube amplifier chassis. The design prioritizes:

- **Fit:** 100mm x 150mm (4" x 6") board size
- **Safety:** IEC 60335-2-6 compliant isolation and creepage
- **Manufacturability:** Partial PCBA with hand-solderable power components
- **Quality:** ENIG finish for reliable fine-pitch assembly

---

## 2. Mechanical Specifications

### 2.1 Board Dimensions

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Width** | 100mm (3.94") | Fits RCA 12A3 chassis width |
| **Length** | 150mm (5.91") | Standard fab size, no surcharge |
| **Thickness** | 1.6mm (0.063") | Standard FR4 |
| **Tolerance** | ±0.15mm | Standard |
| **Corner radius** | 3mm | Rounded corners for handling |

### 2.2 Mounting

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Mounting holes** | 4x M3 (3.2mm) | One at each corner |
| **Hole spacing from edge** | 5mm | Standard standoff clearance |
| **Keep-out from holes** | 3mm radius | No copper/components |
| **Standoff height** | 8mm minimum | Clearance for bottom components |

### 2.3 RCA 12A3 Chassis Constraints

```
┌─────────────────────────────────────────────────────────────┐
│                    RCA 12A3 CHASSIS TOP                     │
│                    (~230mm x 180mm)                         │
│                                                             │
│   ┌─────────┐                              ┌─────────┐      │
│   │ XFORMER │                              │ XFORMER │      │
│   │  (OPT)  │     ┌──────────────────┐     │ (POWER) │      │
│   └─────────┘     │                  │     └─────────┘      │
│                   │   PCB LOCATION   │                      │
│    [TUBE]         │   100mm x 150mm  │        [TUBE]        │
│   SOCKET          │                  │       SOCKET         │
│                   │   (This design)  │                      │
│                   │                  │                      │
│                   └──────────────────┘                      │
│                                                             │
│   ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○   (vent holes)   │
│                                                             │
│                    [FRONT PANEL]                            │
└─────────────────────────────────────────────────────────────┘

Notes:
- Original tube sockets may be repurposed as connector mounts
- Power transformer may be reused for AC input isolation
- Vent holes provide natural cooling airflow
```

### 2.4 Height Constraints

| Zone | Max Height (Top) | Max Height (Bottom) | Notes |
|------|------------------|---------------------|-------|
| General | 25mm | 3mm | Standard component clearance |
| Heatsink area | 40mm | 0mm | IGBTs mount vertically |
| Connector edge | 15mm | 0mm | Panel mount clearance |

---

## 3. Layer Stackup

### 3.1 4-Layer Configuration

| Layer | Name | Function | Copper Weight | Notes |
|-------|------|----------|---------------|-------|
| L1 | Top | Power components, HV traces | 2 oz (70µm) | High-current paths |
| L2 | GND | Ground plane (split PGND/CGND) | 1 oz (35µm) | Reference plane |
| L3 | PWR | Power plane (5V, 3.3V islands) | 1 oz (35µm) | Power distribution |
| L4 | Bottom | Control signals, gate drive | 1 oz (35µm) | Signal routing |

### 3.2 Dielectric Stack

```
         ┌─────────────────────────────────────┐
   L1    │  2 oz copper (70µm)                 │  Top - Power
         ├─────────────────────────────────────┤
         │  Prepreg: 0.2mm (7.8 mil) FR4      │
         ├─────────────────────────────────────┤
   L2    │  1 oz copper (35µm)                 │  Ground Plane
         ├─────────────────────────────────────┤
         │  Core: 1.0mm (39.4 mil) FR4        │
         ├─────────────────────────────────────┤
   L3    │  1 oz copper (35µm)                 │  Power Plane
         ├─────────────────────────────────────┤
         │  Prepreg: 0.2mm (7.8 mil) FR4      │
         ├─────────────────────────────────────┤
   L4    │  1 oz copper (35µm)                 │  Bottom - Control
         └─────────────────────────────────────┘
         
Total thickness: ~1.6mm (63 mil)
```

### 3.3 Impedance Targets (if controlled impedance required)

| Type | Target | Tolerance | Trace Width (L1/L4) |
|------|--------|-----------|---------------------|
| Single-ended | 50Ω | ±10% | 0.28mm over ground |
| Differential | 100Ω | ±10% | 0.15mm, 0.15mm gap |

*Note: Controlled impedance not required for this design (no high-speed signals >50MHz)*

---

## 4. Fabrication Specifications

### 4.1 Base Specifications

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Material** | FR4 TG150 | Standard high-Tg epoxy |
| **Surface finish** | ENIG | 3-5µin Au over 120-240µin Ni |
| **Solder mask** | Green or Black | LPI, both sides |
| **Silkscreen** | White | Top side minimum, bottom optional |
| **Min trace width** | 0.15mm (6 mil) | Signal traces |
| **Min trace space** | 0.15mm (6 mil) | Signal traces |
| **Min annular ring** | 0.15mm (6 mil) | Vias |
| **Min drill** | 0.3mm (12 mil) | Mechanical drill |

### 4.2 Via Specifications

| Via Type | Drill | Pad | Annular Ring | Usage |
|----------|-------|-----|--------------|-------|
| Standard | 0.3mm | 0.6mm | 0.15mm | Signal vias |
| Power | 0.5mm | 1.0mm | 0.25mm | Power distribution |
| Thermal | 0.4mm | 0.8mm | 0.2mm | Thermal relief |

### 4.3 Surface Finish Comparison (Reference)

| Finish | Flatness | Shelf Life | Fine-Pitch | Lead-Free | Cost |
|--------|----------|------------|------------|-----------|------|
| HASL | Poor | Good | Fair | Available | $ |
| **ENIG** | Excellent | Excellent | Excellent | Yes | $$ |
| OSP | Good | Poor | Good | Yes | $ |
| Immersion Tin | Good | Fair | Good | Yes | $$ |

**Selected: ENIG** - Required for ESP32-S3 module (0.5mm pitch) and fine-pitch ICs.

---

## 5. Net Classes and Design Rules

### 5.1 Net Class Definitions

| Net Class | Trace Width | Clearance | Via Size | Current Rating | Usage |
|-----------|-------------|-----------|----------|----------------|-------|
| **Default** | 0.2mm | 0.2mm | 0.6/0.3mm | 0.5A | General signals |
| **Power** | 1.0mm | 0.5mm | 1.0/0.5mm | 3A | 5V, 3.3V rails |
| **HighVoltage** | 2.0mm | 2.0mm | 1.2/0.6mm | 10A | DC bus, IGBT |
| **GateDrive** | 0.5mm | 0.5mm | 0.8/0.4mm | 1A | Gate driver outputs |

### 5.2 High-Voltage Clearance Rules

Per IEC 60335-2-6 and creepage/clearance requirements:

| Isolation | Voltage | Min Clearance | Min Creepage | Design Value |
|-----------|---------|---------------|--------------|--------------|
| Basic (line-to-low voltage) | 400V | 3mm | 4mm | 6mm |
| Reinforced (across barrier) | 400V | 6mm | 8mm | 10mm |
| Functional (within domain) | 50V | 0.5mm | 1mm | 2mm |

### 5.3 Current Capacity Reference

External traces (L1/L4) at 2oz copper, 20°C rise:

| Width | Current (External) | Current (Internal) |
|-------|-------------------|-------------------|
| 0.5mm | 1.8A | 1.2A |
| 1.0mm | 3.2A | 2.2A |
| 2.0mm | 5.5A | 4.0A |
| 3.0mm | 7.5A | 5.5A |
| 5.0mm | 11A | 8A |

*For 22A peak IGBT current: Use 10mm+ trace or copper pour with thermal relief*

---

## 6. Component Placement Zones

### 6.1 Zone Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PCB TOP VIEW                                    │
│                           (100mm x 150mm)                                    │
│                                                                              │
│  ○                                                                      ○    │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                                                                    │    │
│   │   ZONE A: HIGH-VOLTAGE / POWER                                     │    │
│   │   ┌──────────────────────────────────────────────────────────┐    │    │
│   │   │  • DC Bus Capacitors (C_BUS1, C_BUS2)                    │    │    │
│   │   │  • Voltage Doubler Diodes (D1, D2)                       │    │    │
│   │   │  • Bleeder Resistors                                      │    │    │
│   │   │  • Inrush Limiter (NTC)                                   │    │    │
│   │   │  • Bypass Relay                                           │    │    │
│   │   │  • EMI Filter Components                                  │    │    │
│   │   └──────────────────────────────────────────────────────────┘    │    │
│   │                                                                    │    │
│   │   ════════════════ ISOLATION BARRIER (10mm) ═══════════════════   │    │
│   │                                                                    │    │
│   │   ZONE B: HALF-BRIDGE / GATE DRIVE                                │    │
│   │   ┌──────────────────────────────────────────────────────────┐    │    │
│   │   │  • IGBT Mounting (Q1, Q2) - Edge mount to heatsink       │    │    │
│   │   │  • UCC21550 Gate Driver                                   │    │    │
│   │   │  • Bootstrap Circuit (D_BOOT, C_BOOT)                     │    │    │
│   │   │  • Gate Resistors (RG_ON, RGS)                            │    │    │
│   │   │  • Resonant Tank Connections (off-board)                  │    │    │
│   │   └──────────────────────────────────────────────────────────┘    │    │
│   │                                                                    │    │
│   │   ════════════════ GROUND SPLIT LINE ══════════════════════════   │    │
│   │                                                                    │    │
│   │   ZONE C: POWER MANAGEMENT                                        │    │
│   │   ┌─────────────────┐    ┌─────────────────────────────────────┐  │    │
│   │   │  LMR51430 Buck  │    │  XC6220 LDO                         │  │    │
│   │   │  24V → 5V       │───▶│  5V → 3.3V                          │  │    │
│   │   │  + Inductor     │    │                                     │  │    │
│   │   └─────────────────┘    └─────────────────────────────────────┘  │    │
│   │                                                                    │    │
│   │   ZONE D: CONTROL / DIGITAL                                       │    │
│   │   ┌──────────────────────────────────────────────────────────┐    │    │
│   │   │  • ESP32-S3-WROOM Module                                  │    │    │
│   │   │  • MAX31865 RTD Interfaces (x2)                           │    │    │
│   │   │  • ADUM1250 I2C Isolator                                  │    │    │
│   │   │  • Safety Interlock Logic (74HC series)                   │    │    │
│   │   │  • TPS3823 Watchdog                                       │    │    │
│   │   │  • OCP/OVP Comparators                                    │    │    │
│   │   │  • Status LEDs                                            │    │    │
│   │   └──────────────────────────────────────────────────────────┘    │    │
│   │                                                                    │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│  ○                                                                      ○    │
│                                                                              │
│           [CONNECTORS: AC_IN, COIL_OUT, TEMP_SENSE, UI]                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Zone Specifications

| Zone | Ground Domain | Copper Weight | Max Voltage | Key Components |
|------|---------------|---------------|-------------|----------------|
| A | PGND | 2oz | 400V DC | Bus caps, rectifiers |
| B | PGND/ISOGND | 2oz | 400V DC | IGBTs, gate driver |
| C | AGND | 1oz | 24V | Buck, LDO |
| D | CGND | 1oz | 3.3V | MCU, sensors, logic |

### 6.3 Critical Placement Rules

1. **IGBT Placement:**
   - Mount on board edge for heatsink attachment
   - Minimize gate trace length (<20mm)
   - Bootstrap capacitor within 10mm of driver

2. **Buck Converter (LMR51430):**
   - Input cap within 3mm of VIN pin
   - Output cap within 5mm of VOUT pin
   - Inductor placement minimizes SW node area
   - Keep SW node away from sensitive analog

3. **ESP32-S3 Module:**
   - Antenna keep-out zone: 15mm clearance (no copper/ground)
   - Decoupling caps within 3mm of power pins
   - Crystal area free of high-speed signals

4. **MAX31865:**
   - Place close to RTD connector
   - Reference resistor within 5mm
   - Route SPI away from power traces

---

## 7. Ground Plane Design

### 7.1 Split Ground Implementation

Reference: GROUNDING_EMI_STRATEGY.md

```
Layer 2 (Ground Plane):

┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   ┌─────────────────────────────┐                                           │
│   │                             │                                           │
│   │     POWER GROUND (PGND)     │                                           │
│   │                             │                                           │
│   │  • DC bus return            │                                           │
│   │  • IGBT emitters            │                                           │
│   │  • Resonant tank            │                                           │
│   │                             │                                           │
│   └──────────────┬──────────────┘                                           │
│                  │                                                           │
│                  │ STAR GROUND POINT                                         │
│                  │ (Single connection, via array)                            │
│                  │                                                           │
│   ┌──────────────┴──────────────────────────────────────────────────────┐   │
│   │                                                                      │   │
│   │              CONTROL GROUND (CGND)                                   │   │
│   │                                                                      │   │
│   │  • ESP32-S3          • MAX31865        • Safety logic               │   │
│   │  • ADC reference     • ADUM1250 (side 1)                            │   │
│   │                                                                      │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────┐                                                    │
│   │  ISOLATED GROUND    │  (No connection to CGND/PGND)                     │
│   │  (ISOGND)           │                                                    │
│   │                     │                                                    │
│   │  • UCC21550 high-side                                                   │
│   │  • ADUM1250 (side 2)                                                    │
│   └─────────────────────┘                                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Star Ground Implementation

- **Location:** Adjacent to DC bus negative terminal
- **Connection:** 20+ vias in via array (0.4mm drill, 0.8mm pad)
- **Width:** 10mm minimum copper bridge between domains
- **Rule:** No signals cross the ground split except at star point

---

## 8. Assembly Specifications

### 8.1 Assembly Strategy: Partial PCBA

| Assembly Method | Components | Rationale |
|-----------------|------------|-----------|
| **PCBA (SMT)** | ESP32 module, ICs, small passives | Fine-pitch, high precision |
| **Hand solder (THT)** | Bus caps, IGBTs, connectors, relay | Large, easy to place, may need rework |

### 8.2 PCBA Components (SMT)

| Reference | Package | Notes |
|-----------|---------|-------|
| U_MCU | ESP32-S3-WROOM | Module, pick-and-place |
| U_GD | SOIC-16 | UCC21550 |
| U_BUCK | SOT-23-6 | LMR51430 |
| U_LDO | SOT-25 | XC6220 |
| U_RTD1, U_RTD2 | TQFN-20 | MAX31865 |
| U_ISO | SOIC-8 | ADUM1250 |
| All 0603/0805 | Passives | R, C components |
| Logic ICs | SOIC-14 | 74HC series |

### 8.3 Hand-Solder Components (THT)

| Reference | Package | Notes |
|-----------|---------|-------|
| Q1, Q2 | TO-247 | IGBTs, mount to heatsink |
| C_BUS1, C_BUS2 | Radial 25mm | 3300µF 250V |
| D1, D2 | TO-220 | Rectifier diodes |
| D_BOOT | TO-220 | SiC Schottky (or SOD-323 SMD) |
| NTC_INRUSH | Radial | Inrush limiter |
| K_BYPASS | Through-hole | Relay |
| Connectors | Various | AC in, coil out, sensors |
| L_BUCK | 10x10mm | Through-hole pads |

### 8.4 Solder Paste Specifications

| Parameter | Value |
|-----------|-------|
| Alloy | SAC305 (Sn96.5/Ag3.0/Cu0.5) |
| Mesh | Type 4 (20-38µm) |
| Stencil thickness | 0.12mm (5 mil) |
| Aperture reduction | 0% for 0603+, 10% for 0402 |

### 8.5 Reflow Profile (Lead-Free)

| Zone | Temperature | Time |
|------|-------------|------|
| Preheat | 150-200°C | 60-120s |
| Soak | 200-217°C | 60-90s |
| Reflow | 235-250°C peak | 40-60s above 217°C |
| Cooling | <6°C/s | - |

---

## 9. Design for Test (DFT)

### 9.1 Test Points

| Test Point | Signal | Access | Purpose |
|------------|--------|--------|---------|
| TP1 | OR_OUTPUT | Top | Combined fault signal |
| TP2 | LATCH_Q | Top | Latched fault state |
| TP3 | GATE_DISABLE | Top | Final gate disable |
| TP4 | V_BOOT | Top | Bootstrap voltage |
| TP5 | SW_NODE | Top | Half-bridge midpoint |
| TP6 | 5V_RAIL | Top | Buck output |
| TP7 | 3V3_RAIL | Top | LDO output |
| TP8 | PGND | Top | Power ground reference |
| TP9 | CGND | Top | Control ground reference |

### 9.2 Programming/Debug Header

| Header | Pins | Usage |
|--------|------|-------|
| J_PROG | 6-pin | ESP32 UART programming (TX, RX, EN, IO0, 3V3, GND) |
| J_JTAG | 10-pin | Optional JTAG debug (ARM 10-pin) |

### 9.3 Fiducials

- **Global fiducials:** 3x, 1mm diameter copper circle with 2mm solder mask opening
- **Local fiducials:** Near ESP32 module (fine-pitch placement)

---

## 10. Silkscreen Requirements

### 10.1 Markings (Required)

| Item | Location | Content |
|------|----------|---------|
| Project name | Top, corner | "TEMPER v1.0" |
| Polarity | Near polarized components | +/- symbols |
| Pin 1 | Near ICs | Dot or triangle |
| Connector labels | Near each connector | J1, J2, etc. |
| Test points | Near TP pads | TP1-TP9 |
| Warning | Near HV area | "DANGER: HIGH VOLTAGE" |
| Component outlines | All components | Reference designator |

### 10.2 Safety Markings

- High-voltage area boundary line
- "CAUTION: 400V DC" near bus capacitors
- Earth ground symbol at PE connection
- Isolation barrier indication

---

## 11. Design Files Checklist

### 11.1 Fabrication Package

| File | Format | Purpose |
|------|--------|---------|
| Gerber files | RS-274X | Layer artwork |
| NC Drill | Excellon | Drill locations |
| Pick and place | CSV | Component positions |
| BOM | CSV/Excel | Bill of materials |
| Assembly drawing | PDF | Reference for hand assembly |
| Schematic | PDF | Reference |
| 3D model | STEP | Mechanical verification |

### 11.2 Gerber Layer Names

| Layer | File Extension | Content |
|-------|---------------|---------|
| Top Copper | .GTL | L1 copper |
| Bottom Copper | .GBL | L4 copper |
| Inner 1 | .G2L | L2 ground plane |
| Inner 2 | .G3L | L3 power plane |
| Top Solder Mask | .GTS | Top mask |
| Bottom Solder Mask | .GBS | Bottom mask |
| Top Silkscreen | .GTO | Top legend |
| Bottom Silkscreen | .GBO | Bottom legend |
| Top Paste | .GTP | Stencil apertures |
| Board Outline | .GKO | Mechanical outline |
| Drill | .DRL | NC drill file |

---

## 12. Vendor Specifications

### 12.1 Recommended PCB Fabricators

| Vendor | Capability | Lead Time | Cost (10 pcs) | Notes |
|--------|------------|-----------|---------------|-------|
| JLCPCB | 4-layer, ENIG | 5-7 days | ~$50 | PCBA available |
| PCBWay | 4-layer, ENIG | 5-7 days | ~$60 | Good customer service |
| OSH Park | 4-layer | 12-14 days | ~$100 | Made in USA |
| Elecrow | 4-layer, ENIG | 7-10 days | ~$45 | Budget option |

### 12.2 Order Specifications Summary

```
Board Size: 100mm x 150mm
Layers: 4
Thickness: 1.6mm
Copper: 2oz outer, 1oz inner
Surface Finish: ENIG
Solder Mask: Green (or Black)
Silkscreen: White
Min Trace/Space: 6/6 mil
Min Hole: 0.3mm
Impedance Control: No
Via Type: Through-hole only
```

### 12.3 PCBA Specifications

```
Assembly Side: Top only
Components: ~80 SMD placements
Stencil: Top side, 0.12mm
Solder: SAC305 lead-free
Profile: Standard reflow
Special: ESP32 module requires pick-and-place accuracy <0.1mm
```

---

## 13. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-14 | - | Initial specification |

---

## 14. References

| Document | Purpose |
|----------|---------|
| BOM.md | Bill of materials |
| GROUNDING_EMI_STRATEGY.md | Ground plane and isolation design |
| GATE_DRIVER_POWER_ARCHITECTURE_DECISION.md | Bootstrap circuit requirements |
| SAFETY_INTERLOCK_DESIGN.md | Safety circuit layout |
| IEC 60335-2-6 | Cooking appliance safety standard |
| IPC-2221B | PCB design standard |

---

**END OF SPECIFICATION**
