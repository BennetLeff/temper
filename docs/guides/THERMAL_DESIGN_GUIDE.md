# Thermal Design Guide - Temper Induction Cooker

## Document Information

**Version:** 1.0  
**Date:** December 13, 2025  
**Status:** DESIGN COMPLETE

---

## 1. Executive Summary

This document consolidates thermal analysis for the Temper induction cooker operating at 1.8kW on 120VAC input.

### Heat Budget

| Component | Loss (W) | Cooling Method |
|-----------|----------|----------------|
| IGBTs (×2) | 36 | Heatsink + fan |
| Induction coil | 50 | Shared airflow |
| LMR51430 buck | 1-2 | PCB copper |
| Control electronics | <1 | Natural convection |
| **Total** | **~89W** | **Forced air** |

### Thermal Solution

**Configuration:** Compact heatsink with low-speed 80mm fan

| Parameter | Specification |
|-----------|---------------|
| Heatsink | 120×100×40mm extruded aluminum |
| Fan | 80mm, 1000-1500 RPM, ~20 dBA |
| TIM | Graphite pad (Panasonic EYG-S091210) |
| Airflow | Serial: Heatsink → Coil → Exhaust |

---

## 2. Operating Conditions

### 2.1 Electrical Parameters (120V System)

| Parameter | Value | Notes |
|-----------|-------|-------|
| AC Input | 120V RMS, 60Hz | US mains |
| DC Bus | 170V | Peak rectified |
| Output Power | 1.8 kW max | 15A outlet limit |
| Switching Frequency | 40 kHz | Above resonance (37.5k) |
| Tank Current (RMS) | 15.0A | At 1.8kW |
| Tank Current (peak) | 21A | |

### 2.2 Ambient Conditions

| Condition | Temperature | Use Case |
|-----------|-------------|----------|
| Nominal | 25-40°C | Normal kitchen |
| Hot kitchen | 40-60°C | Near oven/stove |
| Worst case design | 60°C | Design limit |

---

## 3. Component Thermal Analysis

### 3.1 IGBT Power Stage (IKW40N120H3)

**Source:** sim_30_thermal_verification.md

#### Loss Breakdown (ZVS operation, 170V bus)

| Loss Type | Per IGBT | Both IGBTs |
|-----------|----------|------------|
| Conduction | 12W | 24W |
| Switching (ZVS) | 4W | 8W |
| Diode | 4W | 8W |
| **Total** | **20W** | **40W** |

Note: Losses lower at 170V vs 320V bus due to:
- Lower voltage stress during switching
- ZVS nearly eliminates turn-on loss

#### Thermal Path

```
Junction → Case → TIM → Heatsink → Air
  Rth_jc    Rth_cs   Rth_sa
  0.50      0.20     0.45 (with fan)
```

#### Temperature Calculation

```
P_total = 40W (both IGBTs)
Rth_total = 0.50 + 0.20 + 0.45 = 1.15 K/W (per device, 20W each)

At 60°C ambient:
Tj = Ta + P × Rth = 60 + 20 × 1.15 = 83°C

Margin: 150 - 83 = 67°C ✓
```

### 3.2 Induction Coil

**Source:** sim_31_coil_thermal_analysis.md

#### Loss Calculation

| Parameter | Value |
|-----------|-------|
| Effective inductance | 60 µH |
| DC resistance | 100 mΩ |
| AC/DC ratio (38kHz) | 1.8 |
| AC resistance (80°C) | 220 mΩ |
| RMS current (2kW) | 15.8A |
| **Power loss** | **55W** |

#### Thermal Path

```
Coil windings → Air gap → Ambient
     Rth_coil-air
     ~1.0 K/W (with forced air)
```

#### Temperature Calculation

```
P_coil = 55W
Rth = 1.0 K/W (forced air across coil)

At 60°C ambient:
T_coil = 60 + 55 × 1.0 = 115°C

Margin to Class B insulation (130°C): 15°C ✓
```

### 3.3 Auxiliary Power (LMR51430)

**Source:** sim_02_lmr51430_load_verification.md

| Parameter | Value |
|-----------|-------|
| Input | 170V DC |
| Output | 5V @ 0.5A |
| Efficiency | ~85% |
| Loss | ~0.5W |
| Thermal | PCB dissipation adequate |

---

## 4. Cooling System Design

### 4.1 Heatsink Selection

**Requirements:**
- Thermal resistance: ≤0.5 K/W with airflow
- Mounting: TO-247 compatible (2 positions)
- Footprint: ≤150×120mm (hot-plate constraint)

**Recommended Options:**

| Option | Size (mm) | Rth_sa | Cost | Notes |
|--------|-----------|--------|------|-------|
| Generic extruded | 120×100×40 | 0.45 K/W | $8-12 | Good balance |
| Fischer SK 89 | 100×88×35 | 0.40 K/W | $15-20 | High quality |
| CPU cooler (repurposed) | varies | 0.3-0.5 | $0-10 | If available |

### 4.2 Fan Selection

**Requirements:**
- Low noise: <25 dBA
- Adequate airflow: >20 CFM
- Size: 80mm (fits enclosure)
- Voltage: 12V DC (from aux supply)

**Recommended:**

| Option | Speed | Airflow | Noise | Notes |
|--------|-------|---------|-------|-------|
| Noctua NF-R8 | 1800 RPM | 31 CFM | 17 dBA | Premium, quiet |
| Arctic F8 | 2000 RPM | 28 CFM | 22 dBA | Good value |
| Generic 80mm | 1500 RPM | 25 CFM | 20 dBA | Budget |

**PWM control (optional):**
- Reduce speed at low power levels
- Thermistor-controlled via simple circuit
- Not required for first prototype

### 4.3 Thermal Interface Material

| Type | Rth | Cost | Notes |
|------|-----|------|-------|
| Thermal paste | 0.15-0.25 K/W | $5 | Standard, messy |
| Graphite pad | 0.10-0.20 K/W | $8 | Clean, reusable |
| Phase-change | 0.10-0.15 K/W | $10 | Best performance |

**Recommendation:** Thermal paste for prototype, graphite pad for production.

---

## 5. Airflow Design

### 5.1 Airflow Path

```
       INTAKE                          EXHAUST
          │                               │
          ▼                               │
    ┌─────────────────────────────────────┴───┐
    │                                         │
    │   ┌───────────┐         ┌───────────┐  │
    │   │   FAN     │         │           │  │
    │   │  80mm     │────────▶│   COIL    │──┼──▶
    │   │           │    │    │   AREA    │  │
    │   └───────────┘    │    └───────────┘  │
    │         │          │                   │
    │         ▼          │                   │
    │   ┌───────────┐    │                   │
    │   │ HEATSINK  │────┘                   │
    │   │  (IGBTs)  │                        │
    │   └───────────┘                        │
    │                                        │
    │   [Control PCB - below/beside]         │
    │                                        │
    └────────────────────────────────────────┘
```

### 5.2 Key Principles

1. **Cool air to heatsink first** - Most critical component gets coolest air
2. **Serial flow** - All heat sources in airflow path
3. **Positive pressure** - Fan pushes air in, prevents dust ingress
4. **Adequate exhaust area** - ≥2× intake area to prevent backpressure

### 5.3 Airflow Obstacles

Avoid blocking airflow with:
- Capacitors (place beside, not in path)
- Wiring harnesses (route around perimeter)
- EMI shields (use perforated if in path)

---

## 6. Thermal Protection

### 6.1 NTC Thermistor Placement

| Location | Purpose | Trip Point |
|----------|---------|------------|
| Heatsink | IGBT protection | 85°C |
| Coil area | Coil protection | 95°C |
| Enclosure | Ambient monitor | 70°C |

### 6.2 Protection Response

```
T_heatsink > 85°C  →  Reduce power to 50%
T_heatsink > 95°C  →  Shutdown, fault LED
T_coil > 95°C      →  Shutdown, fault LED
T_enclosure > 70°C →  Warning (fan speed up if PWM)
```

### 6.3 Thermal Fuse (Backup)

- Location: On heatsink, near IGBT
- Rating: 125°C or 130°C
- Type: One-shot, requires replacement
- Purpose: Backup if NTC/software fails

---

## 7. Bill of Materials (Thermal)

### 7.1 Required Components

| Item | Qty | Specification | Est. Cost |
|------|-----|---------------|-----------|
| Heatsink | 1 | 120×100×40mm, Al extrusion | $10 |
| Fan | 1 | 80mm, 12V, <25dBA | $8 |
| Thermal paste | 1 | Arctic MX-4 or equivalent | $5 |
| NTC thermistor | 2 | 10kΩ @ 25°C, -40 to +125°C | $2 |
| Thermal fuse | 1 | 125°C, 2A | $1 |
| Mounting hardware | 1 set | M3 screws, TO-247 insulators | $3 |
| **Total** | | | **~$29** |

### 7.2 Optional Upgrades

| Item | Benefit | Cost |
|------|---------|------|
| Noctua fan | Quieter (17 vs 22 dBA) | +$7 |
| Graphite TIM | Cleaner assembly | +$3 |
| Larger heatsink | More margin, slower fan | +$5 |
| PWM fan control | Variable speed | +$2 |

---

## 8. Thermal Budget Summary

### At 60°C Ambient, 2kW Output

| Component | Loss | T_operating | T_max | Margin |
|-----------|------|-------------|-------|--------|
| IGBT junction | 40W | 83°C | 150°C | 67°C ✓ |
| Coil | 55W | 115°C | 130°C | 15°C ✓ |
| LMR51430 | 0.5W | 75°C | 150°C | 75°C ✓ |

### System Efficiency

```
P_output = 1800W
P_loss = 36 + 50 + 0.5 = 86.5W
P_input = 1886.5W

Efficiency = 1800 / 1886.5 = 95.4%
```

---

## 9. Design Verification Checklist

- [x] IGBT thermal analysis (sim_30)
- [x] Coil thermal analysis (sim_31)
- [x] Heatsink sizing
- [x] Fan selection
- [x] Airflow path design
- [x] NTC placement defined
- [x] Thermal protection thresholds
- [x] BOM created

---

## 10. References

| Document | Description |
|----------|-------------|
| sim_30_thermal_verification.md | IGBT thermal analysis |
| sim_31_coil_thermal_analysis.md | Coil thermal analysis |
| IKW40N120H3 datasheet | IGBT thermal specs |
| RESONANT_TANK_DESIGN.md | ZVS loss estimates |

---

**END OF DOCUMENT**
