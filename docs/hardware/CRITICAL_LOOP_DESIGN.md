# Critical Loop Area Minimization Specification

**Document ID:** REQ-ELEC-06  
**Version:** 1.0  
**Date:** 2025-12-16  
**Status:** Implemented  
**References:** GROUNDING_EMI_STRATEGY.md, UCC21550 Layout Guide

## 1. Overview

Critical loop areas are PCB current paths that carry high di/dt or dV/dt signals. Large loop areas act as antennas, radiating EMI and coupling noise to sensitive circuits. This document specifies loop area targets and layout strategies for the Temper induction cooker.

## 2. EMI Fundamentals

### 2.1 Loop Area and EMI Relationship

Radiated EMI is proportional to:
- Loop area (A)
- Frequency (f²)
- Current (I)

```
E_radiated ∝ A × f² × I
```

For a half-bridge switching at 38 kHz with 22A peak and 50V/ns dV/dt, even small loop areas can generate significant EMI.

### 2.2 Inductance and Loop Area

Loop inductance is approximately:
```
L ≈ µ₀ × (perimeter / π) × ln(perimeter / wire_width)
```

For practical PCB loops:
```
L ≈ 1.2 nH/mm of perimeter (narrow trace)
L ≈ 0.5 nH/mm of perimeter (wide pour)
```

**Target:** <20nH for main switching loop, <10nH for gate loops.

## 3. Critical Loop Identification

### 3.1 Loop Priority Classification

| Priority | Loop | Frequency | Current | dV/dt | Target Area |
|----------|------|-----------|---------|-------|-------------|
| 1 | DC Bus Switching | 38 kHz | 22A | 50V/ns | <5 cm² |
| 2 | Gate Drive (High-side) | 38 kHz | 1.5A | - | <2 cm² |
| 3 | Gate Drive (Low-side) | 38 kHz | 1.5A | - | <2 cm² |
| 4 | Bootstrap Charging | 38 kHz | 100mA | - | <1 cm² |
| 5 | Buck Converter | 600 kHz | 3A | 30V/ns | <0.5 cm² |
| 6 | Decoupling | DC-100MHz | <1A | - | <0.25 cm² |

## 4. DC Bus Switching Loop (Priority 1)

### 4.1 Current Path

```
                          SWITCHING LOOP
                          
    ┌────────────────────────────────────────────────────┐
    │                                                    │
    │    ┌──────┐          ┌───────┐         ┌──────┐   │
    │    │      │          │       │         │      │   │
    │    │C_BUS │──────────│  Q1   │─────────│      │   │
    │    │      │  DC+     │ (Hi)  │         │      │   │
    │    │ 400V │          │       │         │      │   │
    │    │      │          └───┬───┘         │      │   │
    │    │      │              │             │      │   │
    │    │      │         [SW_NODE]          │  L   │   │
    │    │      │              │             │  (Tank)  │
    │    │      │          ┌───┴───┐         │      │   │
    │    │      │          │       │         │      │   │
    │    │      │──────────│  Q2   │─────────│      │   │
    │    │      │  DC-     │ (Lo)  │         │      │   │
    │    └──────┘          └───────┘         └──────┘   │
    │                                                    │
    └───────── Current flows in this loop ───────────────┘
              during each switching transition
```

### 4.2 Loop Area Calculation

**Target:** <5 cm² (500 mm²)

**Example compliant layout:**
- Bus cap to Q1 collector: 15mm × 5mm trace = 75mm² (one side)
- Q1 to Q2 (SW node): 10mm × 5mm = 50mm² (one side)
- Q2 emitter to cap: 15mm × 5mm = 75mm² (one side)
- **Total loop:** ~200mm² (compliant with margin)

**Non-compliant example:**
- Bus cap 50mm away from IGBTs
- Traces routed on different layers
- Total loop: >1000mm² (FAILS)

### 4.3 Layout Requirements

| Requirement | Value | Rationale |
|-------------|-------|-----------|
| Bus cap to IGBT distance | <20mm | Minimize inductance |
| DC+ and DC- trace spacing | Adjacent (2mm gap) | Magnetic cancellation |
| Copper width | ≥5mm pour | Low inductance |
| Via count (layer transition) | 12+ array | Distribute current |
| Switch node area | <3 cm² | Minimize antenna |

### 4.4 Recommended Layout

```
           TOP VIEW (Layer 1)
           
    ┌────────────────────────────────────────────────┐
    │                                                │
    │   ┌─────────┐     ┌─────────┐                  │
    │   │         │     │         │                  │
    │   │  C_BUS  │─────│   Q1    │──────┐           │
    │   │  (+)    │     │ (IGBT)  │      │           │
    │   │         │     │         │      │           │
    │   └────┬────┘     └────┬────┘      │           │
    │        │               │           │           │
    │   ┌────┴────┐     ┌────┴────┐      │           │
    │   │         │     │         │      │ SW_NODE   │
    │   │  C_BUS  │─────│   Q2    │◄─────┤ (small    │
    │   │  (-)    │     │ (IGBT)  │      │  pour)    │
    │   │         │     │         │      │           │
    │   └─────────┘     └─────────┘      │           │
    │                                     │           │
    │                              [To Tank]         │
    │                                                │
    └────────────────────────────────────────────────┘
    
    KEY:
    ═══ DC+ copper pour
    ─── DC- copper pour (adjacent, 2mm gap)
    SW_NODE kept minimal
```

### 4.5 Verification Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Loop area | <5 cm² | Measure in layout tool |
| Loop inductance | <20nH | Calculate or simulate |
| Voltage overshoot | <50V | Oscilloscope at SW node |
| Ringing frequency | >20MHz | Indicates low L |

## 5. Gate Drive Loops (Priority 2-3)

### 5.1 Gate Drive Current Path

```
                    GATE DRIVE LOOP
                    
    ┌─────────────────────────────────────────┐
    │                                         │
    │   UCC21550                              │
    │   ┌─────────┐                           │
    │   │         │                           │
    │   │   OUT   │──[Rg]──────────[GATE]     │
    │   │         │                   │       │
    │   │   GND   │───────────────────│       │
    │   │         │         [SOURCE]──┘       │
    │   └─────────┘                           │
    │                                         │
    └─── Gate current loop ───────────────────┘
```

### 5.2 Gate Loop Requirements

| Requirement | Value | Rationale |
|-------------|-------|-----------|
| Loop area | <2 cm² per gate | Fast switching, low ringing |
| Gate resistor location | <5mm from driver | Damp oscillations at source |
| Gate/source routing | Differential pair | Magnetic cancellation |
| Via under gate resistor | Avoid if possible | Inductance increase |

### 5.3 High-Side Gate Layout

```
    UCC21550                                    Q1 (IGBT)
    ┌─────────┐                               ┌─────────┐
    │         │                               │         │
    │  OUTH   │═══[Rg_H]══════════════════════│  GATE   │
    │         │           ← 2mm gap →         │         │
    │  GNDS   │═══════════════════════════════│ SOURCE  │
    │         │                               │  (E1)   │
    └─────────┘                               └─────────┘
    
    Total length: <30mm
    Traces as differential pair, 0.5mm wide, 2mm gap
```

### 5.4 Low-Side Gate Layout

Same structure as high-side, but source connects to DC_BUS-.

### 5.5 Gate Loop Inductance Budget

| Component | Inductance | Notes |
|-----------|------------|-------|
| Driver output | ~2nH | Internal to UCC21550 |
| PCB trace (30mm) | ~6nH | 0.2nH/mm for diff pair |
| Gate resistor | ~1nH | SMD 0603 |
| IGBT package | ~5nH | Internal lead |
| **Total** | ~14nH | Within 20nH budget |

## 6. Bootstrap Charging Loop (Priority 4)

### 6.1 Bootstrap Current Path

```
    5V Supply ───► D_BOOT ───► C_BOOT ───► UCC21550 VBS
                    │            │
                    └────────────┘
                  (Charging loop)
```

### 6.2 Bootstrap Layout Requirements

| Requirement | Value | Rationale |
|-------------|-------|-----------|
| Loop area | <1 cm² | Fast charging during dead-time |
| C_boot location | <5mm from VBS pin | Minimize inductance |
| D_boot location | Adjacent to C_boot | Short path |
| Via under C_boot | Avoid | Direct connection preferred |

### 6.3 Bootstrap Component Placement

```
    UCC21550 Package
    ┌──────────────────────────────────────┐
    │                                      │
    │  [VBS]──┬──[C_BOOT 1µF]──[GND_H]     │
    │         │                            │
    │         └──[D_BOOT]──[5V]            │
    │                                      │
    └──────────────────────────────────────┘
    
    All bootstrap components within 5mm of VBS pin
```

## 7. Buck Converter Loop (Priority 5)

### 7.1 Buck Switching Path

```
                    BUCK CONVERTER LOOP
                    
    ┌────────────────────────────────────────────────┐
    │                                                │
    │   ┌─────────┐      ┌───────────┐   ┌───────┐  │
    │   │         │      │           │   │       │  │
    │   │  C_IN   │──────│ LMR51430  │───│   L   │──┼──► VOUT
    │   │         │      │           │   │       │  │
    │   └────┬────┘      └─────┬─────┘   └───────┘  │
    │        │                 │                    │
    │        │            [SW NODE]                 │
    │        │            (minimize!)               │
    │        │                 │                    │
    │        └─────────────────┘                    │
    │                                               │
    └─── Input cap to SW node loop ─────────────────┘
```

### 7.2 Buck Converter Layout Requirements

| Requirement | Value | Rationale |
|-------------|-------|-----------|
| Input loop area | <0.5 cm² | 600kHz switching |
| C_in location | <3mm from VIN | Critical for stability |
| SW node area | <1 cm² | EMI source |
| Output cap | <5mm from VOUT | Output ripple |
| Thermal pad vias | 6+ to GND | Heat dissipation |

### 7.3 LMR51430 Recommended Layout

```
    LMR51430 Package (SOIC-8)
    ┌────────────────────────────────────────────┐
    │                                            │
    │  VIN ─────[C_IN 10µF]───────── GND         │
    │   │                             │          │
    │   └──[<3mm]───────────[<3mm]────┘          │
    │                                            │
    │  SW ──────[L 10µH]─────────[C_OUT]── VOUT  │
    │   │                          │             │
    │   └──[minimize area]─────────┘             │
    │                                            │
    │  [THERMAL PAD] ─── [6 vias to GND]         │
    │                                            │
    └────────────────────────────────────────────┘
```

## 8. Decoupling Loop Optimization (Priority 6)

### 8.1 Decoupling Principle

Every IC power pin should have minimal loop area to its decoupling capacitor.

```
    OPTIMAL DECOUPLING
    
    VCC Pin ──┬─────────────── Power Plane (L3)
              │
         [C_DECOUP]  ← <5mm from pin
              │
    GND Pin ──┴─────────────── Ground Plane (L2)
    
    Loop formed by: VCC pin → Cap → GND pin → IC internal
    Target: <0.25 cm² (25mm²)
```

### 8.2 Decoupling Placement Rules

| IC Type | Cap Value | Max Distance | Via Requirement |
|---------|-----------|--------------|-----------------|
| ESP32-S3 | 100nF + 10nF | 3mm | Direct to planes |
| UCC21550 | 10µF + 100nF | 5mm | Via to GND |
| MAX31865 | 100nF | 3mm | Via to planes |
| Op-amps | 100nF | 5mm | Via to planes |
| LDO output | 10µF + 100nF | 3mm | Via to planes |

### 8.3 Capacitor Via Strategy

```
    CAPACITOR PLACEMENT (Cross-section view)
    
         Component (Top)
              │
    L1 ═══════╪═══════════════════
              │
         [C_DECOUP]
              │        Via to GND
    L2 ───────┼────────●──────────  Ground Plane
              │        │
    L3 ═══════╪════════╪══════════  Power Plane
              │        │
    L4 ───────┴────────┴──────────
         Via to VCC
    
    Vias directly at cap pads, shortest path to planes
```

## 9. Layout Verification Checklist

### 9.1 DC Bus Loop

- [ ] Bus capacitor <20mm from IGBTs
- [ ] DC+ and DC- pours adjacent (2mm gap)
- [ ] Switch node area <3 cm²
- [ ] No unnecessary vias in main current path
- [ ] 12+ via array at any layer transition
- [ ] Calculated loop area <5 cm²

### 9.2 Gate Drive Loops

- [ ] Gate resistor <5mm from UCC21550
- [ ] Gate/source routed as differential pair
- [ ] Total gate trace length <30mm
- [ ] No vias between driver and gate resistor
- [ ] Gate and source return adjacent (2mm gap)
- [ ] Each gate loop <2 cm²

### 9.3 Bootstrap Loops

- [ ] Bootstrap cap <5mm from VBS pin
- [ ] Bootstrap diode adjacent to cap
- [ ] No unnecessary trace length
- [ ] Each bootstrap loop <1 cm²

### 9.4 Buck Converter

- [ ] Input cap <3mm from VIN pin
- [ ] SW node area <1 cm²
- [ ] Output cap <5mm from VOUT pin
- [ ] Thermal pad has 6+ vias to GND
- [ ] Input loop area <0.5 cm²

### 9.5 Decoupling

- [ ] Every IC has local decoupling <5mm
- [ ] Decoupling caps have direct vias to planes
- [ ] ESP32 has 100nF at each VDD pin
- [ ] UCC21550 has 10µF + 100nF at VCCI

## 10. Measurement and Testing

### 10.1 Loop Area Measurement

In KiCad or other layout tool:
1. Use polygon tool to trace current path
2. Calculate enclosed area
3. Document in design review

### 10.2 Inductance Estimation

For quick estimation:
```
L (nH) ≈ 1.2 × Perimeter (mm) × ln(Perimeter / Width)
```

For more accurate results, use ANSYS Q3D or similar.

### 10.3 Bench Verification

| Test | Equipment | Pass Criteria |
|------|-----------|---------------|
| SW node ringing | 500MHz scope, 10:1 probe | <100V overshoot |
| Gate voltage ringing | 500MHz scope | <2V overshoot |
| Radiated EMI | EMI receiver, antenna | EN 55014 Class B |
| Conducted EMI | LISN, spectrum analyzer | EN 55014 Class B |

## 11. References

- UCC21550 Datasheet, Section 11 - Layout Guidelines
- LMR51430 Datasheet - PCB Layout Guidelines
- IKW40N120H3 Application Note - Gate Drive Design
- GROUNDING_EMI_STRATEGY.md - Ground domain architecture
- EN 55014-1 - EMC requirements for household appliances

## 12. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-16 | AI Agent | Initial specification |
