# Simulation 18: Overvoltage Protection (OVP) Circuit Verification

## 1. Overview

This document verifies the overvoltage protection (OVP) circuit designed to detect DC bus overvoltage (>390V) and trigger the gate driver DISABLE signal.

**Testbench:** `simulation/testbenches/sim_18_ovp_protection.cir`  
**Date:** 2025-12-14  
**Status:** PASS

## 2. Design Requirements

| Parameter | Requirement | Measured | Status |
|-----------|-------------|----------|--------|
| Trip threshold | ~390V (with margin below 400V max) | 390V | PASS |
| Response time | <10µs | 9.1ns | PASS |
| No trip at 310V | Output = 0V | 0V | PASS |
| Trip at 420V | Output = 5V | 5V | PASS |

## 3. Circuit Configuration

### 3.1 High-Voltage Resistive Divider
- **R_div1, R_div2, R_div3:** 3 × 1MΩ (3MΩ total, high-side)
- **R_div4:** 30kΩ (low-side)
- **Division ratio:** 30k / (3M + 30k) = 1:101
- **Output at 310V:** 3.07V
- **Output at 390V:** 3.85V (threshold)
- **Output at 420V:** 4.16V

### 3.2 Reference Voltage
- **Generation:** Resistive divider from 5V supply
- **R_ref1:** 3kΩ, **R_ref2:** 10kΩ
- **V_ref:** 5V × 10k/(3k+10k) = 3.846V

### 3.3 Comparator
- **Model:** Behavioral (40ns propagation delay)
- **Trip condition:** V_divider > V_ref
- **Output:** 5V when overvoltage, 0V otherwise

## 4. Test Scenario

| Time Period | DC Bus Voltage | Expected Output |
|-------------|----------------|-----------------|
| 0 - 50µs | 310V (normal) | LOW |
| 50 - 100µs | Ramp 310V → 420V | Trip during ramp |
| 100 - 150µs | 420V (fault) | HIGH |
| 150 - 200µs | Return to 310V | LOW (no latching in this stage) |

## 5. Measurement Results

### 5.1 Voltage Divider Performance

| Measurement | Value | Expected | Status |
|-------------|-------|----------|--------|
| V_ref (reference) | 3.846V | 3.85V | PASS |
| V_div at 310V | 3.069V | 3.07V | PASS |
| V_div at 420V | 4.158V | 4.16V | PASS |

### 5.2 Threshold Calculation

```
Trip threshold = V_ref × (R_total / R_low)
             = 3.846V × (3.03MΩ / 30kΩ)
             = 3.846V × 101
             = 388.5V ≈ 390V
```

### 5.3 Timing Performance

| Measurement | Value | Target | Status |
|-------------|-------|--------|--------|
| Time when V_div crosses threshold | 85.84µs | - | - |
| Time when fault output trips | 85.85µs | - | - |
| **Response time** | **9.1ns** | <10µs | **PASS** |

## 6. Waveform Analysis

```
DC Bus Voltage Profile:
                    _______________
        420V ──────/               \──────
                  /                 \
        310V ────/                   \────

Divider Output:
                   _______________
       4.16V ─────/               \─────
             ↗   /                 \
       3.07V ──•/                   \•───
               ↑                    
          Threshold crossing (t=85.84µs)

Fault Output:
       5V ─────────|‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾|─────
       0V ─────────|               |─────
                   ↑               ↑
              Trip (85.85µs)   Clear (when bus returns)
```

## 7. Component Selection

### 7.1 Resistor Divider
- **High-side resistors:** 3 × CRCW12061M00FKEA (1MΩ, 1206, 200V rating each)
  - Total voltage capability: 600V (with margin)
  - Power dissipation at 420V: (420V)² / 3.03MΩ = 58mW
- **Low-side resistor:** CRCW120630K0FKEA (30kΩ, 1206)
  - Power dissipation: (4.16V)² / 30kΩ = 0.58mW

### 7.2 Comparator
- **Recommended:** TLV3201 or LMV7271
- **Supply:** 5V single-supply
- **Propagation delay:** 40ns typical
- **Output:** Push-pull (drives CMOS logic directly)

### 7.3 ESD Protection
- Add TVS diode (SMBJ5.0A) at divider output
- Protects comparator input from transients

## 8. Safety Analysis

### 8.1 Failure Modes

| Failure | Effect | Mitigation |
|---------|--------|------------|
| R_div open (high-side) | False trip | Fail-safe (system shuts down) |
| R_div open (low-side) | No trip capability | Use redundant monitoring |
| Comparator failure | Various | Watchdog + redundant comparator |

### 8.2 Voltage Ratings
- Maximum DC bus (fault): 450V
- Resistor chain voltage: 450V / 3 = 150V per resistor (OK with 200V rating)
- Divider output at 450V: 4.46V (within 5V logic range)

## 9. Integration Notes

### 9.1 Connection to Interlock
- OVP_FAULT signal connects to 74HC4075 OR gate input
- Combined with OCP and Thermal faults
- Latching provided by sim_20 circuit

### 9.2 Filtering Considerations
- No filtering on divider (fast response required)
- Optional 100pF cap at comparator input for noise immunity
- Keep traces short from divider to comparator

## 10. Conclusion

The OVP circuit meets all design requirements:
- **9.1ns response time** (target: <10µs) - exceeds requirement by 1000×
- **Accurate threshold** at ~390V with 10V margin below 400V limit
- **Clean switching** with no oscillation at threshold
- **Proper output levels** (0V normal, 5V fault)

The circuit provides reliable overvoltage detection to protect the IGBTs and downstream components from DC bus voltage excursions.

## 11. References

- [SAFETY_INTERLOCK_DESIGN.md](../../SAFETY_INTERLOCK_DESIGN.md) - Overall safety architecture
- [VOLTAGE_DOUBLER_DESIGN.md](../../VOLTAGE_DOUBLER_DESIGN.md) - DC bus generation
- [sim_20_interlock_verification.md](sim_20_interlock_verification.md) - Fault integration
