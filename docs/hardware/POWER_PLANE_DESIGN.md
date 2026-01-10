# Power Plane Design and Layer Stackup Specification

**Document ID:** REQ-ELEC-05  
**Version:** 1.0  
**Date:** 2025-12-16  
**Status:** Implemented  
**References:** PCB_SPECIFICATION.md, GROUNDING_EMI_STRATEGY.md

## 1. Overview

This document specifies the power plane design for the Temper 4-layer PCB, including ground plane splits, power islands, and via stitching strategy.

## 2. Layer Stackup

### 2.1 Physical Stack

```
         Z (mm)
           │
    0.000  ┼─────────────────────────────────────┐  Solder Mask Top
           │                                     │
    0.035  │  ████████ L1: TOP (2 oz) ████████  │  Power components, HV pours
           │                                     │
    0.070  ┼─────────────────────────────────────┤  Prepreg 1 (0.2mm)
           │                                     │
    0.270  ┼─────────────────────────────────────┤
           │                                     │
    0.305  │  ████████ L2: GND (1 oz) ████████  │  Ground plane (split)
           │                                     │
    0.340  ┼─────────────────────────────────────┤  Core (1.0mm)
           │                                     │
           │                                     │
           │                                     │
    1.340  ┼─────────────────────────────────────┤
           │                                     │
    1.375  │  ████████ L3: PWR (1 oz) ████████  │  Power plane (islands)
           │                                     │
    1.410  ┼─────────────────────────────────────┤  Prepreg 2 (0.2mm)
           │                                     │
    1.610  ┼─────────────────────────────────────┤
           │                                     │
    1.645  │  ████████ L4: BOT (1 oz) ████████  │  Control signals, gate drive
           │                                     │
    1.680  ┼─────────────────────────────────────┘  Solder Mask Bottom
```

### 2.2 Layer Function Summary

| Layer | Name | Copper | Primary Function | Secondary Function |
|-------|------|--------|------------------|-------------------|
| L1 | TOP | 2 oz | HV copper pours (DC bus, switch node) | Power components |
| L2 | GND | 1 oz | Ground reference plane | EMI shielding |
| L3 | PWR | 1 oz | Power distribution (+5V, +3.3V, +15V) | Thermal spreading |
| L4 | BOT | 1 oz | Control signals, digital | Gate drive routing |

### 2.3 Impedance Characteristics

| Configuration | Reference | Impedance | Trace Width |
|--------------|-----------|-----------|-------------|
| Microstrip L1→L2 | GND plane | 50Ω | 0.28mm |
| Microstrip L4→L3 | PWR plane | 50Ω | 0.28mm |
| Stripline L2 or L3 | Both ref | 50Ω | 0.20mm |

*Note: Controlled impedance not required for this design (max signal frequency ~100MHz for ESP32).*

## 3. Ground Plane Design (Layer 2)

### 3.1 Ground Domain Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 2: GROUND PLANE                               │
│                         100mm × 150mm                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌────────────────────────────────┬──┬────────────────────────────────────┐│
│  │                                │SP│                                    ││
│  │     POWER GROUND (PGND)        │  │      CONTROL GROUND (CGND)         ││
│  │                                │A │                                    ││
│  │  Area: ~60% (60cm²)            │R │      Area: ~35% (52cm²)            ││
│  │                                │  │                                    ││
│  │  Contains:                     │P │      Contains:                     ││
│  │  • DC bus return               │O │      • ESP32-S3 module             ││
│  │  • IGBT emitters (Q1, Q2)      │I │      • MAX31865 (pan temp)         ││
│  │  • Resonant tank return        │N │      • Safety logic                ││
│  │  • Bridge rectifier (-)        │T │      • User interface              ││
│  │  • CT burden resistor          │  │      • ADC references              ││
│  │  • Input capacitors            │  │      • SPI/I2C routing reference   ││
│  │  • Snubber networks            │  │                                    ││
│  │                                │  │                                    ││
│  └────────────────────────────────┴──┴────────────────────────────────────┘│
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │                   ISOLATED GROUND (ISOGND)                             ││
│  │                   Area: ~5% (8cm²)                                     ││
│  │                                                                        ││
│  │  Contains:                                                             ││
│  │  • UCC21550 output side (VGND1, VGND2)                                 ││
│  │  • Bootstrap capacitor returns                                         ││
│  │  • ADUM1250 isolated side                                              ││
│  │  • MAX31865 #2 (IGBT temp) - if isolated                               ││
│  │                                                                        ││
│  │  ⚠ NO GALVANIC CONNECTION TO PGND OR CGND                              ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

LEGEND:
SP = Star Point (single 10mm bridge, PGND↔CGND connection)
```

### 3.2 Star Ground Point Specification

**Location:** Adjacent to DC bus negative terminal
**Size:** 10mm × 10mm copper bridge
**Via Array:** 20 vias minimum (4×5 array, 0.5mm drill, 1.5mm pitch)

**Connection Rules:**
1. PGND and CGND connect ONLY at the star point
2. All ground return currents must flow through the star point
3. No signal traces cross the ground split except at star point
4. Star point placed to minimize high-current loop area

```
           PGND Side                    CGND Side
              │                             │
    [DC Bus-]─┤                             ├─[ESP32 GND]
              │                             │
    [IGBT E1]─┤     ┌─────────────┐         ├─[MAX31865 GND]
              │     │             │         │
    [IGBT E2]─┤     │  STAR POINT │         ├─[UI GND]
              │     │   (20 vias) │         │
    [CT Rtn]──┤─────┤             ├─────────┤─[ADC REF]
              │     │   10mm ×    │         │
              │     │   10mm      │         │
              │     └─────────────┘         │
              │                             │
```

### 3.3 Ground Plane Rules

| Rule | Requirement | Rationale |
|------|-------------|-----------|
| Minimum copper width | 5mm at narrowest | Current capacity |
| Split gap width | 2mm | Prevent capacitive coupling |
| Via stitching pitch | ≤λ/20 @ 100MHz = 15mm | EMI containment |
| No traces crossing split | Except at star point | Prevent ground loops |
| Keep plane solid | No unnecessary cuts | Minimize inductance |

### 3.4 Ground Plane Voids

Voids (copper cutouts) are required in specific locations:

| Location | Size | Layer | Reason |
|----------|------|-------|--------|
| Under UCC21550 transformer | 8mm × 4mm | L2 | Isolation barrier |
| Under ADUM1250 center | 4mm × 2mm | L2 | Isolation barrier |
| Isolation slot zone | 2mm × board width | L2 | HV-LV separation |
| Under high-dV/dt nodes | Minimize area | L2 | Reduce capacitive coupling |

## 4. Power Plane Design (Layer 3)

### 4.1 Power Island Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 3: POWER PLANE                                │
│                         100mm × 150mm                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                                                                         ││
│  │                        +5V ISLAND                                       ││
│  │                        Area: ~40% (60cm²)                               ││
│  │                                                                         ││
│  │  Source: LMR51430 output (5V, 2A)                                       ││
│  │                                                                         ││
│  │  Loads:                                                                 ││
│  │  • Gate driver VCC (UCC21550 VCCI)           ~100mA                     ││
│  │  • Fan driver                                 ~500mA                    ││
│  │  • Relay coil driver                          ~100mA                    ││
│  │  • Op-amps (LM324 or similar)                 ~10mA                     ││
│  │  • XC6220 LDO input                           ~500mA → 3.3V             ││
│  │                                                                         ││
│  │  Decoupling: 10µF + 100nF at each load                                  ││
│  │                                                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                                                                         ││
│  │                        +3.3V ISLAND                                     ││
│  │                        Area: ~30% (45cm²)                               ││
│  │                                                                         ││
│  │  Source: XC6220 LDO output (3.3V, 700mA)                                ││
│  │                                                                         ││
│  │  Loads:                                                                 ││
│  │  • ESP32-S3 module                            ~300mA peak               ││
│  │  • MAX31865 RTD interface (#1)                ~2mA                      ││
│  │  • ADUM1250 side 1                            ~5mA                      ││
│  │  • Safety logic ICs                           ~10mA                     ││
│  │  • Level shifters (if any)                    ~5mA                      ││
│  │                                                                         ││
│  │  Decoupling: 10µF bulk + 100nF per IC + 10nF for ESP32 each VDD        ││
│  │                                                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                                                                         ││
│  │                        +15V ISLAND                                      ││
│  │                        Area: ~15% (22cm²)                               ││
│  │                                                                         ││
│  │  Source: LMR51430 VOUT (if 15V config) or dedicated regulator           ││
│  │                                                                         ││
│  │  Loads:                                                                 ││
│  │  • Gate driver VCCI (UCC21550)                ~50mA quiescent           ││
│  │  • Op-amp positive rail                       ~5mA                      ││
│  │                                                                         ││
│  │  Decoupling: 10µF + 100nF at UCC21550                                   ││
│  │                                                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │           COPPER POUR (Not connected - thermal/fill)                   ││
│  │           Area: ~15%                                                   ││
│  │           Connected to GND via thermal vias for heat spreading          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Power Island Design Rules

| Rule | Requirement | Rationale |
|------|-------------|-----------|
| Island separation | ≥1.0mm | Prevent shorts, allow routing |
| Minimum island width | 3mm | Current capacity for 1oz copper |
| Via to power plane | Multiple vias from L1/L4 | Reduce via inductance |
| Decoupling placement | On L1, via direct to L3 | Minimize loop area |
| No islands under HV | Keep L3 as GND flood | Reduce coupling |

### 4.3 Power Distribution Path

```
                          POWER DISTRIBUTION TREE
                          
    [AC Input] ──→ [Bridge Rectifier] ──→ [DC Bus 170-340V]
                                              │
                                              ▼
                                     ┌────────────────┐
                                     │  LMR51430      │
                                     │  Buck Conv.    │
                                     │  (Vin: 340V)   │
                                     │  (Vout: 5V)    │
                                     └───────┬────────┘
                                             │ 5V, 2A max
                                             │
            ┌────────────────────────────────┼────────────────────────────────┐
            │                                │                                │
            ▼                                ▼                                ▼
    ┌───────────────┐               ┌───────────────┐               ┌───────────────┐
    │  UCC21550     │               │  XC6220 LDO   │               │  Fan Driver   │
    │  Gate Driver  │               │  (5V → 3.3V)  │               │  500mA        │
    │  VCCI         │               │  700mA        │               │               │
    └───────────────┘               └───────┬───────┘               └───────────────┘
                                            │ 3.3V, 700mA max
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │                       │                       │
                    ▼                       ▼                       ▼
            ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
            │  ESP32-S3     │       │  MAX31865     │       │  Safety ICs   │
            │  300mA peak   │       │  2mA          │       │  10mA         │
            └───────────────┘       └───────────────┘       └───────────────┘
```

### 4.4 Isolated Power (Bootstrap)

The high-side IGBT gate driver requires floating power supplies. These are NOT on L3 but implemented with bootstrap circuits on L1:

```
                    BOOTSTRAP SUPPLY (Per IGBT)
                    
    [5V from LMR51430] ──→ [Bootstrap Diode] ──→ [VBOOT_H or VBOOT_L]
                                │                        │
                                │                        │
                          [Cboot 1µF]              [To UCC21550]
                                │                   [VDD1 or VDD2]
                                │
                          [IGBT Source]
                          (Floating ref)
```

**Critical:** Bootstrap circuits are on L1 copper pours, NOT connected to L3 power islands.

## 5. Via Stitching Strategy

### 5.1 Ground Stitching

Via stitching connects ground plane (L2) to ground pours on L1 and L4 for EMI control.

| Zone | Via Pitch | Via Size | Purpose |
|------|-----------|----------|---------|
| Board perimeter | 10mm | 0.3mm drill | Edge EMI containment |
| Around switch node | 5mm | 0.5mm drill | HF noise containment |
| Under ESP32 | 3mm | 0.3mm drill | Digital noise containment |
| Around isolation barrier | 8mm | 0.3mm drill | Define barrier edge |

### 5.2 Power Via Placement

| Connection | Minimum Vias | Via Size | Pattern |
|------------|--------------|----------|---------|
| 5V plane to component | 2 per pad | 0.5mm | Adjacent |
| 3.3V plane to component | 2 per pad | 0.5mm | Adjacent |
| Decoupling cap to plane | 1 per pad | 0.3mm | Direct |
| Bulk cap to plane | 4 per terminal | 0.5mm | Array |

### 5.3 Via Stitching Pattern

```
PERIMETER STITCHING (Every 10mm around board edge)

    ●─────────●─────────●─────────●─────────●─────────●
    │                                                 │
    ●                                                 ●
    │                                                 │
    ●           [PCB Interior]                        ●
    │                                                 │
    ●                                                 ●
    │                                                 │
    ●─────────●─────────●─────────●─────────●─────────●
    
    ● = Ground stitching via (0.3mm drill)


SWITCH NODE CONTAINMENT (5mm pitch ring around switch node)

              ●───●───●───●───●
              │               │
              ●   ┌───────┐   ●
              │   │ SWITCH│   │
              ●   │ NODE  │   ●
              │   │ POUR  │   │
              ●   └───────┘   ●
              │               │
              ●───●───●───●───●
```

## 6. Copper Pour Strategy

### 6.1 Layer 1 (Top) Copper Pours

| Pour Name | Net | Area | Purpose |
|-----------|-----|------|---------|
| DC_BUS+ | DC_BUS+ | ~15cm² | High-current positive bus |
| DC_BUS- | DC_BUS- | ~15cm² | High-current negative bus |
| SWITCH_NODE | SWITCH_NODE | ~5cm² (minimize!) | IGBT output connection |
| GND_POUR_TOP | GND | Fill | EMI shielding, thermal |

### 6.2 Layer 4 (Bottom) Copper Pours

| Pour Name | Net | Area | Purpose |
|-----------|-----|------|---------|
| GND_POUR_BOT | GND | ~70% fill | Reference plane, shielding |
| GATE_H_POUR | GATE_H | ~2cm² | Gate drive to high-side IGBT |
| GATE_L_POUR | GATE_L | ~2cm² | Gate drive to low-side IGBT |

### 6.3 Pour Priority (KiCad)

| Priority | Net | Reason |
|----------|-----|--------|
| 1 (highest) | Specific power nets | Ensure connectivity |
| 2 | Signal traces | Don't get flooded |
| 3 (default) | GND | Fill remaining area |

### 6.4 Thermal Relief Settings

| Connection Type | Thermal Relief | Spoke Width | Gap |
|-----------------|----------------|-------------|-----|
| Signal via to GND | Yes | 0.3mm | 0.3mm |
| Power via to plane | No (solid) | N/A | N/A |
| Component pad to plane | Yes | 0.5mm | 0.3mm |
| IGBT thermal pad | No (solid) | N/A | N/A |

## 7. Verification Checklist

### 7.1 Ground Plane

- [ ] PGND and CGND connected only at star point
- [ ] Star point has 20+ vias
- [ ] No traces cross ground split except at star point
- [ ] ISOGND completely isolated (no galvanic connection)
- [ ] Via stitching ≤15mm pitch at perimeter
- [ ] Switch node containment ring complete

### 7.2 Power Plane

- [ ] 5V island covers all 5V loads
- [ ] 3.3V island covers all 3.3V loads
- [ ] Island separation ≥1.0mm
- [ ] Multiple vias at each power connection
- [ ] Decoupling caps have direct via to power plane
- [ ] No power islands under HV areas

### 7.3 Copper Pours

- [ ] DC bus pours sized for 22A (≥5mm width)
- [ ] Switch node area minimized
- [ ] Thermal relief appropriate for each connection
- [ ] No floating copper (all pours connected)
- [ ] Pour-to-trace clearance maintained

## 8. References

- PCB_SPECIFICATION.md - Layer stackup definition
- GROUNDING_EMI_STRATEGY.md - Ground architecture
- NET_CLASS_SPECIFICATION.md - Net class definitions
- HIGH_VOLTAGE_CLEARANCE_SPEC.md - Isolation requirements
- IPC-2221B - General PCB design guidelines
- UCC21550 Layout Guidelines - Gate driver specific

## 9. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-16 | AI Agent | Initial specification |
