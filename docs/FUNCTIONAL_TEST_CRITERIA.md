# Functional Test Acceptance Criteria

**Project:** Temper Induction Cooker  
**Version:** 1.0  
**Date:** 2025-12-17

---

## 1. Performance Testing

### 1.1 Efficiency
**Goal:** Verify power conversion efficiency > 90% (Class D target).

| Parameter | Test Condition | Pass Criteria | Notes |
|-----------|----------------|---------------|-------|
| **System Efficiency** | 1000W Output | **> 90%** | Pin / Pout |
| **System Efficiency** | 1800W Output | **> 92%** | ZVS active |
| **Standby Power** | Off state | **< 1.0 W** | Mains connected |

### 1.2 Power Delivery Accuracy
**Goal:** Verify output power matches setpoint within tolerance.

| Setpoint | Allowable Range | Tolerance |
|----------|-----------------|-----------|
| **200 W** | 150 - 250 W | ±25% (Low power) |
| **1000 W** | 900 - 1100 W | ±10% |
| **1800 W** | 1700 - 1900 W | ±5% |

### 1.3 Temperature Control
**Goal:** Verify PID loop stability and accuracy.

| Parameter | Condition | Pass Criteria |
|-----------|-----------|---------------|
| **Accuracy** | Steady state at 100°C | **± 2°C** | Using calibrated ref |
| **Stability** | 30 min hold at 60°C | **± 1°C** | Deviation |
| **Overshoot** | Step 25°C -> 100°C | **< 5°C** | Max peak |
| **Settling Time** | Step 25°C -> 100°C | **< 5 min** | To within 2°C |

---

## 2. Protection Circuit Validation

### 2.1 Over-Current Protection (OCP)
**Goal:** Verify hardware latch trips before damage.

| Parameter | Setting | Trip Threshold | Response Time |
|-----------|---------|----------------|---------------|
| **Primary OCP** | 50A Peak | **45 - 55 A** | **< 1 µs** |
| **Secondary OCP** | 60A Peak | **55 - 65 A** | **< 5 µs** |

### 2.2 Over-Voltage Protection (OVP)
**Goal:** Protect bus capacitors and IGBTs.

| Parameter | Setting | Trip Threshold | Hysteresis |
|-----------|---------|----------------|------------|
| **DC Bus OVP** | 400V | **390 - 410 V** | **10 - 20 V** |

### 2.3 Thermal Shutdown
**Goal:** Prevent IGBT destruction.

| Sensor | Trip Temp | Recovery Temp | Response |
|--------|-----------|---------------|----------|
| **Heatsink NTC** | 85°C | 70°C | Shutdown |
| **Coil NTC** | 120°C | 100°C | Shutdown |

### 2.4 Under-Voltage Lockout (UVLO)
**Goal:** Prevent gate driver undefined state.

| Rail | Trip Threshold (Falling) | Recovery (Rising) |
|------|--------------------------|-------------------|
| **Gate Drive (15V)** | **< 12.0 V** | **> 13.0 V** |
| **Logic (3.3V)** | **< 2.9 V** | **> 3.0 V** |

---

## 3. Electromagnetic Compatibility (Pre-Compliance)

### 3.1 Conducted Emissions
**Goal:** Minimize noise on AC lines (CISPR 14-1 Class B).

| Frequency | Limit (Quasi-Peak) | Limit (Average) | Pass Margin |
|-----------|--------------------|-----------------|-------------|
| 150 - 500 kHz | 66-56 dBµV | 56-46 dBµV | **> 3 dB** |
| 0.5 - 5 MHz | 56 dBµV | 46 dBµV | **> 3 dB** |
| 5 - 30 MHz | 60 dBµV | 50 dBµV | **> 3 dB** |

---

## 4. Mechanical Stress

| Test | Condition | Pass Criteria |
|------|-----------|---------------|
| **Button Force** | Actuation | **2 - 5 N** | Tactile feedback |
| **Knob Torque** | Rotation | **0.5 - 2 N·cm** | Smooth feel |
| **Glass Load** | Static weight | **20 kg** | No cracking |

---

## Appendix: Runaway Boundary Map Reference

The interlock trip thresholds (85 C heatsink / 120 C coil in SS 2.3) are
verified against the IKW40N120H3 thermal-runaway boundary by simulation 35.

- **Boundary map:** `simulation/results/runaway_boundary_map.svg`
- **Margin report:** `simulation/results/runaway_interlock_margin.md`
- **Testbench:** `simulation/testbenches/sim_35_runaway_boundary.cir`
- **Plan:** `docs/plans/2026-06-22-010-feat-runaway-boundary-interlock-plan.md`

The interlock must fire with >=20 C margin below the runaway boundary at
every sweep corner (432 points). See the margin report for per-point
pass/fail and worst-3 corners.

---
