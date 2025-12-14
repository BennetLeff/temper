# Voltage Doubler Rectifier Design

## Overview

The Temper induction cooker uses a **full-wave voltage doubler** to convert 120VAC mains to ~314VDC, enabling 1500-1800W operation from a standard 15A outlet.

## Why Voltage Doubler?

### The Problem

With a standard full-bridge rectifier on 120VAC:
- DC bus voltage: ~170V (peak of 120V RMS)
- At 170V with our 8Ω tank impedance: P = V²/Z = 170²/8 = **3.6kW theoretical**
- But real-world losses limit us to **~700W** (see sim_32 analysis)

The tank impedance and switching losses create significant voltage drops that prevent achieving 1800W with only 170V DC bus.

### The Solution

A voltage doubler provides:
- DC bus voltage: ~314V (2× peak, minus losses)
- Sufficient headroom to drive 1800W through the resonant tank
- Compatible with 120V/15A outlet (no 240V required)

## Topology Selection

### Half-Wave (Greinacher) Doubler
```
                D1
    L o────┬────>|────┬───── Vout (+340V)
           │          │
          C1         C2
           │          │
    N o────┴────|<────┴───── GND
                D2
```
- Simpler (2 diodes, 2 caps)
- Higher ripple (60Hz)
- More voltage sag under load
- **Simulation result: 289V, 29V ripple, 1304W** ❌

### Full-Wave (Delon) Doubler ✅ SELECTED
```
                D1 →
    L o────┬────>|────┬───── +Vbus/2 (+157V)
           │          │
          (~)        C1
          AC        3300µF
           │          │
           │          ├───── GND (center)
           │          │
           │         C2
           │        3300µF
           │          │
    N o────┴────|<────┴───── -Vbus/2 (-157V)
                D2 ←
```
- Lower ripple (120Hz vs 60Hz)
- Better regulation under load
- Balanced capacitor stress
- **Simulation result: 314V, 20V ripple, 1538W** ✅

## Simulation Results

### Test Conditions
- Input: 120VAC, 60Hz
- Load: 64Ω (equivalent to 1800W at 340V)
- Simulation: 500ms transient, measurements at 400-500ms (steady state)

### Results (sim_33_voltage_doubler.cir)

| Parameter | Value | Target | Status |
|-----------|-------|--------|--------|
| DC Bus (avg) | 314V | ≥300V | ✅ PASS |
| DC Bus (min) | 303V | - | OK |
| DC Bus (max) | 323V | - | OK |
| Ripple (pk-pk) | 20V | <30V | ✅ PASS |
| Load Power | 1538W | ≥1500W | ✅ PASS |
| +Rail Voltage | +157V | ~170V | OK |
| -Rail Voltage | -157V | ~-170V | OK |

### Voltage Sag Analysis

Theoretical output: 2 × 170V = 340V
Actual output: 314V
Sag: 26V (7.6%)

Causes:
1. Diode forward drops: 2 × 0.7V = 1.4V
2. Capacitor discharge during non-conduction: ~20V
3. Source impedance: ~4V

This sag is acceptable - we still achieve >300V needed for 1500W+ operation.

## Component Specifications

### Capacitors (C1, C2)

| Parameter | Specification |
|-----------|---------------|
| Value | 3300µF (3.3mF) each |
| Voltage Rating | 250V minimum (200V nominal + margin) |
| Type | Aluminum Electrolytic |
| Temperature | 105°C rated |
| ESR | Low ESR type preferred |
| Ripple Current | ≥5A RMS at 120Hz |
| Lifetime | ≥5000 hours at 105°C |

**Recommended Parts:**
| Part Number | Manufacturer | Value | Voltage | Ripple | Price |
|-------------|--------------|-------|---------|--------|-------|
| EKZE251ELL332MM40S | United Chemi-Con | 3300µF | 250V | 3.89A | ~$8 |
| 450BXW3300M | Cornell Dubilier | 3300µF | 250V | 5.4A | ~$12 |
| B43544A2338M | TDK/EPCOS | 3300µF | 250V | 4.9A | ~$10 |

**Note:** Each capacitor only sees ~170V (one rail), so 250V rating provides adequate margin.

### Diodes (D1, D2)

| Parameter | Specification |
|-----------|---------------|
| Type | Ultrafast Recovery |
| Current (avg) | 15A minimum |
| Current (surge) | 50A minimum |
| Voltage (PIV) | 600V minimum |
| Recovery Time | <50ns |
| Package | TO-220 or TO-247 |

**Recommended Parts:**
| Part Number | Manufacturer | Current | Voltage | Trr | Price |
|-------------|--------------|---------|---------|-----|-------|
| MUR1560 | ON Semi | 15A | 600V | 35ns | ~$1.50 |
| RHRP1560 | ON Semi | 15A | 600V | 35ns | ~$1.20 |
| STTH1506 | STMicro | 15A | 600V | 25ns | ~$2.00 |
| VS-15ETH06-M3 | Vishay | 15A | 600V | 35ns | ~$1.80 |

**Note:** Ultrafast recovery is important to minimize switching losses and EMI at 38kHz.

### Soft-Start Circuit (Required)

**CRITICAL:** The voltage doubler has massive inrush current without soft-start!

Inrush current estimate: I_peak = V_peak / R_source = 170V / 0.1Ω = **1700A** (destructive!)

**Soft-Start Implementation:**
```
    AC Line ───┬─── NTC ──────┬─── Rectifier
               │              │
               └── Relay ─────┘
                   (bypass)
```

1. **NTC Thermistor** limits inrush at startup
   - Cold resistance: 10-20Ω (limits inrush to ~17A)
   - Hot resistance: <0.5Ω (minimal loss during operation)
   - Recommended: Ametherm SL32 10015 (10Ω, 15A)

2. **Bypass Relay** shorts NTC after startup
   - Activated 100-500ms after power-on
   - Reduces steady-state losses
   - Recommended: Omron G5LE-1 (10A, 250VAC)

3. **Alternative: Resistor + Relay**
   - Fixed 10Ω power resistor in series
   - Relay bypasses after soft-start
   - More predictable, but requires heatsinking during start

## Split-Rail Considerations

The full-wave doubler creates a **split supply** (+157V / -157V):

### Advantages
- Balanced capacitor stress
- Natural center point for half-bridge connection
- Lower voltage rating required per capacitor

### Design Implications
1. **Half-bridge connection:** Connect resonant tank between bus_p and bus_n
2. **Gate driver isolation:** Required for both high-side and low-side (different references)
3. **Control ground:** ESP32 should reference the center point (GND)
4. **Safety:** Both rails are "hot" relative to earth ground

### Ground Strategy
```
                    +157V (bus_p)
                      │
                    ┌─┴─┐
                    │   │ C1
                    └─┬─┘
                      │
    Earth ─────────── ○ ─────────── GND (control reference)
                      │
                    ┌─┴─┐
                    │   │ C2
                    └─┬─┘
                      │
                    -157V (bus_n)
```

**SAFETY NOTE:** The center point (GND) should be connected to earth ground through appropriate safety components (EMI filter, fuse, etc.).

## Power Path Integration

### Complete Power Path
```
AC Mains (120V) 
    │
    ├── EMI Filter (CM + DM)
    │
    ├── Fuse (15A slow-blow)
    │
    ├── NTC Soft-Start + Bypass Relay
    │
    ├── Voltage Doubler (D1, D2, C1, C2)
    │       │
    │       ├── +157V rail
    │       ├── GND (center)
    │       └── -157V rail
    │
    ├── Half-Bridge (Q1, Q2 - IKW40N120H3)
    │
    ├── Resonant Tank (L=80µH, C=330nF)
    │
    └── Induction Coil → Pan
```

## Thermal Considerations

### Diode Losses
- Forward voltage: ~1.0V at 5A
- Average current: ~5A per diode
- Power loss per diode: ~5W
- Total diode loss: ~10W

### Capacitor Losses
- ESR heating from ripple current
- Estimated: 1-2W per capacitor
- Total capacitor loss: ~3W

### Total Rectifier Losses
- Diodes: 10W
- Capacitors: 3W
- NTC (bypassed): 0W
- **Total: ~13W**

This is in addition to the ~40W IGBT losses and ~50W coil losses.

## EMI Considerations

### Conducted EMI Sources
1. High di/dt during diode conduction
2. Reverse recovery current spikes
3. 38kHz switching noise coupling back to mains

### Mitigation
1. **Input EMI filter:** Required before rectifier
2. **Ultrafast diodes:** MUR1560 with 35ns recovery
3. **Snubber capacitors:** Optional RC snubbers across diodes
4. **Layout:** Short, low-inductance paths

## Safety Features

1. **Fuse:** 15A slow-blow on AC input
2. **Bleeder resistors:** 100kΩ across each capacitor (discharge in ~10s)
3. **NTC soft-start:** Limits inrush current
4. **Overvoltage protection:** Varistor on AC input (optional)

## BOM Summary

| Item | Part Number | Quantity | Unit Price | Total |
|------|-------------|----------|------------|-------|
| Capacitor 3300µF/250V | EKZE251ELL332MM40S | 2 | $8.00 | $16.00 |
| Diode 15A/600V | MUR1560 | 2 | $1.50 | $3.00 |
| NTC 10Ω/15A | SL32 10015 | 1 | $3.00 | $3.00 |
| Relay 10A | G5LE-1-E | 1 | $2.00 | $2.00 |
| Bleeder 100kΩ/2W | - | 2 | $0.20 | $0.40 |
| **Total** | | | | **~$25** |

## Verification Checklist

- [x] DC bus voltage ≥300V at full load
- [x] Ripple voltage <30V (acceptable for resonant converter)
- [x] Power delivery ≥1500W verified
- [ ] Soft-start circuit designed
- [ ] EMI filter specified
- [ ] Thermal management verified
- [ ] Safety compliance reviewed

## References

- Simulation: `simulation/testbenches/sim_33_voltage_doubler.cir`
- Results: `simulation/results/sim_33_voltage_doubler_results.txt`
- 120V Analysis: `simulation/results/sim_32_120v_power_analysis.md`
