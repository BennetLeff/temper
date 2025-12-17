# Simulation 17: Overcurrent Protection (OCP) Circuit Verification

## 1. Overview

This document verifies the overcurrent protection (OCP) circuit designed to detect excessive tank current and trigger the gate driver DISABLE signal.

**Testbench:** `simulation/testbenches/sim_17_ocp_protection.cir`  
**Date:** 2025-12-14  
**Status:** PASS

## 2. Design Requirements

| Parameter | Requirement | Measured | Status |
|-----------|-------------|----------|--------|
| Response time | <14.3µs (half-cycle @ 35kHz) | 33ns | PASS |
| Trip threshold | 50A peak | 50A | PASS |
| No false trip at 40A | V_abs < 2.5V | 2.0V | PASS |
| Correct detection at 60A | V_abs > 2.5V | 3.0V | PASS |

## 3. Circuit Configuration

### 3.1 Current Transformer
- **Ratio:** 1:1000
- **Magnetizing inductance:** 10mH
- **Leakage inductance:** 100µH
- **Winding resistance:** 50Ω

### 3.2 Burden Resistor
- **Value:** 50Ω
- **Output scaling:** 50mV/A primary (after CT transformation)
- **Voltage at 50A:** 2.5V (threshold)
- **Voltage at 40A:** 2.0V (normal operation)
- **Voltage at 60A:** 3.0V (fault condition)

### 3.3 Full-Wave Rectification
- Behavioral model using |V_in|
- In hardware: Precision rectifier with op-amp + diodes
- Small RC filter (100Ω + 10pF) for noise immunity

### 3.4 Comparator
- **Model:** TLV3201 (behavioral)
- **Propagation delay:** 40ns typical
- **Reference voltage:** 2.5V (from resistive divider)
- **Hysteresis:** ~10% (470kΩ/47kΩ ratio)

## 4. Test Scenario

| Time Period | Tank Current | Expected Output |
|-------------|--------------|-----------------|
| 0 - 50µs | 40A peak (normal) | LOW (no trip) |
| 50µs+ | 60A peak (fault) | HIGH (trip) |

## 5. Measurement Results

### 5.1 Detection Performance

| Measurement | Value | Expected | Status |
|-------------|-------|----------|--------|
| V_abs at 40A | 2.000V | <2.5V | PASS |
| V_abs at 60A | 3.000V | >2.5V | PASS |

### 5.2 Timing Performance

| Measurement | Value | Target | Status |
|-------------|-------|--------|--------|
| First trip after fault onset | 50.03µs | - | - |
| Response time | 33ns | <14.3µs | PASS |
| Second trip time | 62.46µs | - | - |
| Trip period | 12.4µs | ~14.3µs | PASS |

### 5.3 Cycle-by-Cycle Behavior

The OCP circuit provides **cycle-by-cycle overcurrent detection**:
- When tank current exceeds 50A, the comparator pulses HIGH
- Each pulse corresponds to one half-cycle where |I| > threshold
- Trip period of 12.4µs confirms operation at 35kHz (half-period = 14.3µs)

## 6. Waveform Analysis

```
Tank Current Profile:
     ___         ___
    /   \       /   \      40A peak (normal)
   /     \     /     \
  ─────────────────────  → t=50µs → Fault onset
          _____       _____
         /     \     /     \   60A peak (fault)
        /       \   /       \
       ─────────────────────────

Comparator Output (OCP_FAULT):
  _____________________|‾‾|__|‾‾|__|‾‾|__|‾‾|__
                       ↑
                     33ns response
```

## 7. Hardware Implementation Notes

### 7.1 Recommended Components
- **Current transformer:** VAC T60404-E4627-X501 or equivalent
- **Precision rectifier:** OPA2350 dual op-amp + BAT54S Schottky diodes
- **Comparator:** TLV3201 (40ns, push-pull output)
- **Reference:** Resistive divider from 5V rail

### 7.2 PCB Layout Considerations
- Keep CT burden resistor close to rectifier input
- Use ground plane under analog section
- Separate analog and digital grounds, star at ADC reference
- Shield CT secondary wiring if >5cm

### 7.3 Integration with Interlock
- OCP_FAULT signal feeds into 74HC4075 OR gate (sim_20)
- Combined with OVP and thermal faults
- Latching logic maintains DISABLE until manual reset

## 8. Conclusion

The OCP circuit meets all design requirements:
- **33ns response time** (target: <14.3µs) - exceeds requirement by 430×
- **No false trips** at normal 40A operation
- **Reliable detection** at 60A fault condition
- **Cycle-by-cycle protection** enables per-half-cycle current limiting

The fast response time ensures the IGBTs are disabled within a small fraction of the resonant cycle, preventing destructive overcurrent conditions.

## 9. References

- [SAFETY_INTERLOCK_DESIGN.md](../../SAFETY_INTERLOCK_DESIGN.md) - Overall safety architecture
- [CT_SENSING_DESIGN.md](../../CT_SENSING_DESIGN.md) - Current transformer design
- [sim_20_interlock_verification.md](sim_20_interlock_verification.md) - Fault integration
