# Temper Project Status & Requirements Analysis

**Date:** 2025-12-16  
**Target:** Breville Control Freak Clone in RCA 12A3 Chassis  
**Status:** Design Phase - Gap Analysis Complete

---

## 1. Executive Summary

This document captures the current state of the Temper induction cooker project and identifies the requirements gaps between the existing design and the target functionality of a Breville Control Freak clone, adapted to fit within an RCA 12A3 vintage tube amplifier chassis.

**Key Finding:** The current design is a robust, safety-critical induction platform with industrial-grade protections. However, it lacks the precision control algorithms and low-temperature capabilities that define the Breville Control Freak's unique value proposition.

---

## 2. Current System Capabilities

### 2.1 Firmware (ESP32-S3)

| Capability | Status | Implementation |
|------------|--------|----------------|
| State Machine | ✅ Complete | 8-state control (INIT, IDLE, PAN_DET, PREHEAT, HEATING, NO_PAN, COOLDOWN, FAULT) |
| PID Control | ✅ Complete | Standard single-loop temperature control |
| PLL Tracking | ✅ Complete | Resonant frequency tracking for optimal power transfer |
| Safety System | ✅ Complete | 8 protection layers (OCP, OVP, Thermal, Watchdog, etc.) |
| Test Coverage | ✅ Complete | 37 unit tests + 30 integration tests |
| WiFi/BLE | ⚠️ Hardware Only | ESP32-S3 capable, software not implemented |

**Reference:** `firmware/README.md`, `firmware/main/state_machine.c`

### 2.2 Hardware (PCB)

| Subsystem | Status | Key Components |
|-----------|--------|----------------|
| Power Stage | ✅ Complete | IKW40N120H3 IGBTs (1200V/40A), UCC21550 isolated driver |
| Voltage Doubler | ✅ Complete | 340VDC bus from 120VAC input |
| Power Management | ✅ Complete | LMR51430 buck (24V→5V), XC6220 LDO (5V→3.3V) |
| Temperature Sensing | ✅ Complete | Dual MAX31865 RTD interfaces (Pan + Probe) |
| Current Sensing | ✅ Complete | Current transformer with precision rectifier |
| Safety Interlock | ✅ Complete | Hardware fault latch, independent of MCU |
| Form Factor | ✅ Complete | 100mm × 150mm 4-layer PCB for RCA 12A3 |

**Reference:** `BOM.md`, `PCB_SPECIFICATION.md`, `pcb/*.kicad_sch`

### 2.3 Simulation & Verification

| Area | Status | Coverage |
|------|--------|----------|
| Power Stage | ✅ Complete | Half-bridge, gate driver, thermal |
| Auxiliary Power | ✅ Complete | LMR51430, isolated supplies |
| Safety Logic | ✅ Complete | OCP, OVP, thermal trip points |
| Interface Timing | ✅ Complete | SPI, I2C, PWM, ADC |

**Reference:** `simulation/results/`, `HALF_BRIDGE_VERIFICATION_REPORT.md`

### 2.4 PCB Placement Optimizer (temper-placer)

| Feature | Status |
|---------|--------|
| Core Optimizer | ✅ Operational |
| Curriculum Learning | ✅ Implemented |
| Heuristics (10 types) | ✅ Implemented |
| KiCad Integration | ✅ Complete |
| DRC Validation | ✅ Integrated |

**Reference:** `TEMPER_PLACER_DESIGN.md`, `temper-placer/README.md`

---

## 3. Gap Analysis: Temper vs. Breville Control Freak

### 3.1 Feature Comparison Matrix

| Feature | Breville Control Freak | Current Temper Design | Gap Status |
|---------|------------------------|----------------------|------------|
| **Temperature Range** | 30°C - 250°C | 50°C - 250°C | ⚠️ **GAP** (Low end missing) |
| **Temperature Stability** | ±0.1°C (claimed) | Undefined (standard PID) | ⚠️ **GAP** |
| **Heating Intensity Control** | 10-level "Intensity" setting | Binary (Preheat/Heat) | ⚠️ **GAP** |
| **Pan Sensor** | Through-glass NTC | Under-glass RTD | ✅ Equivalent |
| **Liquid Probe** | External thermocouple | External RTD (MAX31865) | ✅ Equivalent |
| **Cascade Control** | Pan + Liquid dual-loop | Single-loop only | ⚠️ **GAP** |
| **Thermal Mass Estimation** | Auto-adjusts for pan type | Not implemented | ⚠️ **GAP** |
| **User Interface** | Color TFT + rotary encoder | LEDs + encoder (retro) | 🔄 **Intentional Divergence** |
| **Preset Profiles** | 5+ cooking modes | Not implemented | ⚠️ **GAP** |
| **Timer Integration** | Integrated countdown | Firmware ready, UI missing | ⚠️ **GAP** |
| **Acoustic Management** | Dual fan, variable speed | Single fan, tachometer only | ⚠️ **GAP** |
| **Connectivity** | None | WiFi/BLE hardware present | ✅ **Advantage** |

### 3.2 Critical Gaps Summary

1. **Low-Temperature Operation (30°C-50°C):** Essential for chocolate tempering, butter clarification, and sous-vide applications. Current 50°C minimum is a hard limitation.

2. **Precision Control:** The ±0.1°C stability claim requires advanced control algorithms beyond standard PID, including feedforward compensation and thermal modeling.

3. **Intensity/Heat Rate Control:** Users expect to control *how fast* the pan heats, not just the target temperature. Critical for delicate sauces.

4. **Cascade Control:** Preventing scorching while heating liquids requires simultaneous monitoring of pan bottom and liquid temperatures.

---

## 4. New Requirements Specification

The following requirements must be implemented to achieve Breville Control Freak parity within the RCA 12A3 form factor.

### 4.1 Firmware - Physics & Control

#### REQ-FW-01: Low-Temperature Operation
- **Description:** Extend stable control range to 30°C - 50°C
- **Rationale:** Required for chocolate tempering (32°C), butter clarification (35°C), and holding delicate sauces
- **Acceptance Criteria:**
  - System maintains ±1°C stability at 35°C setpoint
  - Pan detection works reliably at low power levels
  - No thermal runaway false positives at low delta-T
- **Priority:** P1 (Critical)
- **Affected Files:** `state_machine.c`, `control/pid.c`

#### REQ-FW-02: Intensity (Heat Rate) Control
- **Description:** Implement user-adjustable maximum heating rate limiter
- **Rationale:** Prevents overshoot and thermal shock in sensitive applications
- **Acceptance Criteria:**
  - 10 discrete intensity levels (1 = gentle, 10 = maximum)
  - Level 1 limits power to ~10% of maximum
  - Rate limiting applies during both preheat and steady-state
- **Priority:** P1 (Critical)
- **Implementation Notes:**
  - Add `intensity_level` parameter to state machine context
  - Modify PWM duty cycle calculation: `duty = min(pid_output, intensity_max[level])`
- **Affected Files:** `state_machine.c`, `state_machine.h`

#### REQ-FW-03: Cascade (Dual-Loop) Control
- **Description:** Implement cascade control with outer liquid temperature loop and inner pan temperature loop
- **Rationale:** Prevents burning pan bottom while heating liquid to target temperature
- **Acceptance Criteria:**
  - Outer loop setpoint = user target (liquid temp)
  - Outer loop output = inner loop setpoint (pan temp limit)
  - Inner loop prevents pan from exceeding outer loop command
  - Graceful degradation to single-loop if probe disconnected
- **Priority:** P1 (Critical)
- **Implementation Notes:**
  - Create new `components/control/cascade_pid.c`
  - Outer loop: slow (τ ~ 30s), anti-windup enabled
  - Inner loop: fast (τ ~ 2s), existing PID
- **Affected Files:** New file `cascade_pid.c`, `state_machine.c`

#### REQ-FW-04: Thermal Mass Estimation
- **Description:** Estimate pan thermal mass during pan detection phase to auto-tune PID gains
- **Rationale:** Cast iron vs. thin stainless requires different control parameters
- **Acceptance Criteria:**
  - Applies known power pulse during PAN_DET state
  - Measures temperature rise rate (dT/dt)
  - Classifies pan as "light", "medium", or "heavy"
  - Adjusts PID gains accordingly
- **Priority:** P2 (High)
- **Implementation Notes:**
  - Use step response identification: `thermal_mass ∝ P / (dT/dt)`
  - Store 3 gain sets in flash, select based on classification
- **Affected Files:** `state_machine.c`, `control/pid.c`

#### REQ-FW-05: Cooking Profiles
- **Description:** Implement multi-stage cooking profiles with time/temperature sequences
- **Rationale:** Common use cases (boil-then-simmer, sear-then-hold) require automated transitions
- **Acceptance Criteria:**
  - Support up to 5 stages per profile
  - Each stage: target temp, intensity, duration (or "hold indefinitely")
  - Profile storage in NVS (ESP32 non-volatile storage)
  - At least 3 preset profiles: "Simmer", "Sear & Hold", "Sous Vide"
- **Priority:** P2 (High)
- **Affected Files:** New file `profiles.c`, `state_machine.c`

#### REQ-FW-06: Fan Speed Control
- **Description:** Implement PWM fan speed control based on thermal load
- **Rationale:** Reduce acoustic noise at low power levels (e.g., 30°C hold)
- **Acceptance Criteria:**
  - Fan speed proportional to heatsink temperature
  - Minimum speed at <50°C heatsink temp
  - Full speed at >80°C heatsink temp
  - Tachometer fault detection still functional at all speeds
- **Priority:** P2 (High)
- **Affected Files:** `hal/pwm.c`, `safety/thermal.c`

### 4.2 Hardware - Mechanical Integration (RCA 12A3)

#### REQ-MECH-01: Spring-Loaded Pan Sensor Mount
- **Description:** Design spring-loaded mounting mechanism for glass-contact RTD sensor
- **Rationale:** Must maintain reliable thermal contact despite chassis vibrations and pan placement variations
- **Acceptance Criteria:**
  - Sensor maintains contact with ≥2N force
  - Travel range ≥5mm to accommodate glass thickness variation
  - Thermal path resistance <0.5 K/W
  - Compatible with existing MAX31865 RTD interface
- **Priority:** P1 (Critical)
- **Deliverable:** STEP file for 3D printing or machining

#### REQ-MECH-02: Induction Coil Mounting Bracket
- **Description:** Design mounting bracket for Litz wire coil that fits RCA 12A3 chassis
- **Rationale:** Air gap consistency is critical for resonant frequency stability
- **Acceptance Criteria:**
  - Maintains coil-to-glass distance of 3mm ±0.5mm
  - Uses existing 12A3 transformer mounting holes if possible
  - Supports coil OD up to 200mm
  - Non-magnetic material (aluminum or plastic)
- **Priority:** P1 (Critical)
- **Deliverable:** STEP file, mounting hardware BOM

#### REQ-MECH-03: Chassis Airflow Ducting
- **Description:** Design airflow ducting to direct cooling air over IGBT heatsink
- **Rationale:** RCA 12A3 has convection vents designed for tubes, not forced-air cooling of semiconductors
- **Acceptance Criteria:**
  - CFM ≥15 across heatsink fins
  - Intake from chassis bottom vents
  - Exhaust through rear or side
  - Fan mounting integrated with duct
- **Priority:** P1 (Critical)
- **Deliverable:** CFD simulation results, STEP file

#### REQ-MECH-04: Glass Cooktop Panel
- **Description:** Specify or source glass-ceramic cooktop panel for RCA 12A3 opening
- **Rationale:** Standard cooktop glass required for induction operation
- **Acceptance Criteria:**
  - Schott Ceran or equivalent glass-ceramic
  - Thickness 4mm ±0.5mm
  - Withstands 300°C continuous, 500°C peak
  - Dimensions to fit 12A3 top panel cutout
- **Priority:** P1 (Critical)
- **Deliverable:** Supplier and part number, or custom cut specification

### 4.3 User Interface

#### REQ-UI-01: Multi-Mode Encoder Interface
- **Description:** Implement complex state control using single rotary encoder with push button
- **Rationale:** Vintage aesthetic precludes TFT screen; must map Control Freak functionality to minimal UI
- **Acceptance Criteria:**
  - Short press: Start/Stop
  - Long press (2s): Enter settings mode
  - Rotate in normal mode: Adjust temperature
  - Rotate in settings mode: Cycle through (Temp → Intensity → Timer → Profile)
  - LED color/pattern indicates current mode
- **Priority:** P2 (High)
- **Affected Files:** `main/ui.c` (new), `user_interface.kicad_sch`

#### REQ-UI-02: LED Status Encoding
- **Description:** Define LED patterns to communicate system state without display
- **Rationale:** Must convey temperature, intensity, faults, and mode with limited LEDs
- **Acceptance Criteria:**
  - Define patterns for: Heating, At-temp, Cooling, Fault (by type)
  - Intensity level shown as LED brightness or blink rate
  - Temperature shown as color gradient (cool blue → hot red) if RGB LED available
- **Priority:** P2 (High)
- **Deliverable:** LED encoding specification document

#### REQ-UI-03: Web-Based Companion Interface
- **Description:** Implement ESP32 web server for advanced configuration via smartphone/tablet
- **Rationale:** Complex features (profiles, PID tuning, diagnostics) cannot fit on minimal physical UI
- **Acceptance Criteria:**
  - Responsive web UI served from ESP32 flash
  - Real-time temperature graph (WebSocket updates)
  - Profile editor with drag-and-drop stages
  - PID tuning interface with live preview
  - OTA firmware update capability
- **Priority:** P3 (Medium)
- **Affected Files:** New `components/webui/`

### 4.4 Safety Enhancements

#### REQ-SAFETY-01: Low-Power Pan Detection
- **Description:** Ensure pan detection algorithm works reliably at low power levels required for 30°C operation
- **Rationale:** Standard impedance-based detection may be unreliable at <100W
- **Acceptance Criteria:**
  - Pan detection works at 50W power level
  - False positive rate <1% (empty detection as pan present)
  - False negative rate <1% (pan present detected as empty)
- **Priority:** P1 (Critical)
- **Affected Files:** `state_machine.c`, possibly hardware changes to sensing circuit

#### REQ-SAFETY-02: Probe Insertion Detection
- **Description:** Detect when liquid probe is inserted into food vs. dangling in air
- **Rationale:** Cascade control must not use air temperature as liquid temperature
- **Acceptance Criteria:**
  - Detect thermal mass at probe tip (rate of change analysis)
  - Warn user if probe appears to be in air during cascade mode
  - Graceful fallback to single-loop control
- **Priority:** P2 (High)
- **Affected Files:** `sensing.c`, `cascade_pid.c`

---

## 5. Requirements Traceability Matrix

| Req ID | Category | Priority | Depends On | Blocks |
|--------|----------|----------|------------|--------|
| REQ-FW-01 | Firmware | P1 | REQ-SAFETY-01 | REQ-FW-03 |
| REQ-FW-02 | Firmware | P1 | - | - |
| REQ-FW-03 | Firmware | P1 | REQ-FW-01 | REQ-FW-05 |
| REQ-FW-04 | Firmware | P2 | - | - |
| REQ-FW-05 | Firmware | P2 | REQ-FW-03, REQ-UI-03 | - |
| REQ-FW-06 | Firmware | P2 | - | - |
| REQ-MECH-01 | Mechanical | P1 | - | REQ-FW-01 |
| REQ-MECH-02 | Mechanical | P1 | - | - |
| REQ-MECH-03 | Mechanical | P1 | - | - |
| REQ-MECH-04 | Mechanical | P1 | - | REQ-MECH-01 |
| REQ-UI-01 | UI | P2 | - | - |
| REQ-UI-02 | UI | P2 | - | REQ-UI-01 |
| REQ-UI-03 | UI | P3 | - | REQ-FW-05 |
| REQ-SAFETY-01 | Safety | P1 | - | REQ-FW-01 |
| REQ-SAFETY-02 | Safety | P2 | REQ-FW-03 | - |

---

## 6. Implementation Roadmap

### Phase 1: Core Control Freak Features (P1)
**Timeline:** 4-6 weeks
1. REQ-SAFETY-01: Low-power pan detection validation
2. REQ-FW-01: Extend temperature range to 30°C
3. REQ-FW-02: Implement intensity control
4. REQ-FW-03: Implement cascade control
5. REQ-MECH-01 through REQ-MECH-04: Mechanical design

### Phase 2: Enhanced Control (P2)
**Timeline:** 3-4 weeks
1. REQ-FW-04: Thermal mass estimation
2. REQ-FW-06: Fan speed control
3. REQ-UI-01: Multi-mode encoder
4. REQ-UI-02: LED encoding
5. REQ-SAFETY-02: Probe insertion detection

### Phase 3: Advanced Features (P3)
**Timeline:** 4-6 weeks
1. REQ-FW-05: Cooking profiles
2. REQ-UI-03: Web companion interface

---

## 7. Open Questions

1. **Glass Sourcing:** Can we source Schott Ceran in small quantities, or do we need an alternative material?

2. **Coil Winding:** Will we wind custom coils or source pre-wound? This affects REQ-MECH-02 dimensions.

3. **UI Philosophy:** Is the web interface (REQ-UI-03) acceptable as the primary way to access advanced features, or do we need more physical controls?

4. **Certification Path:** Are we targeting any safety certifications (UL, CE)? This affects design decisions.

5. **RCA 12A3 Variants:** Are there multiple 12A3 chassis variants we need to support, or a single reference chassis?

---

## 8. References

| Document | Purpose |
|----------|---------|
| `firmware/README.md` | Firmware architecture and API |
| `BOM.md` | Bill of materials |
| `PCB_SPECIFICATION.md` | PCB design constraints |
| `RESONANT_TANK_DESIGN.md` | LC tank calculations |
| `SAFETY_INTERLOCK_DESIGN.md` | Hardware safety system |
| `THERMAL_DESIGN_GUIDE.md` | Thermal management |
| Breville Control Freak Manual | Reference for feature parity |

---

## 9. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-16 | AI Assistant | Initial requirements analysis |

---

**END OF DOCUMENT**
