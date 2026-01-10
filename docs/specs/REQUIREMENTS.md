# Temper Induction Cooker - System Requirements Specification

**Version:** 1.0  
**Date:** 2025-12-17  
**Status:** Active  
**Target:** Breville Control Freak Clone in RCA 12A3 Chassis

---

## Document Purpose

This document defines the complete system requirements for the Temper induction cooker project. It serves as the authoritative source for all design decisions, validation criteria, and acceptance testing.

**Related Documents:**
- `PROJECT_STATUS_20251216.md` - Gap analysis and feature comparison
- `PCB_SPECIFICATION.md` - PCB fabrication and assembly requirements
- `SAFETY_INTERLOCK_DESIGN.md` - Hardware safety system specification
- `THERMAL_DESIGN_GUIDE.md` - Thermal management requirements

---

## 1. System Requirements (REQ-SYS)

### REQ-SYS-01: Power Input Compatibility
**Priority:** P0 (Critical)  
**Status:** UPDATED - Changed from 2.0kW to 1.8kW

| Parameter | Requirement | Rationale |
|-----------|-------------|-----------|
| **Max Output Power** | 1.8 kW | Standard 15A US outlet compatibility |
| **AC Input Voltage** | 120V RMS ±10% | US residential mains |
| **AC Input Frequency** | 60 Hz ±1 Hz | US grid standard |
| **Max Input Current** | 15A continuous | Standard outlet limit |
| **Input Power** | ≤1900W | Includes system losses (~5%) |
| **Power Factor** | ≥0.95 | Minimize reactive power |

**Validation:**
- Measure input current at full load with calibrated clamp meter
- Verify no breaker trips on 15A circuit during 1-hour continuous operation
- Confirm power factor with power analyzer

**Affected Subsystems:**
- DC bus voltage calculations (lower than 2kW design)
- Resonant tank current (reduced from 22A to ~20A peak)
- Thermal budget (reduced losses)
- IGBT stress (reduced)

**Related Issues:** temper-pwr-01 (Power System Redesign Epic)

---

### REQ-SYS-02: Temperature Range
**Priority:** P0 (Critical)  
**Status:** UPDATED - Extended low end from 50°C to 30°C

| Parameter | Requirement | Rationale |
|-----------|-------------|-----------|
| **Minimum Temperature** | 30°C | Chocolate tempering, butter clarification |
| **Maximum Temperature** | 250°C | Searing, high-heat cooking |
| **Setpoint Resolution** | 1°C | User interface granularity |
| **Control Stability (50-250°C)** | ±1°C | Standard cooking applications |
| **Control Stability (30-50°C)** | ±2°C | Low-temperature applications (relaxed) |

**Validation:**
- Hold 35°C setpoint for 30 minutes, measure temperature every 10 seconds
- Verify no thermal runaway false positives at low delta-T
- Test with multiple pan types (cast iron, stainless, aluminum)

**Affected Subsystems:**
- Firmware PID tuning (low-temp gains)
- PWM duty cycle limits (very low duty for 30°C)
- Pan detection algorithm (must work at ~50W)
- Safety thermal runaway detection

**Related Issues:** temper-5xc.1.1 (REQ-FW-01: Extend temperature range to 30°C)

---

### REQ-SYS-03: Operating Environment
**Priority:** P1 (High)

| Parameter | Requirement | Notes |
|-----------|-------------|-------|
| **Ambient Temperature** | 0°C to 40°C | Normal operation, full power |
| **Ambient Temperature (Derated)** | 40°C to 70°C | Reduced power, see derating curve |
| **Ambient Temperature (Shutdown)** | >75°C | Automatic thermal shutdown |
| **Relative Humidity** | 10% to 90% non-condensing | Typical kitchen environment |
| **Altitude** | 0 to 2000m | Standard atmospheric pressure |

**Derating Curve:**

| Ambient (°C) | Max Power (W) | % of Rated |
|--------------|---------------|------------|
| 0-40 | 1800 | 100% |
| 40-50 | 1800 | 100% |
| 50-55 | 1600 | 89% |
| 55-60 | 1350 | 75% |
| 60-65 | 1100 | 61% |
| 65-70 | 700 | 39% |
| 70-75 | 350 | 19% |
| >75 | 0 | **SHUTDOWN** |

**Validation:**
- Thermal testing at 40°C, 50°C, 60°C ambient (if chamber available)
- Monitor junction temperatures at each ambient point
- Verify automatic derating in firmware

---

## 2. Power Electronics Requirements (REQ-PWR)

### REQ-PWR-01: DC Bus Voltage
**Priority:** P0 (Critical)  
**Status:** UPDATED for 1.8kW operation

| Parameter | Requirement | Notes |
|-----------|-------------|-------|
| **Nominal DC Bus** | 170V DC | Full-wave rectified 120VAC |
| **DC Bus Ripple** | <10% | 3300µF capacitance |
| **Transient Peak** | <400V | Includes switching transients |
| **Bulk Capacitance** | 2× 3300µF/250V | Series for voltage rating |

**Validation:**
- Oscilloscope measurement of DC bus ripple at full load
- Capture worst-case transient during turn-off
- Verify capacitor voltage rating margin (>25%)

---

### REQ-PWR-02: Resonant Tank
**Priority:** P0 (Critical)  
**Status:** CRITICAL UPDATE - Capacitor voltage rating insufficient

| Parameter | Requirement | Notes |
|-----------|-------------|-------|
| **Coil Inductance** | 80 µH (uncoupled) | Litz wire spiral coil |
| **Effective Inductance** | 54-64 µH | With pan coupled |
| **Resonant Capacitance** | 330 nF | **UPDATED: Must be 1kV rated** |
| **Resonant Frequency** | 35.8 kHz | Calculated from L and C |
| **Operating Frequency** | 38-50 kHz | Above resonance for ZVS |
| **Peak Capacitor Voltage** | 648V | **EXCEEDS 630V rating** |
| **Capacitor Voltage Rating** | ≥1000V | **CRITICAL: 630V is insufficient** |

**CRITICAL ISSUE IDENTIFIED:**
The simulation shows 648V peak across the resonant capacitor, but the current design specifies 630V rated capacitors. This is a **negative margin** condition that will cause capacitor failure.

**Recommended Solutions:**
1. **Option A (Preferred):** Use 2× 150nF/1kV film capacitors in parallel
   - Total capacitance: 300nF (close to 330nF target)
   - Voltage rating: 1000V (54% margin at 648V peak)
   - Example: WIMA FKP1 series

2. **Option B:** Use single 330nF/1kV film capacitor
   - Exact capacitance match
   - Voltage rating: 1000V (54% margin)
   - May be harder to source

**Validation:**
- Re-run resonant tank simulation with updated capacitance (300nF or 330nF)
- Verify peak voltage <1000V with margin
- Oscilloscope measurement of actual capacitor voltage in prototype

**Related Issues:** 
- temper-pwr-02 (Resonant Capacitor Upgrade)
- temper-sim-01 (Re-run resonant tank simulations)

---

### REQ-PWR-03: Current Sensing
**Priority:** P1 (High)  
**Status:** INCOMPLETE - CT not specified

| Parameter | Requirement | Notes |
|-----------|-------------|-------|
| **Measurement Range** | 0-50A peak | DC bus current |
| **Accuracy** | ±5% | Sufficient for OCP |
| **Bandwidth** | DC to 100 kHz | Capture switching harmonics |
| **Isolation** | Not required | CT provides galvanic isolation |
| **Output Signal** | 0-3.3V | ADC input range |

**Current Transformer Specification:**
- **Turns Ratio:** 1:1000 (or similar)
- **Primary Current:** 50A peak
- **Secondary Current:** 50mA peak
- **Burden Resistor:** 66Ω (for 3.3V output at 50A primary)
- **Frequency Response:** 100 Hz - 100 kHz

**Recommended Parts (Off-the-Shelf):**

| Part Number | Manufacturer | Ratio | Aperture | Price | Notes |
|-------------|--------------|-------|----------|-------|-------|
| **CR8348-2000-N** | CR Magnetics | 1:2000 | 0.5" | ~$25 | Divide burden by 2 for 3.3V |
| **SCT-013-000** | YHDC | 1:2000 | 13mm | ~$10 | Common, may need custom burden |
| **CST-1005** | Coilcraft | 1:1000 | 10mm | ~$15 | Good frequency response |

**Burden Resistor Calculation:**
```
For 1:1000 CT:
  I_secondary = 50A / 1000 = 50mA
  R_burden = 3.3V / 50mA = 66Ω
  P_burden = 3.3V × 50mA = 165mW (use 1/4W resistor)

For 1:2000 CT:
  I_secondary = 50A / 2000 = 25mA
  R_burden = 3.3V / 25mA = 132Ω
  P_burden = 3.3V × 25mA = 82.5mW (use 1/4W resistor)
```

**Validation:**
- Simulate CT + burden + rectifier circuit in SPICE
- Verify linearity across 0-50A range
- Measure actual current with calibrated clamp meter vs CT output

**Related Issues:**
- temper-pwr-03 (Current Transformer Specification)
- temper-sim-02 (CT Sensing Simulation)

---

### REQ-PWR-04: Thermal Budget
**Priority:** P1 (High)  
**Status:** UPDATED for 1.8kW operation

**System Losses at 1.8kW Output:**

| Component | Power Loss (W) | % Total | Cooling Method |
|-----------|----------------|---------|----------------|
| IGBTs (×2) | 36 | 42% | Heatsink + forced air |
| Induction coil | 40 | 47% | Shared airflow |
| LMR51430 buck | 0.9 | 1% | PCB copper pour |
| XC6220 LDO | 0.6 | 0.7% | PCB copper pour |
| Gate drivers | 1.3 | 1.5% | PCB + airflow |
| ESP32 | 0.5 | 0.6% | Natural convection |
| EMI filter | 1.8 | 2.1% | Convection |
| Capacitors (ESR) | 3.5 | 4.1% | Convection |
| **Total** | **~85W** | **100%** | |

**System Efficiency:** 95.5% (1800W output / 1885W input)

**Thermal Limits:**

| Component | Max Tj (°C) | Design Limit (°C) | Margin |
|-----------|-------------|-------------------|--------|
| IKW40N120H3 | 175 | 125 | 50°C |
| UCC21550 | 150 | 120 | 30°C |
| LMR51430 | 150 | 130 | 20°C |
| Coil insulation | 130 (Class B) | 115 | 15°C |

**Cooling System:**
- **Heatsink:** 120×100×40mm extruded aluminum, Rth ≤0.4 K/W with fan
- **Fan:** 80mm, 1500-2000 RPM, 25-35 CFM, <25 dBA
- **TIM:** Thermal paste or graphite pad, <0.2 K/W

**Validation:**
- Thermal imaging at full load (1.8kW for 30 minutes)
- Measure heatsink temperature with thermocouples
- Verify fan airflow with anemometer

**Related Issues:** temper-pwr-04 (Thermal Budget Update)

---

## 3. Control System Requirements (REQ-CTRL)

### REQ-CTRL-01: Low-Temperature Operation
**Priority:** P0 (Critical)  
**Status:** NEW - Required for 30°C minimum

**Challenge:** Induction heating is inherently high-power. Achieving stable 30°C control requires very low power levels (~50W) with fine modulation.

**Recommended Approach: Burst-Mode PWM with Frequency Detuning**

1. **Burst-Mode PWM:**
   - Short heating bursts (100-500ms) with long off-times (1-10s)
   - Duty cycle: 1-10% for 30-50°C range
   - Prevents thermal runaway while allowing fine control

2. **Frequency Detuning:**
   - Operate further from resonance (45-50 kHz vs 38 kHz)
   - Reduces power transfer efficiency intentionally
   - Provides additional power reduction without extreme duty cycles

3. **PID Tuning:**
   - Slower response acceptable at low temperatures (30s time constant)
   - Reduce integral gain to prevent overshoot
   - Add deadband (±0.5°C) to prevent oscillation

**Implementation:**
```c
// firmware/components/control/low_temp_control.c
typedef struct {
    float burst_duration_ms;    // 100-500ms
    float burst_period_ms;      // 1000-10000ms
    float detune_frequency_hz;  // 45000-50000 Hz
    float pid_kp;               // Reduced proportional gain
    float pid_ki;               // Reduced integral gain
    float pid_kd;               // Derivative gain
} LowTempConfig;
```

**Validation:**
- Hold 35°C for 30 minutes, measure stability (±2°C acceptable)
- Verify no thermal runaway false positives
- Test with multiple pan types

**Related Issues:** temper-5xc.1.1 (REQ-FW-01)

---

### REQ-CTRL-02: Temperature Accuracy
**Priority:** P2 (Medium) - Nice-to-have

| Parameter | Requirement | Notes |
|-----------|-------------|-------|
| **Setpoint Accuracy** | ±1°C (50-250°C) | Standard cooking |
| **Setpoint Accuracy** | ±2°C (30-50°C) | Low-temperature (relaxed) |
| **Long-term Stability** | ±0.5°C over 1 hour | After reaching setpoint |
| **Overshoot** | <5°C | During initial heating |

**Note:** The Breville Control Freak claims ±0.1°C stability, but this is likely marketing. Real-world testing shows ±0.5-1°C is more realistic for induction systems.

---

### REQ-CTRL-03: Power Modulation
**Priority:** P2 (Medium) - Nice-to-have

| Parameter | Requirement | Notes |
|-----------|-------------|-------|
| **Intensity Levels** | 10 discrete levels | User-selectable heat rate |
| **Intensity Range** | 10% to 100% | Level 1 = 180W, Level 10 = 1800W |
| **Modulation Method** | PWM duty cycle | 10-100% duty at fixed frequency |

**Related Issues:** temper-5xc.1.2 (REQ-FW-02: Intensity control)

---

## 4. Safety Requirements (REQ-SAFETY)

### REQ-SAFETY-01: Overcurrent Protection
**Priority:** P0 (Critical)

| Parameter | Requirement | Notes |
|-----------|-------------|-------|
| **OCP Threshold** | 50A peak | 2.5V CT output |
| **Response Time** | <1 µs | Hardware comparator |
| **Fault Action** | Immediate shutdown | Latch until power cycle |

**Implementation:**
- TLV3201 comparator (33ns propagation delay)
- Hardware fault latch (independent of MCU)
- LED indicator for OCP fault

---

### REQ-SAFETY-02: Thermal Protection
**Priority:** P0 (Critical)

| Location | Sensor | Warning (°C) | Shutdown (°C) |
|----------|--------|--------------|---------------|
| Heatsink | NTC 10kΩ | 75 | 95 |
| Coil area | NTC 10kΩ | 90 | 115 |
| Enclosure | NTC 10kΩ | 65 | 75 |
| Thermal fuse | TCO 130°C | - | 130 (irreversible) |

---

### REQ-SAFETY-03: Isolation and Clearance
**Priority:** P0 (Critical)

**IEC 60335-2-6 Compliance:**

| Boundary | Insulation | Working V | Min Required | Design Value |
|----------|------------|-----------|--------------|--------------|
| AC Mains to SELV | Reinforced | 340V pk | 5.0mm | 8.0mm |
| DC Bus to SELV | Reinforced | 400V pk | 5.0mm | 8.0mm |
| Gate Iso to SELV | Reinforced | 355V | 5.0mm | 8.0mm |

**PCB Isolation Slot:**
- Width: 2.0mm minimum
- Creepage enhancement: 2 × 2.0mm + surface = 8mm effective
- Keep-out: 6mm each side (no copper)

---

### REQ-SAFETY-04: Testing Requirements
**Priority:** P1 (High)  
**Status:** NEW - Define testing procedures

**Pre-Power-On Checklist:**
1. Visual inspection (solder joints, component orientation)
2. Continuity test (ground connections)
3. Isolation test (mains to SELV with megohmmeter)
4. Polarity check (DC bus capacitors, diodes)

**Power-On Testing:**
1. **Low-Voltage Test (12V supply):**
   - Verify 5V and 3.3V rails
   - Check MCU boot and LED indicators
   - Verify SPI/I2C communication

2. **Hi-Pot Test:**
   - Mains to SELV: 3000V AC for 1 minute, <5mA leakage
   - DC Bus to SELV: 3000V AC for 1 minute, <5mA leakage

3. **Ground Continuity:**
   - Measure resistance from PE to all exposed metal (<0.1Ω)

4. **Leakage Current:**
   - Touch current: <3.5mA (IEC 60335-1 limit)
   - Measured with Y-caps installed

**Recommended Equipment:**

| Test | Equipment | Approx. Cost | Notes |
|------|-----------|--------------|-------|
| Hi-Pot | Fluke 1507 or equivalent | $300-500 | 1000V insulation tester |
| Ground Continuity | Fluke 87V multimeter | $400 | 4-wire resistance mode |
| Leakage Current | Extech 380260 | $150 | AC leakage clamp meter |
| Oscilloscope | Rigol DS1054Z | $350 | For waveform verification |

**Related Issues:** temper-safety-01 (Safety Testing Infrastructure)

---

## 5. Mechanical Requirements (REQ-MECH)

### REQ-MECH-01: Chassis Integration
**Priority:** P1 (High)  
**Status:** INCOMPLETE - No CAD files

**RCA 12A3 Chassis Dimensions:**
- External: ~230mm W × 180mm D × 120mm H (approximate, needs verification)
- Internal clearance: TBD
- Mounting holes: TBD

**Action Items:**
1. Source RCA 12A3 chassis dimensions (online or measure physical unit)
2. Create 3D model of chassis interior
3. Design mounting brackets for PCB, coil, heatsink
4. Verify clearances for all components

**Related Issues:** temper-5xc.2 (Mechanical Integration Epic)

---

### REQ-MECH-02: Cooling System
**Priority:** P1 (High)

| Parameter | Requirement | Notes |
|-----------|-------------|-------|
| **Heatsink** | 120×100×40mm | Extruded aluminum |
| **Heatsink Rth** | ≤0.4 K/W | With forced air |
| **Fan** | 80mm, 1500-2000 RPM | <25 dBA |
| **Airflow** | 25-35 CFM | Measured with anemometer |
| **Ducting** | Direct airflow over coil | Shared cooling |

**Related Issues:** temper-5xc.2.3 (REQ-MECH-03: Chassis airflow ducting)

---

## 6. User Interface Requirements (REQ-UI)

### REQ-UI-01: Physical Controls
**Priority:** P2 (Medium)

| Control | Type | Function |
|---------|------|----------|
| **Encoder** | Rotary with push | Temperature setpoint, menu navigation |
| **Power Button** | Momentary | System on/off |
| **Start/Stop** | Momentary | Begin/pause heating |
| **Display** | Small OLED/LCD | Temperature, status, mode |

**Vintage Aesthetic:**
- Knobs should match RCA 12A3 era (1950s)
- Consider backlit analog-style dial for temperature
- Minimal LEDs (power, heating, fault)

**Related Issues:** temper-5xc.3 (User Interface Epic)

---

### REQ-UI-02: Debug Interface
**Priority:** P1 (High)

| Interface | Purpose | Notes |
|-----------|---------|-------|
| **USB Serial** | Firmware debug, logging | ESP32 USB-to-UART |
| **JTAG** | Firmware programming | Tag-Connect TC2030 |
| **Web Interface** | Advanced configuration | ESP32 WiFi (future) |

---

## 7. EMI/EMC Requirements (REQ-EMC)

### REQ-EMC-01: Conducted Emissions
**Priority:** P1 (High)

**Applicable Standard:** EN 55014-1 (Household Appliances)

| Frequency Range | Quasi-Peak Limit | Average Limit |
|-----------------|------------------|---------------|
| 150 kHz - 500 kHz | 66 dBµV | 56 dBµV |
| 500 kHz - 5 MHz | 56 dBµV | 46 dBµV |
| 5 MHz - 30 MHz | 60 dBµV | 50 dBµV |

**EMI Filter Design:**
- DM inductor: 470 µH, 15A
- CM choke: 10 mH, 15A
- X2 capacitors: 470 nF, 275VAC
- Y2 capacitors: 2.2 nF, 300VAC (touch current <0.35mA)
- MOV: 275V, 10kA surge rating

**ZVS Benefit:** Zero-voltage switching reduces dV/dt from 50-100 V/ns to <0.1 V/ns, providing ~40 dB EMI reduction.

---

### REQ-EMC-02: Pre-Compliance Testing
**Priority:** P2 (Medium)  
**Status:** NEW - Define DIY testing approach

**Recommended Approach (Without EMC Chamber):**

1. **DIY Near-Field Probe:**
   - Build H-field probe (wire loop) and E-field probe (monopole)
   - Use spectrum analyzer or SDR (RTL-SDR + software)
   - Scan around PCB to identify hotspots

2. **LISN (Line Impedance Stabilization Network):**
   - Purchase or build 50Ω LISN
   - Measure conducted emissions with spectrum analyzer
   - Compare to EN 55014-1 limits

3. **Iterative Improvement:**
   - Identify worst frequencies
   - Add/adjust filtering
   - Re-measure until below limits

**Equipment:**
- Spectrum analyzer or RTL-SDR: $50-500
- LISN: $200-1000 (or DIY for ~$50)
- Near-field probes: DIY (~$20 in parts)

**Related Issues:** temper-emc-01 (EMI Pre-Compliance Testing)

---

## 8. Requirements Traceability Matrix

| Requirement | Priority | Status | Related bd Issues | Validation Method |
|-------------|----------|--------|-------------------|-------------------|
| REQ-SYS-01 | P0 | UPDATED | temper-pwr-01 | Current measurement |
| REQ-SYS-02 | P0 | UPDATED | temper-5xc.1.1 | Temperature hold test |
| REQ-SYS-03 | P1 | ACTIVE | - | Thermal chamber (if available) |
| REQ-PWR-01 | P0 | UPDATED | temper-pwr-01 | Oscilloscope |
| REQ-PWR-02 | P0 | CRITICAL | temper-pwr-02, temper-sim-01 | Simulation + prototype |
| REQ-PWR-03 | P1 | INCOMPLETE | temper-pwr-03, temper-sim-02 | CT simulation + test |
| REQ-PWR-04 | P1 | UPDATED | temper-pwr-04 | Thermal imaging |
| REQ-CTRL-01 | P0 | NEW | temper-5xc.1.1 | Low-temp hold test |
| REQ-CTRL-02 | P2 | ACTIVE | - | Temperature logging |
| REQ-CTRL-03 | P2 | ACTIVE | temper-5xc.1.2 | User testing |
| REQ-SAFETY-01 | P0 | ACTIVE | - | OCP injection test |
| REQ-SAFETY-02 | P0 | ACTIVE | - | Thermal trip test |
| REQ-SAFETY-03 | P0 | ACTIVE | - | Hi-pot test |
| REQ-SAFETY-04 | P1 | NEW | temper-safety-01 | Test procedure execution |
| REQ-MECH-01 | P1 | INCOMPLETE | temper-5xc.2 | CAD model + fit check |
| REQ-MECH-02 | P1 | ACTIVE | temper-5xc.2.3 | Airflow measurement |
| REQ-UI-01 | P2 | ACTIVE | temper-5xc.3 | User testing |
| REQ-UI-02 | P1 | ACTIVE | - | Debug session |
| REQ-EMC-01 | P1 | ACTIVE | - | LISN measurement |
| REQ-EMC-02 | P2 | NEW | temper-emc-01 | Pre-compliance test |

---

## 9. Acceptance Criteria

### Minimum Viable Product (MVP)

**Must-Have (P0):**
- ✅ 1.8kW maximum power at 120VAC/15A
- ✅ 30°C-250°C temperature range
- ✅ ±2°C stability at 30-50°C, ±1°C at 50-250°C
- ✅ All safety interlocks functional (OCP, OVP, thermal)
- ✅ Resonant capacitor rated ≥1kV (648V peak)
- ✅ Current transformer specified and simulated
- ✅ Hi-pot test passed (3000V AC, <5mA leakage)

**Should-Have (P1):**
- ✅ Mechanical integration in RCA 12A3 chassis
- ✅ Thermal budget validated at 40°C ambient
- ✅ Safety testing procedure documented
- ✅ EMI pre-compliance testing completed

**Nice-to-Have (P2):**
- 10-level intensity control
- Cascade control (pan + liquid)
- Web interface for advanced configuration
- Cooking profiles

---

## 10. Change Log

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-12-17 | Initial requirements document | AI Agent |
| | | - Updated power from 2.0kW to 1.8kW | |
| | | - Extended temperature range to 30°C | |
| | | - Identified resonant capacitor issue (630V → 1kV) | |
| | | - Specified current transformer requirements | |
| | | - Added safety testing procedures | |
| | | - Added low-temperature control strategy | |

---

## 11. References

- `PROJECT_STATUS_20251216.md` - Gap analysis
- `PCB_SPECIFICATION.md` - PCB requirements
- `SAFETY_INTERLOCK_DESIGN.md` - Safety system
- `THERMAL_DESIGN_GUIDE.md` - Thermal management
- `RESONANT_TANK_DESIGN.md` - Resonant tank design
- IEC 60335-2-6 - Safety standard for cooking appliances
- EN 55014-1 - EMC standard for household appliances
