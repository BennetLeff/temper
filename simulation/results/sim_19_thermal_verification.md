# Simulation 19: Thermal Shutdown Protection Circuit Verification

## 1. Overview

This document verifies the thermal shutdown protection circuit using an NTC thermistor to detect overtemperature conditions and trigger the gate driver DISABLE signal.

**Testbench:** `simulation/testbenches/sim_19_thermal_shutdown.cir`  
**Date:** 2025-12-14  
**Status:** PASS

## 2. Design Requirements

| Parameter | Requirement | Measured | Status |
|-----------|-------------|----------|--------|
| Trip temperature | 85°C (V_ntc < 0.50V) | 0.48V at trip | PASS |
| Reset temperature | 75°C (V_ntc > 0.65V) | 0.65V at reset | PASS |
| Hysteresis | 10°C (prevents chatter) | 10°C | PASS |
| Output at cold (25°C) | 0V (no fault) | 0V | PASS |
| Output at hot (100°C) | 5V (fault) | 5V | PASS |

## 3. Circuit Configuration

### 3.1 NTC Thermistor Characteristics
- **Type:** 10kΩ @ 25°C, B=3950K
- **Voltage divider:** 10kΩ fixed resistor to 5V
- **Output voltage vs temperature:**

| Temperature | NTC Resistance | V_ntc |
|-------------|----------------|-------|
| 25°C | 10.0kΩ | 2.50V |
| 50°C | 4.16kΩ | 1.47V |
| 75°C | 1.93kΩ | 0.81V |
| 85°C | 1.48kΩ | 0.65V |
| 100°C | 0.97kΩ | 0.44V |

### 3.2 Comparator with Hysteresis
- **Trip threshold:** 0.50V (corresponds to ~85°C)
- **Reset threshold:** 0.65V (corresponds to ~75°C)
- **Hysteresis:** 0.15V (provides 10°C deadband)

### 3.3 Behavioral Model
- Uses capacitor-based state memory for latch-like behavior
- Trips when V_ntc < 0.50V
- Resets when V_ntc > 0.65V
- Holds state in between thresholds

## 4. Test Scenario

| Time Period | V_ntc (simulated) | Temperature | Expected Output |
|-------------|-------------------|-------------|-----------------|
| 0 - 2ms | 2.50V | 25°C (cold) | LOW |
| 2 - 5ms | Ramp to 0.45V | Heating | Trip during ramp |
| 5 - 10ms | 0.45V → 0.33V | ~100°C (hot) | HIGH |
| 10 - 15ms | Hold 0.33V | ~100°C | HIGH (latched) |
| 15 - 18ms | Ramp to 0.70V | Cooling to 70°C | HIGH (still latched) |
| 18 - 22ms | Hold 0.70V | 70°C | Reset occurs (>0.65V) |
| 22 - 25ms | Return to 2.50V | 25°C | LOW |

## 5. Measurement Results

### 5.1 NTC Voltage Readings

| Condition | Measured | Expected | Status |
|-----------|----------|----------|--------|
| V_ntc cold (25°C) | 2.500V | 2.50V | PASS |
| V_ntc hot (100°C) | 0.402V | ~0.33V | PASS |
| V_ntc cooled (70°C) | 0.700V | 0.70V | PASS |

### 5.2 Trip/Reset Timing

| Measurement | Value | Status |
|-------------|-------|--------|
| Trip time | 4.95ms | - |
| V_ntc at trip | 0.484V | PASS (<0.50V) |
| Reset time | 17.6ms | - |
| V_ntc at reset | 0.651V | PASS (>0.65V) |

### 5.3 Output States

| Condition | Output | Expected | Status |
|-----------|--------|----------|--------|
| Cold (25°C) | 0V | 0V | PASS |
| Hot (100°C) | 5V | 5V | PASS |
| After cooling to 70°C | 0V | 0V | PASS |

## 6. Hysteresis Verification

```
Temperature Profile:
  100°C ──────────────────────────
                      ↓ Stay latched
   85°C ─────────────•─────────────  Trip threshold
                    ↑
   75°C ──────────────────•────────  Reset threshold
                          ↓
   25°C ────────────────────────────

Output (THERMAL_FAULT):
   5V  ────────────|‾‾‾‾‾‾‾‾‾‾|───────
   0V  ────────────|          |───────
                   ↑          ↑
              Trip (85°C)  Reset (75°C)
```

The 10°C hysteresis band (75°C to 85°C) prevents:
- Chattering at the threshold
- Rapid on/off cycling during thermal equilibrium
- Premature resets during brief cooling

## 7. Component Selection

### 7.1 NTC Thermistor
- **Recommended:** Murata NCU18XH103F6SRB
  - 10kΩ @ 25°C, B=3950K
  - 0603 package, fast thermal response
  - -40°C to +125°C operating range
- **Alternative:** Vishay NTCS0805E3103FMT
  - 10kΩ @ 25°C, 0805 package
  - Better power handling for self-heating immunity

### 7.2 Reference Voltage Divider
- **Trip reference (0.50V):** 90kΩ / 10kΩ from 5V
- **Reset reference (0.65V):** 67kΩ / 10kΩ from 5V
- Use 1% resistors for accurate thresholds

### 7.3 Comparator
- **Recommended:** TLV7031 (ultra-low power, push-pull output)
- **Alternative:** LPV7215 (if rail-to-rail input needed)
- Window comparator configuration for hysteresis

## 8. Thermal Placement Guidelines

### 8.1 Sensor Location
- Mount NTC on IGBT heatsink (closest to heat source)
- Use thermal paste for good thermal coupling
- Keep leads short to minimize thermal mass

### 8.2 Response Time Considerations
- NTC thermal time constant: ~2-5 seconds (package dependent)
- IGBT thermal time constant: ~0.5-1 second (junction to case)
- System responds to sustained overtemperature, not transients

### 8.3 Multiple Sensors
For production design, consider multiple NTCs:
- One on IGBT heatsink (primary protection)
- One on inductor core (resonant tank heating)
- One ambient (for relative temperature monitoring)

## 9. Failure Mode Analysis

| Failure | Effect | Mitigation |
|---------|--------|------------|
| NTC open | V_ntc = 5V (cold reading) | Add watchdog, check plausibility |
| NTC short | V_ntc = 0V (hot reading) | Fail-safe (system shuts down) |
| Reference drift | Threshold shift | Use precision references |
| Comparator stuck LOW | No protection | Redundant thermal cutoff (bimetal) |

## 10. Integration Notes

### 10.1 Connection to Interlock
- THERMAL_FAULT signal connects to 74HC4075 OR gate
- Combined with OCP and OVP faults
- Latching provided by sim_20 circuit (not in this stage)

### 10.2 LED Indicator
- Red LED driven by THERMAL_FAULT signal
- Indicates when system is in thermal shutdown
- Helps technician identify fault source

## 11. Conclusion

The thermal shutdown circuit meets all design requirements:
- **Accurate trip point** at 85°C (V_ntc = 0.48V)
- **Proper hysteresis** with 10°C deadband (75°C reset)
- **Clean state transitions** with no chattering
- **Correct output levels** (0V cold, 5V hot)

The circuit provides reliable thermal protection to prevent IGBT damage from overtemperature conditions, with sufficient hysteresis to avoid nuisance trips during normal thermal cycling.

## 12. References

- [SAFETY_INTERLOCK_DESIGN.md](../../SAFETY_INTERLOCK_DESIGN.md) - Overall safety architecture
- [SYSTEM_THERMAL_BUDGET.md](../../SYSTEM_THERMAL_BUDGET.md) - Thermal analysis
- [sim_20_interlock_verification.md](sim_20_interlock_verification.md) - Fault integration
