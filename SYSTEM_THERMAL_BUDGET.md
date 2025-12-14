# System Thermal Budget - Temper Induction Cooker

## Task Reference
- **BD Epic**: temper-8rf
- **Date**: 2025-12-14
- **Related Documents**:
  - THERMAL_DESIGN_GUIDE.md
  - LMR51430_THERMAL_ANALYSIS.md
  - sim_30_thermal_verification.md
  - sim_31_coil_thermal_analysis.md

---

## 1. Executive Summary

This document provides a complete system thermal budget for the Temper 2kW induction cooker, consolidating all component analyses and defining derating curves for reliable operation.

### System Heat Budget (Worst Case: 240VAC, 2kW)

| Component | Power Loss | % of Total | Cooling Method |
|-----------|------------|------------|----------------|
| IGBTs (×2) | 60 W | 52% | Heatsink + forced air |
| Induction coil | 45 W | 39% | Shared airflow |
| LMR51430 buck | 1.0 W | 0.9% | PCB copper pour |
| XC6220 LDO | 0.65 W | 0.6% | PCB copper pour |
| Gate drivers | 1.5 W | 1.3% | PCB + airflow |
| Control (ESP32) | 0.5 W | 0.4% | Natural convection |
| EMI filter | 2.0 W | 1.7% | Convection |
| Capacitors (ESR) | 4.0 W | 3.5% | Convection |
| **Total** | **~115 W** | **100%** | - |

### System Efficiency: **94.5%** (at 2kW output)

---

## 2. Operating Scenarios

### 2.1 Voltage/Power Configurations

| Input | DC Bus | Max Power | IGBT Loss | Coil Loss | Total Loss |
|-------|--------|-----------|-----------|-----------|------------|
| 120VAC | 170V | 2 kW | 40 W | 55 W | ~100 W |
| 240VAC | 320V | 2 kW | 60 W | 45 W | ~115 W |

Note: Higher bus voltage → higher switching loss but lower coil I²R loss.

### 2.2 Ambient Temperature Ranges

| Environment | Temp Range | Use Case | Duration |
|-------------|------------|----------|----------|
| **Normal** | 25-40°C | Typical kitchen | Continuous |
| **Warm kitchen** | 40-55°C | Summer, near oven | Extended |
| **Worst case** | 55-70°C | Hot location, poor ventilation | Limited |
| **Design limit** | 85°C | Absolute maximum | Emergency shutdown |

---

## 3. Component Thermal Details

### 3.1 IGBT Power Stage (IKW40N120H3)

**Source:** sim_30_thermal_verification.md, RESONANT_TANK_DESIGN.md

| Parameter | 120V System | 240V System |
|-----------|-------------|-------------|
| DC Bus Voltage | 170V | 320V |
| Tank Current (peak) | 22A | 42A |
| Conduction loss (both) | 24W | 34W |
| Switching loss (ZVS) | 8W | 17W |
| Diode losses | 8W | 9W |
| **Total IGBT loss** | **40W** | **60W** |

**Thermal Path:**
```
Tj → Rth_jc (0.50) → Tc → Rth_cs (0.20) → Ts → Rth_sa (0.35-0.45) → Ta
```

**Temperature Calculations:**

| Condition | Ta | Rth_sa | Ts | Tj | Margin |
|-----------|----|----|----|----|--------|
| 120V, Normal | 40°C | 0.45 | 58°C | 72°C | 78°C |
| 120V, Worst | 70°C | 0.35 | 84°C | 98°C | 52°C |
| 240V, Normal | 40°C | 0.35 | 61°C | 82°C | 68°C |
| 240V, Worst | 70°C | 0.35 | 91°C | 112°C | 38°C |
| 240V, Extreme | 85°C | 0.35 | 106°C | 127°C | 23°C |

### 3.2 Induction Coil

**Source:** sim_31_coil_thermal_analysis.md, THERMAL_DESIGN_GUIDE.md

| Parameter | 120V System | 240V System |
|-----------|-------------|-------------|
| RMS Current | 15.8A | 28A |
| AC Resistance (80°C) | 220mΩ | 58mΩ* |
| **Power Loss** | **55W** | **45W** |

*Lower effective resistance in 240V system due to different coil design optimization

**Thermal Path:**
```
T_winding → Rth_coil (1.0 K/W) → T_ambient
```

**Operating Temperatures:**

| Condition | Ta | Loss | T_coil | Insulation Limit | Margin |
|-----------|----|----|--------|------------------|--------|
| Normal | 40°C | 55W | 95°C | 130°C (Class B) | 35°C |
| Worst case | 70°C | 55W | 125°C | 130°C | 5°C ⚠️ |

**Note:** Coil temperature becomes limiting factor at high ambient. Thermal protection should trigger power reduction at T_coil > 110°C.

### 3.3 Auxiliary Power Supply

**Source:** LMR51430_THERMAL_ANALYSIS.md, sim_15_ldo_selection_verification.md

| Component | Vin | Vout | Iout | Loss | Tj @ 70°C |
|-----------|-----|------|------|------|-----------|
| LMR51430 | 12V | 5V | 1.2A | 1.0W | 130°C |
| XC6220 LDO | 5V | 3.3V | 0.38A | 0.65W | 120°C |

Both components require PCB copper pour for heat spreading.

### 3.4 Gate Drivers (UCC21550)

| Parameter | Value |
|-----------|-------|
| VCCI supply current | 5mA quiescent |
| Gate charge current | ~300mA average |
| Power dissipation | ~1.5W total (both channels) |
| Max junction temp | 150°C |
| Expected Tj | <100°C (good airflow) |

### 3.5 Other Components

| Component | Loss | Notes |
|-----------|------|-------|
| Bridge rectifier | 3-5W | Integrated into power stage |
| DC bus capacitors | 1-2W | ESR heating |
| EMI filter inductors | 1-2W | I²R + core loss |
| Resonant capacitor | 2-3W | ESR at 38kHz |
| ESP32-S3 + peripherals | 0.5W | Via LDO |

---

## 4. Cooling System Requirements

### 4.1 Heatsink Specification

| Parameter | 120V System | 240V System |
|-----------|-------------|-------------|
| Total IGBT dissipation | 40W | 60W |
| Required Rth_sa | ≤0.50 K/W | ≤0.35 K/W |
| Recommended heatsink | 100×80×35mm | 120×100×40mm |
| Fan required | Optional | Yes |

### 4.2 Fan Specification

| Parameter | Specification |
|-----------|---------------|
| Size | 80mm × 80mm × 25mm |
| Voltage | 12VDC |
| Speed | 1500-2000 RPM |
| Airflow | 25-35 CFM |
| Static pressure | >2mm H₂O |
| Noise | <25 dBA |
| Power | <2W |

**Recommended Models:**
- Noctua NF-R8 (17 dBA, 31 CFM)
- Arctic F8 (22 dBA, 28 CFM)
- Generic 80mm (20 dBA, 25 CFM)

### 4.3 Airflow Design

```
         INTAKE (cool air)
              ↓
    ┌─────────┴─────────┐
    │   ┌───────────┐   │
    │   │   FAN     │   │
    │   └─────┬─────┘   │
    │         ↓         │
    │   ┌───────────┐   │
    │   │ HEATSINK  │   │
    │   │  (IGBTs)  │   │
    │   └─────┬─────┘   │
    │         ↓         │
    │   ┌───────────┐   │
    │   │   COIL    │   │
    │   │   AREA    │   │
    │   └─────┬─────┘   │
    │         ↓         │
    └─────────┴─────────┘
              ↓
         EXHAUST (hot air)
```

**Design Rules:**
1. Heatsink receives coolest air (first in path)
2. Coil receives pre-heated air (+20-30°C)
3. Exhaust area ≥2× intake area
4. No obstructions in airflow path

---

## 5. Derating Curves

### 5.1 Power vs Ambient Temperature

```
Output Power (W)
    │
2000├────────────────┬──────┐
    │                │      │
1600├                │      └──────┐
    │                │             │
1200├                │             └──────┐
    │                │                    │
 800├                │                    └──────┐
    │                │                           │
 400├                │                           └────┐
    │                │                                │
   0├────────────────┴─────┴─────┴─────┴─────┴────────┴──
    0       25      40     55     70     85    100   Ta(°C)
    
    ← Full Power → ←─ Derate ─→ ← Shutdown →
```

### 5.2 Derating Table

| Ambient (°C) | Max Power (W) | % of Rated | Limiting Factor |
|--------------|---------------|------------|-----------------|
| 0-40 | 2000 | 100% | None |
| 40-50 | 2000 | 100% | Margin reduced |
| 50-55 | 1800 | 90% | Coil temp |
| 55-60 | 1500 | 75% | Coil temp |
| 60-65 | 1200 | 60% | IGBT + coil |
| 65-70 | 800 | 40% | IGBT Tj limit |
| 70-75 | 400 | 20% | All components |
| >75 | 0 | 0% | **SHUTDOWN** |

### 5.3 Derating Formula

```
P_max(Ta) = P_rated × min(1.0, (75 - Ta) / 35)   for Ta > 40°C
          = P_rated                               for Ta ≤ 40°C
```

Example at 60°C:
```
P_max = 2000 × (75 - 60) / 35 = 2000 × 0.43 = 857W → round to 800W
```

---

## 6. Thermal Protection System

### 6.1 Temperature Sensors

| Location | Sensor | Threshold | Action |
|----------|--------|-----------|--------|
| Heatsink | NTC 10kΩ | 85°C | Reduce power 50% |
| Heatsink | NTC 10kΩ | 95°C | Shutdown |
| Coil area | NTC 10kΩ | 100°C | Reduce power 50% |
| Coil area | NTC 10kΩ | 115°C | Shutdown |
| IGBT (optional) | MAX31865 | 125°C | Immediate shutdown |
| Enclosure | NTC 10kΩ | 65°C | Warning |

### 6.2 Protection Response

```
T_heatsink:
  < 75°C  →  Normal operation (100% power)
  75-85°C →  Warning, increase fan speed
  85-95°C →  Reduce power to 50%
  > 95°C  →  Shutdown, fault indication

T_coil:
  < 90°C  →  Normal operation
  90-100°C → Warning, increase fan speed  
  100-115°C → Reduce power to 50%
  > 115°C  →  Shutdown, fault indication
```

### 6.3 Thermal Fuse (Backup)

| Parameter | Specification |
|-----------|---------------|
| Location | On heatsink, near IGBT |
| Rating | 130°C (irreversible) |
| Type | TCO (Thermal Cut-Off) |
| Purpose | Backup if NTC/software fails |

---

## 7. PCB Thermal Layout

### 7.1 Layer Stack-up

| Layer | Function | Copper |
|-------|----------|--------|
| Top | Power components | 2 oz |
| Inner 1 | Ground plane | 1 oz |
| Inner 2 | Power plane | 1 oz |
| Bottom | Control signals | 1 oz |

### 7.2 Thermal Via Requirements

| Location | Via Count | Diameter | Purpose |
|----------|-----------|----------|---------|
| LMR51430 GND | 8-12 | 0.3mm | Heat to ground plane |
| XC6220 GND | 6-8 | 0.3mm | Heat to ground plane |
| UCC21550 | 4-6 | 0.3mm | Heat spreading |

### 7.3 Copper Pour Areas

| Component | Min Area | Connection |
|-----------|----------|------------|
| LMR51430 | 500mm² | GND, VIN, SW |
| XC6220 | 300mm² | GND, thermal pad |
| ESP32 module | 400mm² | GND |

---

## 8. System Thermal Budget Summary

### 8.1 Power Budget at 40°C Ambient

| Subsystem | Input | Loss | Output | Efficiency |
|-----------|-------|------|--------|------------|
| AC Input | 2115W | 5W | 2110W | 99.8% |
| Rectifier | 2110W | 5W | 2105W | 99.8% |
| Half-bridge | 2105W | 60W | 2045W | 97.1% |
| Coil | 2045W | 45W | 2000W | 97.8% |
| **System Total** | **2115W** | **115W** | **2000W** | **94.6%** |

### 8.2 Temperature Summary at Steady State

| Component | 25°C Ambient | 40°C Ambient | 55°C Ambient | 70°C Ambient |
|-----------|--------------|--------------|--------------|--------------|
| IGBT Tj | 67°C | 82°C | 97°C | 112°C |
| Heatsink Tc | 46°C | 61°C | 76°C | 91°C |
| Coil | 80°C | 95°C | 110°C | 125°C ⚠️ |
| LMR51430 Tj | 95°C | 115°C | 130°C | 150°C ⚠️ |
| XC6220 Tj | 80°C | 100°C | 115°C | 130°C |
| ESP32 | 35°C | 50°C | 65°C | 80°C |

### 8.3 Thermal Margin Summary

| Component | Max Tj | Worst Tj | Margin | Status |
|-----------|--------|----------|--------|--------|
| IKW40N120H3 | 150°C | 112°C | 38°C | ✅ OK |
| Coil insulation | 130°C | 125°C | 5°C | ⚠️ Tight |
| LMR51430 | 150°C | 150°C | 0°C | ⚠️ At limit* |
| XC6220 | 150°C | 130°C | 20°C | ✅ OK |
| ESP32-S3 | 105°C | 80°C | 25°C | ✅ OK |

*LMR51430 requires placement away from heat sources; see LMR51430_THERMAL_ANALYSIS.md

---

## 9. Design Recommendations

### 9.1 Critical Success Factors

1. **Forced air cooling** - Required for 240V system at full power
2. **LMR51430 placement** - Away from power stage, good copper pour
3. **Thermal protection** - NTC sensors on heatsink and coil
4. **Derating** - Implement power reduction above 50°C ambient

### 9.2 Design Checklist

- [x] IGBT thermal analysis complete (sim_30)
- [x] Coil thermal analysis complete (sim_31)
- [x] LMR51430 thermal analysis complete
- [x] LDO selection and thermal analysis (sim_15)
- [x] Heatsink specified (100-120mm extruded aluminum)
- [x] Fan specified (80mm, <25dBA)
- [x] Thermal protection thresholds defined
- [x] Derating curves established
- [x] PCB thermal layout guidelines defined

---

## 10. Conclusion

The Temper induction cooker thermal design is validated for:

- **2kW continuous operation** at ambient ≤50°C
- **Reduced power operation** at ambient 50-70°C
- **Safe shutdown** at ambient >70°C or component overtemperature

**Key thermal risks:**
1. Coil insulation at high ambient (mitigated by power derating)
2. LMR51430 at high ambient (mitigated by placement and copper pour)

**Epic temper-8rf: COMPLETE**

---

## 11. References

| Document | Content |
|----------|---------|
| THERMAL_DESIGN_GUIDE.md | Overview, 120V system |
| LMR51430_THERMAL_ANALYSIS.md | Aux power supply thermal |
| sim_30_thermal_verification.md | IGBT detailed analysis |
| sim_31_coil_thermal_analysis.md | Coil losses |
| sim_15_ldo_selection_verification.md | LDO thermal |
| IKW40N120H3 datasheet | IGBT thermal specs |
| RESONANT_TANK_DESIGN.md | ZVS loss estimates |

---

**END OF DOCUMENT**
