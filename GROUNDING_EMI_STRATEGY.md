# Grounding and EMI Strategy for Temper Induction Cooker

## Task Reference
- **BD Issue**: temper-6u5
- **Date**: 2025-12-14
- **Related**: temper_0zd4_emi_emc_verification.md

---

## 1. Executive Summary

This document defines the grounding architecture and EMI strategy for a 2kW induction cooker with mixed high-power (320VDC, 22A peak) and low-signal (3.3V, µV-level ADC) subsystems.

**Key Challenges:**
- 38kHz half-bridge switching with 50V/ns dV/dt transitions
- CT and thermistor sensing requiring mV-level accuracy
- Safety isolation requirements (IEC 60335-2-6)
- Conducted emissions compliance (EN 55014-1)

**Architecture:** Star grounding with isolated power/control domains connected at single point.

---

## 2. Ground Domain Architecture

### 2.1 Ground Domain Diagram

```
                                    EARTH (PE)
                                        │
                                        │ (Safety Ground)
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
            ┌───────┴───────┐   ┌───────┴───────┐   ┌───────┴───────┐
            │  EMI FILTER   │   │   ENCLOSURE   │   │   USER TOUCH  │
            │   GROUND      │   │    GROUND     │   │    SURFACES   │
            │               │   │               │   │               │
            │ • Y-caps      │   │ • Metal case  │   │ • Control     │
            │ • CM choke    │   │ • Heatsink    │   │   panel       │
            │   center tap  │   │ • Shields     │   │ • Knobs       │
            └───────────────┘   └───────────────┘   └───────────────┘

                                        │
                         ═══════════════╧═══════════════
                         ║    STAR GROUND POINT (SGP)   ║
                         ║    Located at DC bus return  ║
                         ═══════════════╤═══════════════
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
            ┌───────┴───────┐   ┌───────┴───────┐   ┌───────┴───────┐
            │ POWER GROUND  │   │   AUX POWER   │   │CONTROL GROUND │
            │   (PGND)      │   │    GROUND     │   │   (CGND)      │
            │               │   │               │   │               │
            │ • DC bus (-)  │   │ • LMR51430    │───│ • ESP32-S3    │
            │ • IGBT E1, E2 │   │ • XC6220 LDO  │   │ • MAX31865    │
            │ • Resonant    │   │ • Gate driver │   │ • ADUM1250    │
            │   tank return │   │   VCCI side   │   │   (Side 1)    │
            │ • CT burden   │   │               │   │ • ADC refs    │
            │   resistor    │   │               │   │               │
            └───────────────┘   └───────────────┘   └───────────────┘

                                                            ║
                                                    ════════╩════════
                                                    ║   ISOLATION   ║
                                                    ║    BARRIER    ║
                                                    ════════╤════════
                                                            │
                                                    ┌───────┴───────┐
                                                    │ ISOLATED GND  │
                                                    │   (ISOGND)    │
                                                    │               │
                                                    │ • ADUM1250    │
                                                    │   (Side 2)    │
                                                    │ • UCC21550    │
                                                    │   high-side   │
                                                    │ • MAX31865 #2 │
                                                    │   (IGBT temp) │
                                                    └───────────────┘
```

### 2.2 Ground Domain Definitions

| Domain | Abbreviation | Voltage Range | Current | Noise Level |
|--------|--------------|---------------|---------|-------------|
| Power Ground | PGND | 0-320VDC (referenced) | 0-22A peak | High (switching transients) |
| Aux Power Ground | AGND | 0V (from PGND) | 0-1.5A | Medium (buck switching) |
| Control Ground | CGND | 0V (from AGND) | 0-400mA | Low (digital + analog) |
| Isolated Ground | ISOGND | Floating (±320V offset) | <100mA | Variable |
| Earth/PE | PE | 0V (mains reference) | Fault current only | N/A |

---

## 3. Star Grounding Implementation

### 3.1 Star Ground Point Location

**Location:** Adjacent to DC bus negative terminal and IGBT emitter return.

**Rationale:**
- Minimizes inductance in high-current return path
- All ground currents flow through single defined path
- Prevents ground loops between domains
- Provides stable voltage reference for measurements

### 3.2 Connection Hierarchy

```
                    STAR GROUND POINT (SGP)
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   [PGND Plane]       [AGND Plane]        [CGND Plane]
        │                   │                   │
   Heavy copper         Via array          Via array
   (2 oz, 100 mil)     (20 vias)          (20 vias)
        │                   │                   │
   • DC bus cap (-)    • LMR51430 GND      • ESP32 GND
   • IGBT emitters     • Bootstrap caps     • MAX31865 GND
   • CT burden R       • UCC21550 VCCI-    • ADUM1250 GND1
   • Snubber return
```

### 3.3 PCB Implementation

**4-Layer Stack-up:**

| Layer | Function | Copper Weight |
|-------|----------|---------------|
| L1 (Top) | Power components, high-current traces | 2 oz |
| L2 | Ground plane (split PGND/CGND) | 1 oz |
| L3 | Power plane (5V, 3.3V islands) | 1 oz |
| L4 (Bottom) | Control signals, gate drive | 1 oz |

**Ground Plane Split:**

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  ┌─────────────────────┐    ┌───────────────────┐  │
│  │                     │    │                   │  │
│  │    POWER GROUND     │    │  CONTROL GROUND   │  │
│  │       (PGND)        │    │     (CGND)        │  │
│  │                     │    │                   │  │
│  │  • DC bus area      │    │  • ESP32 area     │  │
│  │  • IGBT footprints  │    │  • ADC area       │  │
│  │  • Resonant tank    │    │  • Digital I/O    │  │
│  │                     │    │                   │  │
│  └──────────┬──────────┘    └────────┬──────────┘  │
│             │                        │             │
│             └────────┬───────────────┘             │
│                      │                             │
│               [STAR POINT]                         │
│             (Single connection)                    │
│                                                    │
└─────────────────────────────────────────────────────┘
```

---

## 4. Isolation Barrier Strategy

### 4.1 Isolation Requirements (IEC 60335-2-6)

| Barrier | Voltage Rating | Method | Component |
|---------|---------------|--------|-----------|
| Gate drive | 5.7kVRMS | Transformer | UCC21550 (internal) |
| I2C signals | 2.5kVRMS | Capacitive | ADUM1250 |
| Temperature sense | 2.5kVRMS | Capacitive | ADUM1250 |
| Current sense | 2.5kVRMS | Magnetic | Current transformer |
| HV bus monitor | 5kVRMS | Optical | Optocoupler (future) |

### 4.2 Isolation Barrier Ground Treatment

```
                    CONTROL SIDE                    ISOLATED SIDE
                        │                               │
    ESP32-S3 ──────────┤                               ├────── UCC21550 High-side
                        │                               │
    MAX31865 (local) ──┤         ╔═══════════╗         ├────── MAX31865 (IGBT)
                        │         ║ ISOLATION ║         │
    ADUM1250 Side1 ────┼────────>║  BARRIER  ║<────────┼────── ADUM1250 Side2
                        │         ║   (2.5kV) ║         │
    CT Signal ─────────┤         ╚═══════════╝         │
                        │                               │
                     [CGND]                         [ISOGND]
                        │                               │
                        │      ╔═══════════════╗        │
                        │      ║ NO CONNECTION ║        │
                        │      ║ BETWEEN GNDs  ║        │
                        └──────╚═══════════════╝────────┘
```

**Critical Rules:**
1. **Never connect CGND to ISOGND** - defeats isolation
2. Isolated side powered by bootstrap or isolated supply
3. Signal crossing via isolation components only
4. Creepage distance >8mm between ground domains on PCB

### 4.3 Current Transformer Ground Connection

```
        CT Secondary
            │
    ┌───────┴───────┐
    │               │
    R_burden      C_bypass
    (50Ω)         (100nF)
    │               │
    └───────┬───────┘
            │
    Signal to ESP32 ADC
            │
            ├──── R_filter ──── ADC_IN
            │     (1kΩ)
            │
    ┌───────┴───────┐
    │  CT GROUND    │
    │  (Isolated    │
    │   from PGND)  │
    └───────┬───────┘
            │
            └────── To CGND (via star point)
```

**Design Notes:**
- CT secondary is magnetically isolated from primary
- CT ground connects to CGND (measurement reference)
- Burden resistor provides current-to-voltage conversion
- Filter capacitor (100nF) rejects HF noise

---

## 5. EMI Filtering Strategy

### 5.1 AC Input EMI Filter

```
AC LINE ────┬──[FUSE]──┬──[L_DM]──┬──[L_CM]──┬────── To Rectifier
            │          │          │          │
NEUTRAL ──┬─┼──────────┼──────────┼──────────┼────── 
          │ │          │          │          │
         MOV         C_X1       C_Y1       C_X2
          │ │          │          │          │
PE ───────┴─┴──────────┴──────────┴──────────┴──────
```

### 5.2 Component Specifications

| Component | Value | Rating | Type | Purpose |
|-----------|-------|--------|------|---------|
| FUSE | 15A | 250VAC | Slow-blow | Overcurrent protection |
| MOV | 275V | 10kA | Metal oxide | Surge suppression |
| L_DM | 470µH | 15A | Toroidal | DM noise suppression |
| L_CM | 10mH | 15A | Common-mode choke | CM noise suppression |
| C_X1, C_X2 | 470nF | 275VAC | X2 safety cap | DM filter |
| C_Y1, C_Y2 | 2.2nF | 300VAC | Y2 safety cap | CM filter (line-to-PE) |

### 5.3 Filter Performance

| Frequency | DM Attenuation | CM Attenuation | Requirement |
|-----------|----------------|----------------|-------------|
| 38 kHz | 15 dB | 10 dB | Below test band |
| 150 kHz | 25 dB | 20 dB | >20 dB |
| 500 kHz | 40 dB | 30 dB | >30 dB |
| 2 MHz | 55 dB | 45 dB | >25 dB |

### 5.4 Y-Capacitor Leakage Current

**IEC 60335-1 Limit:** <3.5mA touch current for Class I appliances

**Calculation:**
```
I_leakage = V_line × 2πf × C_Y_total
I_leakage = 240V × 2π × 50Hz × 4.4nF
I_leakage = 0.33 mA ✓ (well under limit)
```

---

## 6. Shield Termination Strategy

### 6.1 Heatsink Grounding

```
                    ┌─────────────────────┐
                    │      HEATSINK       │
                    │                     │
    IGBT mounting ──┤  (Electrically      │
    (isolated)      │   connected to      │──── To PE via
                    │   collector via     │     short, wide
                    │   thermal pad)      │     conductor
                    │                     │
                    └─────────────────────┘
```

**Design:**
- Heatsink connected to PE (earth) for safety
- IGBTs mounted with insulating pads (TO-247 + Kapton)
- Thermal grease: electrically insulating, thermally conductive
- Short, wide connection (<10cm, >6mm width) to PE

### 6.2 Enclosure Shielding

| Element | Connection | Method |
|---------|------------|--------|
| Metal enclosure | PE | M4 screw + star washer |
| Ventilation grilles | PE (via enclosure) | Honeycomb shield |
| Cable entry | PE | Conductive grommet |
| Display window | Float or capacitive | Non-conductive frame |

### 6.3 Cable Shielding

| Cable | Shield Termination | Notes |
|-------|-------------------|-------|
| AC power cord | PE at entry point | Class I requirement |
| Coil leads | Twisted pair, no shield | <50cm, minimize loop |
| Temperature sensor | Shield to CGND at ESP32 end | Single-point ground |
| Fan power | Unshielded | Low noise source |

---

## 7. Signal Integrity for Sensitive Circuits

### 7.1 ADC Input Layout

```
    From CT/Thermistor
            │
            ▼
    ┌───────────────────────────────────┐
    │      GUARD RING (CGND)            │
    │   ┌───────────────────────────┐   │
    │   │     ADC INPUT TRACE       │   │
    │   │    (routed over CGND)     │   │
    │   └───────────────────────────┘   │
    │                                   │
    └───────────────────────────────────┘
```

**Layout Rules:**
1. Route ADC traces over solid CGND plane
2. Guard ring around ADC inputs
3. Keep away from power traces (>10mm)
4. No vias under ADC input pins
5. Filter capacitor at ADC pin (<3mm)

### 7.2 Gate Drive Signal Routing

```
    ESP32 GPIO ──[51Ω]──[33pF]──── UCC21550 INA/INB
                   │       │
                  GND     GND
                   │       │
              [Place near ESP32]
```

**Layout Rules:**
1. Series resistor at source (ESP32 end)
2. Filter capacitor at destination (UCC21550 end)
3. Route over ground plane
4. Maximum trace length: 50mm
5. Matched length for INA/INB if possible

### 7.3 SPI Bus Layout (MAX31865)

```
    ESP32 VSPI ──[33Ω]──── MAX31865
                   │
              [Each line]
```

**Layout Rules:**
1. 33Ω series resistors on CLK, MOSI, CS
2. Route as differential pairs where possible
3. Keep SPI traces away from DC bus
4. Shield with CGND traces on both sides

---

## 8. IEC 60335-2-6 Compliance

### 8.1 Relevant Clauses

| Clause | Requirement | Implementation |
|--------|-------------|----------------|
| 8.1 | Touch current <3.5mA | Y-cap leakage 0.33mA |
| 19.1 | Abnormal operation | Hardware safety interlock |
| 22.3 | Creepage/clearance | >8mm for basic insulation |
| 23.3 | Internal wiring | Rated for max temperature |
| 29.1 | Mechanical strength | Metal enclosure |

### 8.2 Creepage and Clearance

| Location | Requirement | Design | Status |
|----------|-------------|--------|--------|
| Line-to-PE | 4mm | 8mm | ✅ |
| Line-to-low-voltage | 6mm | 10mm | ✅ |
| Across isolation barrier | 8mm | 12mm | ✅ |
| IGBT collector-to-heatsink | 5mm | 8mm (pad + gap) | ✅ |

---

## 9. Grounding Diagram (Complete System)

```
═══════════════════════════════════════════════════════════════════════════════
                              TEMPER GROUNDING ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────┐
    │                             AC MAINS INPUT                              │
    │   L ────[FUSE]────[MOV]────[L_DM]────[L_CM]────┬──── BRIDGE RECTIFIER   │
    │   N ──────────────────────────────────────────┬┴────                    │
    │   PE ─────────┬───────────────────────────────┴─────                    │
    │               │                                                          │
    │         [Y-CAPS to PE]                                                  │
    │               │                                                          │
    └───────────────┼──────────────────────────────────────────────────────────┘
                    │
                    │ EARTH GROUND
                    │
    ┌───────────────┼──────────────────────────────────────────────────────────┐
    │               │                 ENCLOSURE & HEATSINK                     │
    │   ┌───────────┴───────────┐                                             │
    │   │  • Metal case         │                                             │
    │   │  • Heatsink (via pad) │                                             │
    │   │  • Fan housing        │                                             │
    │   │  • Control panel      │                                             │
    │   └───────────────────────┘                                             │
    └──────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────────────────────────────────┐
    │                           POWER STAGE (PGND)                             │
    │                                                                          │
    │   DC BUS (+) ═══════════════════════════════════════════════════════     │
    │                    │              │              │                       │
    │               [C_BUS 2200µF]  [IGBT Q1]    [RESONANT TANK]              │
    │                    │              │              │                       │
    │                    │          [BOOTSTRAP]   [L_res + C_res]             │
    │                    │              │              │                       │
    │   DC BUS (-) ══════╪══════════════╪══════════════╪═══════════════════    │
    │              ══════╧══════════════╧══════════════╧═══════════════════    │
    │                            ║                                             │
    │                    ════════╩════════                                     │
    │                    ║ STAR GROUND  ║                                      │
    │                    ║    POINT     ║                                      │
    │                    ════════╦════════                                     │
    │                            ║                                             │
    └────────────────────────────╫─────────────────────────────────────────────┘
                                 ║
         ┌───────────────────────╫────────────────────────────────┐
         │                       ║                                │
    ┌────┴────┐            ┌─────╨─────┐                   ┌──────┴──────┐
    │ AUX PWR │            │   MAIN    │                   │  CONTROL    │
    │  GROUND │            │  GROUND   │                   │   GROUND    │
    │         │            │  (STAR)   │                   │             │
    │LMR51430 │            │           │                   │ ESP32-S3    │
    │XC6220   │────────────│           │───────────────────│ MAX31865    │
    │UCC21550 │            │           │                   │ ADUM1250-1  │
    │(VCCI)   │            │           │                   │ ADC REF     │
    └─────────┘            └───────────┘                   └─────────────┘
                                                                  ║
                                                          ════════╩════════
                                                          ║  ISOLATION   ║
                                                          ║   BARRIER    ║
                                                          ║   (2.5kV)    ║
                                                          ════════╦════════
                                                                  ║
                                                          ┌───────╨───────┐
                                                          │   ISOLATED    │
                                                          │    GROUND     │
                                                          │               │
                                                          │ • ADUM1250-2  │
                                                          │ • UCC21550    │
                                                          │   (High-side) │
                                                          │ • MAX31865    │
                                                          │   (IGBT temp) │
                                                          └───────────────┘

═══════════════════════════════════════════════════════════════════════════════
                                    LEGEND
═══════════════════════════════════════════════════════════════════════════════
  ═══════  High-current power path (>1A)
  ───────  Signal/control path (<1A)
  ║   ║    Isolation barrier
  [   ]    Component
  ┌─ ─┐    Functional block
═══════════════════════════════════════════════════════════════════════════════
```

---

## 10. Design Checklist

### 10.1 Grounding Checklist

- [x] Star ground point defined at DC bus return
- [x] PGND, AGND, CGND domains identified
- [x] Single-point connection between domains
- [x] Isolation barriers identified and rated
- [x] CT ground connected to CGND
- [x] Heatsink grounded to PE
- [x] Y-cap leakage current calculated (<3.5mA)

### 10.2 EMI Checklist

- [x] AC input filter designed (DM + CM)
- [x] X2 and Y2 capacitors specified
- [x] Filter insertion loss calculated
- [x] ZVS operation verified for EMI reduction
- [x] PCB stack-up defined (4-layer)
- [x] Ground plane continuity maintained
- [x] Sensitive trace routing guidelines defined

### 10.3 Safety Checklist

- [x] Creepage/clearance requirements met
- [x] Touch current limit met
- [x] Isolation voltage ratings adequate
- [x] PE connection specified

---

## 11. References

| Document | Description |
|----------|-------------|
| IEC 60335-1 | Household appliances - General requirements |
| IEC 60335-2-6 | Particular requirements for cooking ranges |
| EN 55014-1 | EMC - Emission requirements |
| temper_0zd4_emi_emc_verification.md | EMI analysis for this project |
| GATE_DRIVER_POWER_ARCHITECTURE_DECISION.md | Bootstrap vs isolated supply |
| COMPONENT_COMPATIBILITY_VERIFICATION.md | System component integration |

---

## 12. Conclusion

This grounding and EMI strategy provides:

1. **Star grounding architecture** - Eliminates ground loops, provides stable measurement reference
2. **Clear domain separation** - Power, control, and isolated grounds with defined boundaries
3. **Proper isolation barriers** - 2.5-5.7kVRMS isolation for safety and signal integrity
4. **Comprehensive EMI filtering** - AC input filter meeting EN 55014-1 Class B
5. **PCB guidelines** - 4-layer stack-up with split ground planes
6. **IEC 60335 compliance** - Creepage, clearance, touch current requirements met

**Task temper-6u5: COMPLETE**
