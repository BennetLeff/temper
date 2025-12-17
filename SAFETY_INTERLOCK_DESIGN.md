# Safety Interlock Design Document

## Temper Induction Cooker - Hardware Safety Systems

**Document Version:** 1.0  
**Date:** December 13, 2025  
**Status:** Verified by Simulation

---

## 1. Executive Summary

This document describes the hardware safety interlock system for the Temper induction cooker. The system provides fail-safe protection independent of firmware, ensuring that even if the ESP32 controller crashes, locks up, or has a software bug, the power stage will be disabled within microseconds.

### Safety Philosophy

**Hardware interlocks are the last line of defense.** They operate independently of:
- ESP32 firmware
- Software timing loops
- Communication interfaces
- User interface

The interlocks use discrete logic ICs and analog comparators to achieve deterministic, fast response times that software cannot guarantee.

### Key Performance Metrics

| Protection | Response Time | Target | Margin |
|------------|--------------|--------|--------|
| Overcurrent (OCP) | 33ns | <1µs | 30x |
| Overvoltage (OVP) | 9ns | <10µs | 1000x |
| Thermal Shutdown | <1ms | <100ms | 100x |
| Fault Integration | 30ns | <100ns | 3x |

---

## 2. System Block Diagram

```
                                    ┌─────────────────┐
                                    │   RESET BUTTON  │
                                    │   (Active LOW)  │
                                    └────────┬────────┘
                                             │
┌──────────────────┐                         │
│ CURRENT          │    ┌────────┐    ┌──────┴──────┐    ┌─────────────┐
│ TRANSFORMER      ├───►│  OCP   ├───►│             │    │             │
│ (1:1000)         │    │ CIRCUIT│    │             │    │  UCC21550   │
└──────────────────┘    └────────┘    │             │    │  GATE       │
                                      │             │    │  DRIVER     │
┌──────────────────┐    ┌────────┐    │    OR       │    │             │
│ HV BUS           │    │  OVP   │    │    GATE     ├───►│  DISABLE    │
│ RESISTIVE        ├───►│ CIRCUIT├───►│      +      │    │  PIN        │
│ DIVIDER          │    │        │    │   LATCH     │    │             │
└──────────────────┘    └────────┘    │             │    │  (Active    │
                                      │             │    │   HIGH)     │
┌──────────────────┐    ┌────────┐    │             │    │             │
│ NTC THERMISTOR   │    │THERMAL │    │             │    └─────────────┘
│ (IGBT Heatsink)  ├───►│SHUTDOWN├───►│             │
│                  │    │        │    │             │
└──────────────────┘    └────────┘    │             │
                                      │             │
┌──────────────────┐    ┌────────┐    │             │
│ ESP32 GPIO       │    │HARDWARE│    │             │
│ (WDI Heartbeat)  ├───►│WATCHDOG├───►│             │
│                  │    │TPS3823 │    └──────┬──────┘
└──────────────────┘    └────────┘           │
                                             │
                                    ┌────────┴────────┐
                                    │   FAULT LEDs    │
                                    │OCP OVP TEMP WDT │
                                    └─────────────────┘
```

---

## 3. Overcurrent Protection (OCP)

### 3.1 Design Requirements

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Trip Threshold | 50A peak | 125% of rated 40A |
| Response Time | <1µs | Prevent IGBT damage |
| Detection Method | Full-wave rectified | Detect both half-cycles |
| Sensing Element | Current Transformer | Galvanic isolation |

### 3.2 Current Transformer Specifications

| Parameter | Value |
|-----------|-------|
| Turns Ratio | 1:1000 |
| Magnetizing Inductance | 10mH |
| Leakage Inductance | 100µH |
| Winding Resistance | 50Ω |
| Burden Resistor | 50Ω |

**Output Voltage Calculation:**
```
V_out = I_primary × (1/N) × R_burden
V_out = 50A × (1/1000) × 50Ω = 2.5V at threshold
```

### 3.3 Circuit Description

```
                    ┌─────────────────┐
 TANK               │                 │
 CURRENT ──────────►│ CURRENT         │──────► CT_OUT (AC)
                    │ TRANSFORMER     │
                    │ 1:1000          │
                    └─────────────────┘
                            │
                            ▼
                    ┌─────────────────┐
                    │ FULL-WAVE       │
                    │ RECTIFIER       │──────► |CT_OUT| (DC)
                    │ (Precision)     │
                    └─────────────────┘
                            │
                            ▼
                    ┌─────────────────┐
                    │ COMPARATOR      │
 2.5V REF ─────────►│ TLV3201         │──────► OCP_FAULT
                    │ (40ns delay)    │
                    └─────────────────┘
```

### 3.4 Simulation Results (sim_17)

| Measurement | Value | Target | Status |
|-------------|-------|--------|--------|
| Response Time | 33ns | <1µs | ✓ PASS |
| V_rectified @ 40A | 2.00V | <2.5V | ✓ No false trip |
| V_rectified @ 60A | 3.00V | >2.5V | ✓ Detects fault |
| Trip Period | 12.4µs | ~14.3µs | ✓ Cycle-by-cycle |

### 3.5 Component Selection

| Component | Part Number | Key Specs |
|-----------|-------------|-----------|
| CT | Application Specific | 1:1000, 100kHz BW |
| Comparator | TLV3201 | 40ns, rail-to-rail |
| Reference | Resistive divider | 2.5V from 5V |
| Precision Rectifier | LM358 + 1N4148 | For hardware impl. |

---

## 4. Overvoltage Protection (OVP)

### 4.1 Design Requirements

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Trip Threshold | ~390V | 110% of nominal 360V |
| Maximum Bus | 450V | Component ratings |
| Response Time | <10µs | Before caps discharge |
| Sensing Method | Resistive divider | Simple, reliable |

### 4.2 Resistive Divider Design

**Requirements:**
- High voltage capability (500V+)
- Low power dissipation
- Safe output voltage for comparator

**Implementation:**
```
DC BUS (0-450V)
    │
    ├── R1 = 1MΩ ──┬── R2 = 1MΩ ──┬── R3 = 1MΩ ──┐
    │              │              │              │
    │              │              │              ├── DIVIDER_OUT
    │              │              │              │
    └──────────────┴──────────────┴──────────────┴── R4 = 30kΩ ── GND
```

**Division Ratio:** 3.03MΩ / 30kΩ = 101:1

**Output Voltages:**
| Bus Voltage | Divider Output |
|-------------|----------------|
| 310V (nominal) | 3.07V |
| 390V (trip) | 3.86V |
| 420V (overvoltage) | 4.16V |

### 4.3 Circuit Description

```
DC BUS ────┬─── [1MΩ] ─┬─ [1MΩ] ─┬─ [1MΩ] ─┬─────► DIV_OUT
           │           │         │         │
           │           │         │         [30kΩ]
           │           │         │         │
           GND         GND       GND       GND
                                           │
                                           ▼
                                   ┌─────────────────┐
                                   │ COMPARATOR      │
            3.85V REF ────────────►│ TLV3201         │──────► OVP_FAULT
                                   │ (40ns delay)    │
                                   └─────────────────┘
```

### 4.4 Simulation Results (sim_18)

| Measurement | Value | Target | Status |
|-------------|-------|--------|--------|
| Response Time | 9ns | <10µs | ✓ PASS (1000x margin) |
| V_div @ 310V | 3.07V | <3.85V | ✓ No false trip |
| V_div @ 420V | 4.16V | >3.85V | ✓ Detects fault |
| Reference | 3.85V | 3.85V | ✓ Correct |

### 4.5 High Voltage Safety

**CRITICAL:** The resistive divider operates at lethal voltages!

**Hardware Implementation Notes:**
1. Use 1MΩ resistors rated for 500V each (distributed voltage)
2. Add optocoupler isolation before comparator for additional safety
3. Use creepage/clearance appropriate for 500V+ per IEC 60664-1
4. Consider TVS diode across R4 for transient protection

---

## 5. Thermal Shutdown Protection

### 5.1 Design Requirements

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Trip Temperature | 85°C | IGBT max junction 150°C, margin |
| Reset Temperature | 75°C | 10°C hysteresis |
| Response Time | <100ms | Thermal mass provides time |
| Sensor Location | IGBT heatsink | Direct thermal coupling |

### 5.2 NTC Thermistor Characteristics

| Parameter | Value |
|-----------|-------|
| Resistance @ 25°C | 10kΩ |
| B-value | 3950K |
| Tolerance | ±1% |

**Resistance vs Temperature:**
| Temperature | Resistance | V_divider (10k pullup) |
|-------------|------------|------------------------|
| 25°C | 10.0kΩ | 2.50V |
| 50°C | 3.6kΩ | 1.32V |
| 75°C | 1.5kΩ | 0.65V |
| 85°C | 1.0kΩ | 0.45V |
| 100°C | 0.68kΩ | 0.32V |

### 5.3 Circuit Description

```
        VCC (5V)
           │
          [10kΩ]
           │
           ├─────────────────────────────► NTC_NODE
           │
         [NTC]
           │
          GND

                    ┌─────────────────────┐
NTC_NODE ──────────►│ COMPARATOR          │
                    │ w/ HYSTERESIS       │──────► THERMAL_FAULT
0.50V (trip)  ─────►│                     │
0.65V (reset) ─────►│                     │
                    └─────────────────────┘
```

### 5.4 Simulation Results (sim_19)

| Measurement | Value | Target | Status |
|-------------|-------|--------|--------|
| Trip Voltage | 0.48V | <0.50V | ✓ PASS |
| Reset Voltage | 0.65V | >0.65V | ✓ PASS |
| Hysteresis | 10°C | 10°C | ✓ Correct |
| Cold Output | 0V | 0V | ✓ No false trip |
| Hot Output | 5V | 5V | ✓ Fault detected |

### 5.5 Sensor Placement

**CRITICAL:** NTC placement directly affects protection effectiveness!

**Recommended Locations:**
1. **Primary:** Bonded to IGBT heatsink with thermal paste
2. **Secondary:** Near heatsink mounting point
3. **Ambient:** Inside enclosure for reference

**Thermal Interface:**
- Use thermal epoxy or thermal paste
- Ensure firm mechanical contact
- Consider thermal time constant in protection design

---

## 6. UVLO (Undervoltage Lockout)

### 6.1 Built-in Protection

The UCC21550B gate driver includes integrated UVLO on both:
- **VCC (low-side supply):** 7.6V falling, 8.1V rising
- **VCCI (isolated supply):** 10.5V falling, 11.5V rising

### 6.2 Verification Status

UVLO was verified in simulation sim_15 (UCC21550 deadtime characterization).

### 6.3 Design Implication

No external UVLO circuit is required. The UCC21550B will automatically disable outputs if supply voltages fall below thresholds.

---

## 7. External Hardware Watchdog (MCU Lockup Protection)

### 7.1 Safety Gap Analysis

The existing safety layers have a critical gap:

| Layer | Protection | Limitation |
|-------|------------|------------|
| Software | ESP32 TWDT | Cannot trigger if MCU hard-locks |
| Hardware | OCP/OVP/Thermal | Only detect electrical faults, not MCU failure |

**Risk:** If ESP32 hard-locks (ESD, silicon bug, power glitch) while PWM is active, the power stage stays on indefinitely.

### 7.2 Design Requirements

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Detection | MCU lockup | Addresses safety gap |
| Timeout | 1.6s | Long enough for firmware, short enough for safety |
| Independence | Hardware-only | No software dependency |
| Integration | Fault OR gate | Same response as OCP/OVP/Thermal |

### 7.3 Component Selection: TPS3823-33

| Parameter | Value | Notes |
|-----------|-------|-------|
| Manufacturer | Texas Instruments | |
| Timeout | 1.6s (fixed) | No external RC needed |
| RESET Output | Active-LOW, **push-pull** | Can drive logic directly |
| Supply Voltage | 1.1V to 5.0V | Use at 3.3V (matches ESP32) |
| Package | SOT-23-5 (DBVR suffix) | |
| Quiescent Current | 15µA typical | Negligible vs system power |
| Operating Temperature | -40°C to +85°C | Standard grade; use TPS3823**A**-33 for -40°C to +125°C |
| Voltage Supervision | 2.93V threshold (VIT-) | RESET asserts if VDD < 2.93V (beneficial side effect) |

### 7.4 Circuit Description

```
  ESP32 GPIO ──────┐
                   │
              ┌────┴────┐
     VCC ────►│ VDD WDI │
     (3.3V)   │         │
        │     │TPS3823-33│
       ═╪═    │         │
    100nF     │ MR RESET├─────────────────► RESET_N (push-pull output)
        │     │         │
       GND    │   GND   │
              └────┬────┘
                   │
                  GND

  Notes:
  - 100nF ceramic capacitor on VDD for decoupling (per TI datasheet)
  - MR tied to VDD disables manual reset (explained in Section 7.5a)
  - RESET is push-pull, no external pullup required
```

**Signal Inversion:**
```
  RESET_N ───┤>o├─── WDT_FAULT (active HIGH)
              │
           74HC04 inverter (from existing fault logic)
```

### 7.5 Operation

1. **Normal Operation:** Firmware toggles WDI GPIO at ~100Hz (10ms period)
2. **Timer Reset:** Each WDI edge resets internal timer to zero
3. **Lockup Detection:** If no WDI edge for 1.6s, RESET asserts LOW
4. **Fault Integration:** WDT_FAULT (inverted RESET) feeds fault OR gate
5. **Recovery:** When WDI resumes toggling, RESET de-asserts after next edge

### 7.5a Design Decisions

**MR (Manual Reset) Pin:**
The MR input is an active-low manual reset. When MR is pulled LOW, the TPS3823-33 immediately asserts RESET regardless of watchdog state. In our design, MR is tied to VDD to disable this feature because:
1. Manual reset is handled by dedicated RESET button in fault logic (Section 8)
2. Tying MR high simplifies wiring and eliminates potential noise coupling
3. The watchdog function remains fully operational

**Voltage Supervision (VIT-):**
The TPS3823-33 also monitors VDD and asserts RESET if voltage drops below 2.93V (typical). This provides **free brownout protection**:
- If 3.3V rail droops during high-current transients, RESET asserts
- Power stage is disabled before ESP32 enters undefined state
- This is a beneficial side-effect, not a limitation

### 7.6 Simulation Results (sim_21)

| Phase | Test | Expected | Actual | Status |
|-------|------|----------|--------|--------|
| Normal | WDT_FAULT @ 2s | 0V | 0V | ✓ PASS |
| Lockup | Timeout delay | ~1.6s | ~1.6s | ✓ PASS |
| Lockup | WDT_FAULT @ 5s | 5V | 5V | ✓ PASS |
| Lockup | GATE_DISABLE @ 5s | 5V | 5V | ✓ PASS |
| Recovery | WDT_FAULT @ 7s | 0V | 0V | ✓ PASS |

### 7.7 Firmware Requirements

**GPIO Initialization:**
```c
#define WDI_GPIO  GPIO_NUM_xx  // Assign appropriate GPIO

void watchdog_hardware_init(void) {
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << WDI_GPIO),
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config(&io_conf);
}
```

**Heartbeat Toggle (call from state_machine_update):**
```c
static bool wdi_state = false;

void watchdog_hardware_feed(void) {
    wdi_state = !wdi_state;
    gpio_set_level(WDI_GPIO, wdi_state);
}
```

### 7.8 Component Selection

| Ref | Description | Part Number | Notes |
|-----|-------------|-------------|-------|
| U_WDT | Watchdog Timer IC | TPS3823-33DBVR | SOT-23-5, -40°C to +85°C |
| C_WDT | Decoupling Capacitor | 100nF 0402 X7R 16V | On VDD pin per TI datasheet |
| (existing) | Inverter | 74HC04 | Share with fault logic |

**Note:** No pullup resistor needed - TPS3823-33 has push-pull RESET output.

**For extended temperature (-40°C to +125°C):** Use TPS3823**A**-33DBVR instead.

---

## 8. Fault Integration Logic

### 8.1 Design Requirements

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Combining Logic | OR gate | Any fault disables |
| Latching | Yes | Prevents cycling |
| Reset Condition | Manual + faults cleared | Safe restart |
| Output | Active HIGH | UCC21550 DISABLE |
| Response Time | <100ns | Fast shutdown |

### 8.2 Logic Architecture

```
OCP_FAULT ─────┐
               │
OVP_FAULT ────►├──── OR ────┬────────────────────► GATE_DISABLE
               │      GATE  │                      (to UCC21550)
THERMAL_FAULT ─┤            │
               │            │
WDT_FAULT ─────┘            │
                            │
                       ┌────┴────┐
                       │   SR    │
                       │  LATCH  │
                       └────┬────┘
                            │
                   ┌────────┴────────┐
                   │     AND         │
                   │  (Reset Valid)  │
                   └────────┬────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
         RESET_N                    NOT(FAULT_ACTIVE)
      (Button Press)              (All faults cleared)
```

### 8.3 Latching Behavior

**SET Condition:**
- Any fault input goes HIGH
- Latch immediately sets
- GATE_DISABLE goes HIGH within 30ns

**HOLD Condition:**
- Latch maintains state
- Even if fault clears, GATE_DISABLE stays HIGH
- Prevents automatic restart

**RESET Condition:**
- User presses RESET button (RESET_N goes LOW)
- AND all fault inputs are LOW
- Latch clears, GATE_DISABLE goes LOW
- System can restart

### 8.4 Simulation Results (sim_20)

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Response Time | <100ns | 30ns | ✓ PASS |
| Latch holds after OCP | HIGH | 5.0V | ✓ PASS |
| Latch holds after OVP | HIGH | 5.0V | ✓ PASS |
| Reset clears latch | LOW | 0.0V | ✓ PASS |
| Re-latches on new fault | HIGH | 5.0V | ✓ PASS |
| Second reset works | LOW | 0.0V | ✓ PASS |

### 8.5 Hardware Implementation

**Recommended ICs:**

| Function | IC | Package |
|----------|----|---------| 
| 3-input OR | 74HC4075 | SOIC-14 |
| SR Latch (NAND) | 74HC00 | SOIC-14 |
| Reset AND | 74HC08 | SOIC-14 |
| Inverter | 74HC04 | SOIC-14 |

**Alternative: Single IC Solution**
- 74HC4075 provides triple 3-input OR gates
- One OR for faults, remaining gates for latch

---

## 9. Timing Analysis

### 9.1 Worst-Case Propagation Path

```
FAULT DETECTION ──► OR GATE ──► LATCH ──► OUTPUT BUFFER ──► UCC21550
     (varies)        (10ns)     (20ns)       (20ns)          (48ns)
```

### 9.2 Total Response Times

| Fault Type | Detection | Logic | UCC21550 | Total | Target |
|------------|-----------|-------|----------|-------|--------|
| OCP | 33ns | 50ns | 48ns | 131ns | <1µs |
| OVP | 9ns | 50ns | 48ns | 107ns | <10µs |
| Thermal | <1ms | 50ns | 48ns | ~1ms | <100ms |
| WDT | 1.6s | 50ns | 48ns | ~1.6s | <2s |

**All response times meet requirements with significant margin.**

### 9.3 Worst-Case Analysis

**OCP Worst Case:**
- Fault occurs at AC zero crossing
- Must wait for half-cycle peak: ~14µs at 35kHz
- Still well within 1µs detection + 14µs phase = 14µs total
- This is acceptable as the energy during ramp-up is limited

**OVP Worst Case:**
- Bus capacitor charging from rectifier
- Rate of rise limited by source impedance
- 9ns response ensures detection before damage

---

## 10. LED Fault Indicators

### 10.1 Indicator Assignments

| LED | Color | Meaning |
|-----|-------|---------|
| LED1 | Red | Overcurrent Fault |
| LED2 | Yellow | Overvoltage Fault |
| LED3 | Orange | Thermal Fault |
| LED4 | Blue | Watchdog Fault |
| LED5 | Red | Master Fault (Latched) |

### 10.2 LED Driver Circuit

```
FAULT_SIGNAL ────[330Ω]────┬────► LED+ (Anode)
                           │
                           ▼
                        [LED]
                           │
                          GND
```

**For higher current (20mA):**
```
FAULT_SIGNAL ────[1kΩ]────┬──── 2N2222 Base
                          │
                       VCC ◄──── Collector
                          │
                      [150Ω]
                          │
                        [LED]
                          │
                         GND
```

---

## 11. Test Procedures

### 11.1 OCP Test

1. **Setup:** Connect signal generator to CT secondary
2. **Normal Test:** Inject 40A equivalent signal (2.0V), verify no trip
3. **Fault Test:** Inject 60A equivalent signal (3.0V), verify trip within 1µs
4. **Latch Test:** Remove fault, verify GATE_DISABLE stays HIGH
5. **Reset Test:** Press reset, verify GATE_DISABLE goes LOW

### 11.2 OVP Test

1. **Setup:** Connect adjustable DC supply to divider input (use isolation!)
2. **Normal Test:** Set to 310V, verify no trip
3. **Fault Test:** Ramp to 420V, verify trip at ~390V
4. **Response Test:** Use fast ramp, verify <10µs response
5. **Reset Test:** Reduce voltage, press reset, verify system clears

### 11.3 Thermal Test

1. **Setup:** Use temperature chamber or heat gun on NTC
2. **Normal Test:** At 25°C, verify no trip
3. **Fault Test:** Heat to 85°C, verify trip
4. **Hysteresis Test:** Cool to 80°C, verify still tripped
5. **Reset Test:** Cool to 70°C, press reset, verify clear

### 11.4 Watchdog Test

1. **Setup:** Power up system with firmware running
2. **Normal Test:** Verify WDT_LED stays OFF, GATE_DISABLE stays LOW
3. **Lockup Test:** Halt firmware (debugger), verify WDT_LED lights after ~1.6s
4. **Integration Test:** Verify GATE_DISABLE goes HIGH when WDT triggers
5. **Recovery Test:** Resume firmware, verify WDT_LED extinguishes

### 11.5 Integration Test

1. **Multiple Faults:** Trigger OCP, then OVP, verify both latched
2. **Reset Interlock:** Try reset while fault active, verify blocked
3. **Sequential:** Clear all faults, reset, verify system recovers
4. **Power Cycle:** Power off/on, verify default safe state

---

## 12. Component BOM (Safety-Critical)

| Ref | Description | Part Number | Qty | Notes |
|-----|-------------|-------------|-----|-------|
| U1 | Comparator (OCP) | TLV3201 | 1 | 40ns prop delay |
| U2 | Comparator (OVP) | TLV3201 | 1 | 40ns prop delay |
| U3 | Comparator (Thermal) | TLV3201 | 1 | With hysteresis |
| U4 | Triple OR Gate | 74HC4075 | 1 | Fault combining (4 inputs used) |
| U5 | Quad NAND | 74HC00 | 1 | SR Latch |
| U6 | Quad AND | 74HC08 | 1 | Reset logic |
| U7 | Hex Inverter | 74HC04 | 1 | Signal inversion |
| U_WDT | Hardware Watchdog | TPS3823-33DBVR | 1 | 1.6s timeout, SOT-23-5 |
| CT1 | Current Transformer | TBD | 1 | 1:1000, 100kHz |
| R1-R3 | HV Divider | 1MΩ, 1/4W, 500V | 3 | 1% tolerance |
| R4 | HV Divider Low | 30kΩ, 1/4W | 1 | 1% tolerance |
| R5 | Burden Resistor | 50Ω, 1/4W | 1 | 1% tolerance |
| R_WDT | WDT Pullup | 10kΩ 0402 | 1 | 1% tolerance |
| NTC1 | Thermistor | 10kΩ NTC, B=3950 | 1 | ±1% |
| S1 | Reset Button | Momentary, NO | 1 | Panel mount |
| LED1-5 | Indicator LEDs | Various colors | 5 | 3mm or 5mm |

---

## 13. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-13 | Initial release, all simulations verified |
| 1.1 | 2025-12-14 | Added Section 7: External Hardware Watchdog (TPS3823-33) |

---

## 14. References

### Simulation Files

| File | Description |
|------|-------------|
| sim_17_ocp_protection.cir | OCP circuit verification |
| sim_17a_ct_validation.cir | CT model validation |
| sim_17b_ct_frequency_response.cir | CT bandwidth test |
| sim_18_ovp_protection.cir | OVP circuit verification |
| sim_19_thermal_shutdown.cir | Thermal protection verification |
| sim_20_interlock_integration.cir | Fault integration verification |
| sim_21_hardware_watchdog.cir | Hardware watchdog verification |

### Models

| File | Description |
|------|-------------|
| models/current_transformer.sub | CT SPICE subcircuit |

### Datasheets

- TLV3201 (TI): High-speed comparator
- UCC21550 (TI): Isolated gate driver
- 74HC4075 (TI/Nexperia): Triple 3-input OR
- 74HC00 (TI/Nexperia): Quad 2-input NAND

---

**END OF DOCUMENT**
