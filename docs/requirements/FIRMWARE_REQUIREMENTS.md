# Temper Firmware Requirements Specification

**Version:** 1.0  
**Date:** 2025-12-19  
**Status:** Active  
**Domain:** ESP32-S3 Firmware

## Document Purpose

This document defines firmware-specific requirements for the Temper induction cooker control system. For hardware/system requirements, see `REQUIREMENTS.md` in the project root.

## 1. State Machine Requirements (REQ-FW-SM)

### REQ-FW-SM-01: State Count
**Priority:** P0  
**Status:** VERIFIED

The state machine SHALL implement exactly 8 states:
- INIT, IDLE, PAN_DET, PREHEAT, HEATING, NO_PAN, COOLDOWN, FAULT

| Parameter | Value |
|-----------|-------|
| State count | 8 |
| Implementation | `firmware/main/state_machine.c` |

**Validation:** Unit test count >= 37, all state transitions tested  
**Linked Issues:** (baseline requirement)

---

### REQ-FW-SM-02: Fault Recovery
**Priority:** P0  
**Status:** VERIFIED

The system SHALL recover from FAULT state only via explicit user reset. Automatic recovery from FAULT is prohibited.

| Parameter | Value |
|-----------|-------|
| Recovery method | User reset button only |
| Auto-recovery | Disabled |

**Validation:** Integration test `test_fault_requires_user_reset`  
**Linked Issues:** (baseline requirement)

---

### REQ-FW-SM-03: State Transition Latency
**Priority:** P1  
**Status:** IN_PROGRESS

State transitions SHALL complete within 10ms to ensure responsive control.

| Parameter | Value |
|-----------|-------|
| Max transition time | 10ms |
| Measurement point | State entry to exit |

**Validation:** Timing measurement in integration tests  
**Linked Issues:** (create issue)

---

### REQ-FW-SM-04: Watchdog Integration
**Priority:** P0  
**Status:** VERIFIED

Each state SHALL have a maximum dwell time. Exceeding dwell time triggers watchdog fault.

| State | Max Dwell Time |
|-------|----------------|
| INIT | 5s |
| PAN_DET | 10s |
| PREHEAT | 600s (10 min) |
| NO_PAN | 5s |
| COOLDOWN | 300s (5 min) |

**Validation:** `test_watchdog_state_timeout` integration test  
**Linked Issues:** (baseline requirement)

---

## 2. Control Requirements (REQ-FW-CTRL)

### REQ-FW-CTRL-01: Temperature Stability
**Priority:** P0  
**Status:** IN_PROGRESS

The PID controller SHALL maintain temperature stability within specified bounds.

| Range | Stability | Response Time |
|-------|-----------|---------------|
| 30-50°C | ±2°C | <10s |
| 50-250°C | ±1°C | <5s |

**Validation:** Closed-loop simulation and hardware testing  
**Linked Issues:** temper-5xc.1.1

---

### REQ-FW-CTRL-02: PWM Resolution
**Priority:** P1  
**Status:** NOT_STARTED

PWM duty cycle SHALL support 0.1% resolution for precise low-power control.

| Parameter | Value |
|-----------|-------|
| Resolution | 0.1% (1000 steps) |
| Frequency | 20-100 kHz (configurable) |
| Dead time | 200-500ns |

**Validation:** Oscilloscope measurement of PWM output  
**Linked Issues:** (create issue)

---

### REQ-FW-CTRL-03: PLL Tracking
**Priority:** P1  
**Status:** IN_PROGRESS

The PLL SHALL track resonant frequency within ±1 kHz of optimal.

| Parameter | Value |
|-----------|-------|
| Tracking accuracy | ±1 kHz |
| Lock time | <100ms |
| Frequency range | 20-50 kHz |

**Validation:** ZVS margin measurement in simulation  
**Linked Issues:** temper-5xc.1.1

---

### REQ-FW-CTRL-04: Low Power Operation
**Priority:** P1  
**Status:** IN_PROGRESS

System SHALL support stable operation at 5-10% of maximum power for simmering.

| Parameter | Value |
|-----------|-------|
| Minimum power | 5% (~100W) |
| Stability at min | ±10W |
| Modulation | PWM burst mode |

**Validation:** Power measurement at low duty cycles  
**Linked Issues:** temper-5xc.1.1

---

## 3. Safety Requirements (REQ-FW-SAFETY)

### REQ-FW-SAFETY-01: Software Watchdog
**Priority:** P0  
**Status:** VERIFIED

Software watchdog SHALL trigger shutdown within 10 seconds of system hang.

| Parameter | Value |
|-----------|-------|
| Timeout | 10s max (state-dependent) |
| Action | Transition to FAULT state |

**Validation:** `test_watchdog_timeout` integration test  
**Linked Issues:** (baseline requirement)

---

### REQ-FW-SAFETY-02: Over-Temperature Protection
**Priority:** P0  
**Status:** VERIFIED

System SHALL shutdown when heatsink temperature exceeds 100°C.

| Parameter | Value |
|-----------|-------|
| Threshold | 100°C heatsink |
| Action | Immediate FAULT transition |
| Hysteresis | 10°C (restart at 90°C) |

**Validation:** `test_over_temp_shutdown` integration test  
**Linked Issues:** (baseline requirement)

---

### REQ-FW-SAFETY-03: Over-Current Protection
**Priority:** P0  
**Status:** VERIFIED

System SHALL shutdown when DC bus current exceeds 35A.

| Parameter | Value |
|-----------|-------|
| Threshold | 35A DC bus |
| Response time | <1ms |
| Action | Hardware interlock + FAULT state |

**Validation:** Simulation `sim_ocp_response.cir`  
**Linked Issues:** (baseline requirement)

---

### REQ-FW-SAFETY-04: Pan Detection Timeout
**Priority:** P0  
**Status:** VERIFIED

System SHALL exit PAN_DET state if no valid pan detected within 5 seconds.

| Parameter | Value |
|-----------|-------|
| Timeout | 5s |
| Action | Return to IDLE |
| Retry | User must press start again |

**Validation:** `test_pan_detection_timeout` unit test  
**Linked Issues:** (baseline requirement)

---

### REQ-FW-SAFETY-05: Pan Removal Detection
**Priority:** P0  
**Status:** VERIFIED

System SHALL detect pan removal within 500ms and transition to NO_PAN state.

| Parameter | Value |
|-----------|-------|
| Detection time | <500ms |
| Grace period | 3s before returning to IDLE |
| Power during grace | Reduced (10%) |

**Validation:** `test_pan_removal_detection` integration test  
**Linked Issues:** (baseline requirement)

---

### REQ-FW-SAFETY-06: RTD Probe Monitoring
**Priority:** P0  
**Status:** VERIFIED

System SHALL detect RTD probe open/short circuit and transition to FAULT.

| Condition | Detection |
|-----------|-----------|
| Open circuit | R > 500Ω |
| Short circuit | R < 10Ω |
| Response time | <100ms |

**Validation:** `test_rtd_fault_detection` unit test  
**Linked Issues:** (baseline requirement)

---

### REQ-FW-SAFETY-07: Thermal Runaway Detection
**Priority:** P0  
**Status:** VERIFIED

System SHALL detect thermal runaway (pan temp > target + 10°C) and reduce power.

| Parameter | Value |
|-----------|-------|
| Threshold | Target + 10°C |
| Action | Reduce to 50% power |
| Fault threshold | Target + 20°C → FAULT |

**Validation:** `test_thermal_runaway` integration test  
**Linked Issues:** (baseline requirement)

---

## 4. Interface Requirements (REQ-FW-IF)

### REQ-FW-IF-01: SPI Communication (MAX31865)
**Priority:** P1  
**Status:** VERIFIED

MAX31865 RTD interface SHALL operate reliably at 1MHz SPI.

| Parameter | Value |
|-----------|-------|
| Clock speed | 1 MHz |
| Mode | SPI Mode 1 (CPOL=0, CPHA=1) |
| CS setup time | >100ns |

**Validation:** Simulation `sim_spi_timing.md`  
**Linked Issues:** (baseline requirement)

---

### REQ-FW-IF-02: I2C Communication (UI)
**Priority:** P2  
**Status:** NOT_STARTED

User interface I2C bus SHALL support 400 kHz operation.

| Parameter | Value |
|-----------|-------|
| Clock speed | 400 kHz |
| Pull-ups | 4.7kΩ |
| Timeout | 100ms |

**Validation:** I2C bus analyzer measurement  
**Linked Issues:** (create issue)

---

### REQ-FW-IF-03: ADC Sampling
**Priority:** P1  
**Status:** VERIFIED

ADC channels SHALL be sampled at appropriate rates for their function.

| Channel | Sample Rate | Resolution |
|---------|-------------|------------|
| DC Bus Current | 100 kHz | 12-bit |
| DC Bus Voltage | 10 kHz | 12-bit |
| Temperature (NTC) | 10 Hz | 12-bit |

**Validation:** Timing analysis and simulation  
**Linked Issues:** (baseline requirement)

---

## 5. Performance Requirements (REQ-FW-PERF)

### REQ-FW-PERF-01: Boot Time
**Priority:** P2  
**Status:** NOT_STARTED

System SHALL complete INIT state and enter IDLE within 3 seconds of power-on.

| Parameter | Value |
|-----------|-------|
| Boot time | <3s |
| Includes | Hardware init, self-test, calibration |

**Validation:** Timing measurement  
**Linked Issues:** (create issue)

---

### REQ-FW-PERF-02: Control Loop Rate
**Priority:** P1  
**Status:** IN_PROGRESS

Main control loop SHALL execute at 10 kHz minimum.

| Parameter | Value |
|-----------|-------|
| Loop rate | >=10 kHz |
| Jitter | <10 µs |
| CPU usage | <50% at full rate |

**Validation:** RTOS timing analysis  
**Linked Issues:** (create issue)

---

## Requirements Traceability Matrix

| REQ ID | Status | Validation Method | bd Issue |
|--------|--------|-------------------|----------|
| REQ-FW-SM-01 | VERIFIED | 37 unit tests | - |
| REQ-FW-SM-02 | VERIFIED | test_fault_requires_user_reset | - |
| REQ-FW-SM-03 | IN_PROGRESS | timing measurement | TBD |
| REQ-FW-SM-04 | VERIFIED | test_watchdog_state_timeout | - |
| REQ-FW-CTRL-01 | IN_PROGRESS | simulation + hardware | temper-5xc.1.1 |
| REQ-FW-CTRL-02 | NOT_STARTED | oscilloscope | TBD |
| REQ-FW-CTRL-03 | IN_PROGRESS | ZVS margin sim | temper-5xc.1.1 |
| REQ-FW-CTRL-04 | IN_PROGRESS | power measurement | temper-5xc.1.1 |
| REQ-FW-SAFETY-01 | VERIFIED | test_watchdog_timeout | - |
| REQ-FW-SAFETY-02 | VERIFIED | test_over_temp_shutdown | - |
| REQ-FW-SAFETY-03 | VERIFIED | sim_ocp_response.cir | - |
| REQ-FW-SAFETY-04 | VERIFIED | test_pan_detection_timeout | - |
| REQ-FW-SAFETY-05 | VERIFIED | test_pan_removal_detection | - |
| REQ-FW-SAFETY-06 | VERIFIED | test_rtd_fault_detection | - |
| REQ-FW-SAFETY-07 | VERIFIED | test_thermal_runaway | - |
| REQ-FW-IF-01 | VERIFIED | sim_spi_timing.md | - |
| REQ-FW-IF-02 | NOT_STARTED | I2C analyzer | TBD |
| REQ-FW-IF-03 | VERIFIED | timing analysis | - |
| REQ-FW-PERF-01 | NOT_STARTED | timing measurement | TBD |
| REQ-FW-PERF-02 | IN_PROGRESS | RTOS analysis | TBD |

## Summary Statistics

| Category | Total | Verified | In Progress | Not Started |
|----------|-------|----------|-------------|-------------|
| State Machine (SM) | 4 | 3 | 1 | 0 |
| Control (CTRL) | 4 | 0 | 3 | 1 |
| Safety (SAFETY) | 7 | 7 | 0 | 0 |
| Interface (IF) | 3 | 2 | 0 | 1 |
| Performance (PERF) | 2 | 0 | 1 | 1 |
| **Total** | **20** | **12** | **5** | **3** |

**Coverage:** 60% verified, 25% in progress, 15% not started
