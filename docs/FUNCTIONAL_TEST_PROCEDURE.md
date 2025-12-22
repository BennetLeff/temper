# Functional Test Procedure: Temper PCBA

## 1. Scope
This document outlines the testing steps required to validate a fully assembled Temper Power Board (Rev A) before it is integrated into the final chassis.

## 2. Test Equipment
- Lab Power Supply (0-30V, 5A)
- Digital Multimeter (DMM)
- 4-Channel Oscilloscope (≥ 100MHz)
- HV Differential Probe
- Current Probe
- USB-to-Serial Adapter (if not using onboard USB)
- Electronic Load (optional)

## 3. Test Stages

### Step 1: Resistance Checks (Unpowered)
- **Net: VCC_3V3 to GND**: > 1 kΩ
- **Net: VCC_15V to GND**: > 500 Ω
- **Net: DC_BUS+ to DC_BUS-**: > 100 kΩ (Check bleed resistors)
- **Net: AC_L to AC_N**: Open (Check fuse and relay state)

### Step 2: Logic Power Validation
1. Apply 15V to the auxiliary power input.
2. Measure voltage at TP_3V3. Expect **3.3V ± 0.1V**.
3. Check MCU heartbeat LED (if applicable).
4. Verify UART output for "Booting Temper..." message.

### Step 3: Gate Drive Characterization
1. Enable PWM in "Test Mode" via firmware console.
2. Probe `GATE_H` vs `SWITCH_NODE`.
3. Probe `GATE_L` vs `DC_BUS-`.
4. **Pass Criteria**:
   - V_gs_peak = 15V ± 1V.
   - V_gs_off = -5V ± 1V (if using negative bias).
   - Dead-time = 300ns ± 50ns.
   - Clean edges with < 10% overshoot.

### Step 4: Safety Interlock Verification
1. **OCP Test**: Inject a 3.5V signal into `I_SENSE`. Verify `SHUTDOWN_N` goes LOW and `FAULT` status is reported.
2. **OVP Test**: Apply 400V equivalent to `V_BUS_SENSE` divider. Verify shutdown.
3. **Thermal Test**: Heat the NTC or short it. Verify shutdown.
4. **Watchdog Test**: Stop the "kick" signal from firmware. Verify system resets or locks out within 1.6s.

### Step 5: Resonant Tank (Low Voltage)
1. Connect induction coil.
2. Apply 30V DC to `DC_BUS+`.
3. Set PWM to 40kHz (above resonance).
4. Observe `SWITCH_NODE` waveform.
5. Sweep frequency down toward 33kHz.
6. Verify **Zero Voltage Switching (ZVS)**: The switch node should reach 0V before the high-side IGBT turns on.

### Step 6: Full Power Verification (High Voltage)
**DANGER: LETHAL VOLTAGES PRESENT.**
1. Connect 120VAC via isolation transformer and variac.
2. Slowly ramp from 0V to 120V.
3. Monitor `I_SENSE` and `DC_BUS` in firmware.
4. Verify resonant frequency tracking (PLL) maintains ZVS as the pan is moved.
5. Measure power consumption. At 120V, verify up to 1800W capability.

## 4. Documentation
Record all measurements in the `SAFETY_TEST_LOG_TEMPLATE.md`.
Any board failing Step 3 or 4 must be quarantined for repair.
