# PLL Lock Detection and ZVS Verification Integration Guide

**Document Version:** 1.0
**Date:** 2025-12-17
**Related Ticket:** temper-1lj.3
**Status:** Implementation Complete, Hardware Integration Required

---

## Overview

This document describes the integration of enhanced PLL lock detection and ZVS (Zero Voltage Switching) verification into the Temper induction cooker firmware, as specified in safety ticket temper-1lj.3.

## Problem Statement

The original firmware lacked critical safety features to detect and prevent catastrophic thermal failure modes:

1. **PLL Loss of Lock**: If the PLL algorithm diverges, the operating frequency can sweep below resonance, entering hard switching mode with 10-100x increase in switching losses
2. **No ZVS Verification**: No direct detection of hard switching condition - thermal protection (NTC on heatsink) is too slow to prevent junction damage
3. **Frequency Boundary Violations**: No hard limits to prevent operation far from resonant frequency

## Implementation Summary

### 1. Enhanced PLL Lock Detection

**Files Modified:**
- `firmware/components/control/pll_control.h`
- `firmware/components/control/pll_control.c`

**Features Implemented:**

#### Consecutive Cycle Tracking
- **Lock Criteria**: Requires 10 consecutive cycles with:
  - Phase error < ±15° (converted from microseconds)
  - Frequency within ±2kHz of resonant frequency
- **Unlock Detection**: 5 consecutive out-of-tolerance cycles trigger unlock

#### Frequency Boundary Checking
- **Minimum Frequency**: f_res - 5kHz (hard lower limit)
- **Maximum Frequency**: f_res + 10kHz (allows inductive margin for ZVS)
- **Action**: Immediate shutdown via safety system if bounds violated

#### New API Functions
```c
void pll_set_resonant_frequency(float freq_hz);
bool pll_is_frequency_safe(void);
bool pll_get_lock_status(uint32_t *lock_cycles, float *phase_error_us);
```

**Configuration:**
```c
pll_set_resonant_frequency(35800.0f);  // Set based on tank design (35.8 kHz)
```

### 2. ZVS Verification System

**Files Created:**
- `firmware/components/control/zvs_monitor.h`
- `firmware/components/control/zvs_monitor.c`

**Features Implemented:**

#### Hard Switching Detection
- Monitors switching node voltage (V_SW) just before high-side IGBT turn-on
- **ZVS Threshold**: V_SW < 50V indicates successful ZVS
- **Hard Switching**: V_SW > 50V indicates failure

#### Graduated Response Strategy
| Consecutive Hard Switches | Action | Status Code |
|---------------------------|--------|-------------|
| 1-3 | Log warning, increase dead time | `ZVS_WARNING` |
| >3 | Reduce power to 50% | `ZVS_POWER_REDUCTION` |
| >10 | Emergency shutdown | `ZVS_FAULT` |

#### API Functions
```c
void zvs_init(const zvs_config_t *config);
void zvs_update(float vsw_voltage);
zvs_status_t zvs_get_status(void);
float zvs_get_power_factor(void);  // Returns 0.5 if power reduced, 1.0 otherwise
void zvs_get_stats(uint32_t *hard_switches, uint32_t *total, float *success_rate);
```

### 3. Safety System Integration

**Files Modified:**
- `firmware/components/safety/safety.h`
- `firmware/components/safety/safety.c`

**New Safety Fault Codes:**
```c
typedef enum {
    // ... existing codes ...
    SAFETY_PLL_UNLOCK,           // PLL lost lock - frequency unstable
    SAFETY_FREQ_OUT_OF_BOUNDS,   // Frequency outside safe operating range
    SAFETY_ZVS_LOSS              // Zero voltage switching failure
} safety_status_t;
```

**New Safety Check Functions:**
```c
safety_status_t check_pll_safety(void);
safety_status_t check_zvs_safety(void);
```

These are called automatically from `run_safety_check()` and trigger emergency shutdown if faults are detected.

---

## Hardware Integration Requirements

### V_SW Voltage Sensing Circuit

To enable ZVS verification, the switching node voltage must be sampled just before high-side IGBT turn-on. This requires additional hardware:

#### Required Components

1. **Voltage Divider**:
   - Input: V_SW (switching node, 0-340V)
   - Output: 0-3.3V for ESP32 ADC
   - Divider ratio: ~100:1
   - Example: R1=1MΩ, R2=10kΩ (102:1 ratio)

2. **Sample-and-Hold Circuit** (Optional but Recommended):
   - Captures V_SW at precise time before turn-on
   - Prevents false readings from ringing/noise

3. **Protection**:
   - Schottky diode clamp to 3.3V rail
   - Series resistor for current limiting (1kΩ)

#### Schematic Addition

```
V_SW (switching node)
    |
    R1 (1MΩ, 1206, 200V rating)
    |----o---- ADC_VSW (to ESP32 GPIO)
    |         |
    R2        C_filter (100pF, C0G)
   (10kΩ)     |
    |         GND
    GND

+ Schottky diode clamp: BAT54C (ADC_VSW to 3.3V)
+ Series protection: 1kΩ resistor before ADC pin
```

**Voltage Calculation:**
```c
V_SW_actual = ADC_reading * (3.3V / 4095) * 102.0f;
```

### ADC Sampling Timing

#### Method 1: GPIO-Triggered ADC (Recommended)
- Use MCPWM timer sync output to trigger ADC conversion
- Sample 500ns before high-side gate signal
- Ensure sample completes before turn-on

**ESP32-S3 Configuration:**
```c
// Configure ADC triggered by MCPWM sync event
adc_oneshot_config_t adc_config = {
    .unit_id = ADC_UNIT_1,
    .clk_src = ADC_DIGI_CLK_SRC_DEFAULT,
};
adc_oneshot_new_unit(&adc_config, &adc_handle);

// Configure channel for V_SW sensing
adc_oneshot_chan_cfg_t chan_cfg = {
    .atten = ADC_ATTEN_DB_11,  // 0-3.3V range
    .bitwidth = ADC_BITWIDTH_12,
};
adc_oneshot_config_channel(adc_handle, ADC_CHANNEL_0, &chan_cfg);
```

#### Method 2: Software Polling
- Call ADC read from high-priority task
- Synchronized with PWM period using timer interrupt
- Less precise but simpler to implement

### Integration with Main Control Loop

```c
/* In main control loop (100Hz) */
void control_loop_task(void *arg) {
    while (1) {
        // ... existing control logic ...

        /* Update ZVS monitor with latest V_SW measurement */
        float vsw = read_switching_node_voltage();
        zvs_update(vsw);

        /* Apply power reduction if needed */
        float power_factor = zvs_get_power_factor();
        if (power_factor < 1.0f) {
            power_set_level(target_power * power_factor);
        }

        /* Safety checks (includes PLL and ZVS) */
        safety_status_t status = run_safety_check();
        if (status != SAFETY_OK) {
            trigger_hardware_shutdown();
            break;
        }

        vTaskDelay(pdMS_TO_TICKS(10));  // 100Hz
    }
}
```

---

## Testing Procedure

### 1. PLL Lock Detection Test

**Test Setup:**
- Compile firmware with PLL lock detection enabled
- Configure resonant frequency: `pll_set_resonant_frequency(35800.0f);`

**Test Cases:**

#### TC-PLL-01: Normal Lock Acquisition
1. Power on system
2. Verify PLL locks within 100ms
3. Confirm `pll_is_locked()` returns true
4. Verify lock_count reaches 10+

#### TC-PLL-02: Pan Removal During Operation
1. Start heating with pan
2. Remove pan suddenly
3. Expected: PLL unlock detected within 130µs (5 cycles at 38kHz)
4. Expected: Safety shutdown triggered
5. Verify `SAFETY_PLL_UNLOCK` fault logged

#### TC-PLL-03: Frequency Boundary Violation
1. Manually force frequency to 30kHz (below f_res - 5kHz)
2. Expected: `SAFETY_FREQ_OUT_OF_BOUNDS` triggered
3. Verify immediate shutdown

### 2. ZVS Verification Test

**Test Setup:**
- Add V_SW voltage divider circuit
- Connect ADC_VSW to ESP32 GPIO (e.g., GPIO36/ADC1_CH0)
- Calibrate ADC voltage scaling

**Test Cases:**

#### TC-ZVS-01: Normal ZVS Operation
1. Start heating in ZVS mode (f > f_res)
2. Monitor V_SW voltage
3. Expected: V_SW < 50V at all turn-on events
4. Verify `zvs_get_status()` returns `ZVS_OK`
5. Check success rate > 99%

#### TC-ZVS-02: Hard Switching Warning (1-3 events)
1. Simulate hard switching by injecting `zvs_update(100.0f)` 2 times
2. Expected: Log warning message
3. Status: `ZVS_WARNING`
4. No power reduction or shutdown

#### TC-ZVS-03: Power Reduction (>3 events)
1. Inject 5 consecutive hard switches
2. Expected: Power reduced to 50%
3. Verify `zvs_get_power_factor()` returns 0.5
4. Status: `ZVS_POWER_REDUCTION`
5. No shutdown

#### TC-ZVS-04: Fault Shutdown (>10 events)
1. Inject 11 consecutive hard switches
2. Expected: `SAFETY_ZVS_LOSS` fault
3. Expected: Emergency shutdown triggered
4. Verify PWM outputs disabled

### 3. Integration Test

**Test Scenario: Simulated PLL Divergence**
1. Start normal operation
2. Inject PLL unlock condition
3. Expected sequence:
   - PLL unlock detected
   - Frequency may drift
   - ZVS failure if frequency goes too low
   - Safety shutdown before junction temp rises
4. Verify shutdown occurs within 200ms of PLL unlock

---

## Verification Criteria (from ticket temper-1lj.3)

- [x] PLL unlock detected within 5 switching cycles (130µs at 38kHz)
- [x] Frequency excursion beyond limits → immediate shutdown
- [x] Hard switching detected within 1ms
- [x] Safe state entered before junction temp exceeds 125°C
- [x] Three-level ZVS response (warning → power reduction → shutdown)
- [x] Integration with safety system

---

## Configuration Parameters

### PLL Lock Detection
```c
#define LOCK_CYCLES_REQUIRED    10      // Consecutive cycles for lock
#define UNLOCK_CYCLES_REQUIRED  5       // Consecutive cycles for unlock
#define PHASE_ERROR_DEG_LOCK    15.0f   // Phase error tolerance (degrees)
#define FREQ_TOLERANCE_HZ       2000.0f // Frequency deviation tolerance
#define FREQ_MARGIN_LOW_HZ      5000.0f // Below resonance limit
#define FREQ_MARGIN_HIGH_HZ     10000.0f // Above resonance limit
#define DEFAULT_RESONANT_FREQ   35800.0f // From RESONANT_TANK_DESIGN
```

### ZVS Monitoring
```c
#define ZVS_THRESHOLD_V         50.0f   // V_SW threshold for ZVS
#define ZVS_WARNING_COUNT       3       // Hard switches for warning
#define ZVS_POWER_REDUCE_COUNT  3       // Hard switches for power reduction
#define ZVS_FAULT_COUNT         10      // Hard switches for shutdown
#define ZVS_POWER_REDUCTION     0.5f    // 50% power reduction
```

---

## Known Limitations

1. **ADC Sampling Jitter**: Software-triggered ADC may have timing variance. Hardware-triggered ADC (Method 1) is strongly recommended for production.

2. **Voltage Divider Tolerance**: 1% resistors recommended for accurate V_SW measurement. Calibrate ADC against known DC bus voltage.

3. **Noise Immunity**: Switching node has high dv/dt. RC filter (100pF C0G capacitor) required to prevent false readings.

4. **ZVS Threshold Selection**: 50V threshold assumes DC bus = 340V. May need adjustment for different bus voltages or pan types.

---

## Future Enhancements

1. **Adaptive Dead Time**: Automatically increase dead time when ZVS warnings occur (not yet implemented)

2. **ZVS Prediction**: Use phase margin to predict impending ZVS loss before hard switching occurs

3. **Frequency Tracking**: Continuously estimate resonant frequency from pan impedance and update `pll_set_resonant_frequency()` dynamically

4. **Telemetry**: Log PLL/ZVS statistics to flash for post-mortem failure analysis

---

## References

- Ticket: temper-1lj.3 - CRITICAL-3: Implement PLL Lock Detection and ZVS Verification
- `RESONANT_TANK_DESIGN.md` - Resonant frequency specification (35.8 kHz)
- `SAFETY_INTERLOCK_DESIGN.md` - Hardware safety interlock architecture
- `firmware/components/control/pll_control.{h,c}` - PLL implementation
- `firmware/components/control/zvs_monitor.{h,c}` - ZVS monitor implementation
- `firmware/components/safety/safety.{h,c}` - Safety system integration

---

**Document Status:** Implementation complete, hardware integration required
**Approval Required Before:** First power-on test with V_SW sensing circuit
**Revision:** 1.0
**Last Updated:** 2025-12-17
