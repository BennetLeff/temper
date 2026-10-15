# Temper Induction Cooktop Firmware

ESP32-S3 based firmware for the Temper induction cooktop, implementing a state machine-driven control system with comprehensive safety features.

## Architecture

### State Machine

The firmware is organized around a central state machine (`main/state_machine.c`) with the following states:

| State | Description |
|-------|-------------|
| `INIT` | Power-on self-test (POST) |
| `IDLE` | Standby mode, awaiting user input |
| `PAN_DET` | Pan detection phase (5s timeout) |
| `PREHEAT` | Aggressive heating to approach target |
| `HEATING` | Precision PID temperature control |
| `NO_PAN` | Pan removed pause (3s window to replace) |
| `COOLDOWN` | Active cooling after stop |
| `FAULT` | Safety lockout (requires reset) |

### Components

```
firmware/
├── main/
│   ├── state_machine.c    # Core state machine logic
│   ├── state_machine.h    # Public API and type definitions
│   └── main.c             # Application entry point
├── components/
│   ├── control/           # PID controller, PLL tracking
│   ├── hal/               # Hardware abstraction layer
│   └── safety/            # Safety monitoring and fault handling
└── test/                  # Host-based unit and integration tests
```

## Controller pin map (zapote/controller, layout L2 + L3 blower + stage 16 BLW_PG)

The firmware targets the integrated SELV controller. Its single pin map is
`components/hal/include/controller_pins.h` (numbers) plus the table in
`components/hal/controller_board.c` (function, owner, pulls, boot level).
`tools/check_controller_pinmap.py` checks both against the controller ato
(snapshot in `test/fixtures/controller-layout/`, or `--git-ref controller-layout`),
and `test/test_controller_pins.c` pins the rules below. Every module GPIO is
used; there is no spare pin.

- **RUN_EN = GPIO14** (DECISIONS C23). PERMIT = interlock latch AND RUN_EN
  (U37). 4.7 k pull-down, no internal pull-up; preset low before the pad
  becomes an output. Firmware can only remove permission with it; the
  safety cut (`ctrl_board_run_en_kill()`) latches it low until MCU reset.
  There is no RUNAWAY_CUT output on this board (GPIO15 is PWM_HB).
- **IL_WDI = GPIO18** (TPS3823 heartbeat). SUP_RUN_OK and RTD_DRDY are
  TCA9555 P14 and P07, polled over I2C every control tick.
- **TCA9555 (U8) bits**: P07 RTD_DRDY (low = ready), P10 LATCHED_FAULT_RB,
  P11 RTD_FAULT_RB, P12 HS_FAULT_RB, P13 COIL_FAULT_RB, P14 SUP_RUN_OK_RB,
  P15 FAN_OFF (L3, the only output), **P16 BLW_PG** (stage 16, C33: high = PS3
  present; input only), P06 reserved (second MAX31865 CS). `CTRL_EXP_<NET>` =
  8 × port + bit.
- **I2C**: SDA GPIO37, SCL GPIO0 (SPI-boot strap, 4.7 k pull-up; never an
  internal pull-down).
- **UI bus (J7, SPI3)**: SCK 40, MOSI 41, MISO 44, CS_OLED# 47, D/C 45,
  CS_EXP# 48. GPIO44 is U0RXD, so the console is USB-Serial-JTAG
  (`sdkconfig.defaults`). GPIO45 is the VDD_SPI strap: never an internal
  pull-up. The sounder is a self-oscillating buzzer on a UI-board expander
  output; there is no sounder PWM.
- **Rim NTC = GPIO9 / ADC1_CH8** (R36, C27, C31), ninth slot of the ADC1 pattern;
  Semitec 104GT-2 on a 1.00 k pull-up (0.489 V, 7.0 mV/K at 250 °C). It feeds
  the 250 °C pan cap with the pan RTD (`components/control/thermal_mgmt.h`).
- **Blower (J10, L3, C28)**: 3-wire (V, GND, FG). Speed: GPIO46 LEDC, 20 kHz,
  into the buck FB; **duty 0 = full speed** (12.2 V), capped at 85 % (≥ 6.07 V
  at every corner, above the blower's 5.5 V floor). Reset / brown-out leaves
  GPIO46 an input on its 100 k strap pull-down: 11.0–11.4 V, still near full
  speed. On/off: expander P15 FAN_OFF (latch written 0 = on before it becomes
  an output). Tach: FG → GPIO3 PCNT; pulses per revolution is
  `BLOWER_TACH_PULSES_PER_REV` in `config.yaml` (unverified, default 2). A
  stopped, locked or unplugged blower or an open FG wire reads 0 rpm and
  derates tank power after 1 s (`blower_ctrl_step()`).
- **Blower supply and the inlet limit (stage 16)**: the blower runs from PS3
  (MPM-65-15ST, power-board tap F2 / J11, also the controller logic since
  s38; PS1 is deleted), so the inlet estimate's auxiliary allowance is PS2 +
  PS3 logic (0.26 A) + the PS3 blower term scheduled from the commanded drive
  (`components/power/blower_aux.h`), each counted by its worst-corner increment
  to the inlet RMS: 0.31 A off, 0.65 A typical, 0.887 A at full speed or
  whenever the drive is unknown. A speed-up takes the allowance first
  and moves the blower 300 ms later; a fault goes to full speed at once. The
  regulated inlet total stays 13.5 A (COMMISSIONING.md step 8c).
- **BLW_PG, PS3 present (expander P16, controller C33)**: 20 k / 4.7 k from
  V15_BLW at J13, ≥ 2.74 V with PS3 on, ≤ 0.30 V without it. Debounced in the
  expander poll: 3 equal reads at 10 ms before it is "present" or "absent"; a
  failed or stale expander read is **unknown**, never "present"
  (`ctrl_blw_pg_update()`, `ctrl_exp_blw_pg()`). Use (`blower_ctrl_supply()`):
  - FG at 0 Hz while driven (the stall path) is labelled for the UI / log:
    BLW_PG 0 → **PS3 absent**, BLW_PG 1 → **blower failed**, unknown → the
    plain stall. All three take the same C28 derate (and stop on a rising sink).
  - **Start interlock**: PS3 absent before heating starts → no start (IDLE
    shows "NO BLOWER PWR"; PAN_DET, which every start path enters, applies no
    power and returns to IDLE). Unknown does not block: the stall path still
    protects.
  - **Plausibility**: BLW_PG 0 while the tach shows the blower turning for
    > 3 s (`BLW_PG_PLAUS_TIME_MS`, provisional) latches a BLW_PG sense fault
    until reset; BLW_PG is then ignored (stall-only behaviour). No derate on
    that alone.
  - The PS3 inlet allowance never drops on BLW_PG 0: PS3's AC side may still
    draw with a failed output (`blower_aux.h`).

## Thermal trip ladder (L3, DECISIONS C32)

| | Fan law | Firmware derate | Firmware trip | Hardware trip (band) |
|---|---|---|---|---|
| Heatsink (Vishay NTCALUG01A104GA) | 88.6 °C | — | 95 °C (`OVER_TEMP_THRESHOLD`) | 101.4 °C (98.3–104.6) |
| Coil (Semitec 104GT-2, 100 k / 300 °C) | 140 °C | 150–160 °C | 165 °C (`COIL_FW_TRIP_C`) | 175.7 °C (169.7–182.0) |

Source: `docs/evidence/2026-10-12-thermal-trip-ladder-l3.md`, which supersedes
the IGBT-era 80 °C trip of `2026-08-15-thermal-threshold-decision.md`.
`test/test_thermal_mgmt.c` fails if any rung is reordered. Every NTC input has
a 10 k / 100 nF filter (C29): readings are used only after it has settled
(`ntc_input_settled()`, ≤ 28 ms from power-up), and its ≤ 3.3 ms lag is
negligible next to the 100 ms thermal ticks. The ESP32-S3 ADC reads only up
to ~3.1 V, so on a 10 k pull-up a 100 k NTC colder than ~15 °C (or open)
reads as the range floor: the interlocks treat it as cool, the blower runs
full speed, and the thermal-sense OPEN_REF comparator latches a real open.
The rim (1.00 k pull-up) resolves only above ~70 °C; below that, or open, it
gives no rim cap and the pan RTD still caps at 250 °C.

Because cold and open read alike, a plausibility check (`thermal_plaus_t`,
run on every heating tick) latches a **rim-sensor fault** when the rim stays
below range for > 30 s while the pan RTD reads > 150 °C (rim dropped from the
cap; the pan RTD alone caps), and a **coil-sensor fault** when the coil reads
< 25 °C after > 5 min at > 50 % power (tank clamped to 22 A, blower full
speed). Both are shown on the display and held until MCU reset; the
constants are bench-tunable (`components/power/COMMISSIONING.md` step 8b).

`components/hal/include/temper_pins.h` is the legacy `elec/` board map, kept
unchanged for the tools that read it; controller firmware must not include it.

## Building

### Prerequisites

- ESP-IDF v5.0+ (for target builds)
- CMake 3.16+
- GCC (for host-based tests)

### Target Build (ESP32-S3)

```bash
cd firmware
idf.py set-target esp32s3
idf.py build
idf.py flash monitor
```

### Host Build (Tests Only)

```bash
cd firmware/test
mkdir -p build && cd build
cmake ..
make
```

## Testing

The firmware includes comprehensive test coverage with:
- **37 unit tests** for state machine transitions
- **30 integration tests** for complete operational sequences

### Running Tests

```bash
cd firmware/test

# Build all test targets
mkdir -p build && cd build
cmake ..
make

# Run state machine unit tests
./test_state_machine_only

# Run integration tests
./test_integration_only

# Run all tests via CTest
ctest --output-on-failure
```

### Test Categories

#### Unit Tests (`test_state_machine.c`)
- State initialization and defaults
- Individual state transitions
- Self-test pass/fail scenarios
- Fault detection (OCP, OVP, thermal, probe)
- Fault recovery conditions
- API boundary testing

#### Integration Tests (`test_integration.c`)
- **Startup Sequence**: INIT → IDLE → PAN_DET → PREHEAT → HEATING
- **Normal Operation**: Temperature regulation, timer countdown, manual stop
- **Fault Injection**: Over-current, over-temp, fan failure, probe faults
- **Power Cycle**: Recovery from idle, heating, fault states
- **Stress Tests**: Rapid state changes, long duration, sensor noise

### Test Infrastructure

Tests use the [Unity](http://www.throwtheswitch.org/unity) test framework with mock HAL implementations:

- `state_machine_stubs.c` - Mock implementations for all HAL functions
- `mock_sm_*()` functions - Control mock behavior (temperatures, currents, buttons)
- Time simulation via `mock_sm_advance_time()`

Example test setup:
```c
void test_fault_over_current(void) {
    setup_test();  // Resets mocks and state machine
    
    /* Reach HEATING state */
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    // ... setup to reach HEATING ...
    
    /* Inject fault condition */
    mock_sm_set_dc_bus_current(45.0f);  // > 40A threshold
    state_machine_update();
    
    /* Verify fault handling */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_CURRENT, state_machine_get_fault());
}
```

## Safety Features

The firmware implements multiple layers of safety:

1. **Hardware Watchdog (TPS3823-33)**: External WDT fed every update cycle, 1.6s timeout
2. **Software Watchdog**: State-specific timeouts (1-10s depending on state)
3. **Over-Current Protection**: DC bus current >40A triggers immediate shutdown
4. **Over-Temperature Protection**: Heatsink >80°C triggers fault
5. **Fan Failure Detection**: Tachometer monitoring during operation
6. **RTD Probe Monitoring**: Open circuit (>10kΩ) and short circuit (<10Ω) detection
7. **Thermal Runaway Detection**: Pan temp exceeding target by >10°C
8. **Pan Detection**: Impedance-based detection with confidence threshold

## Configuration

Tunable parameters are declared in `firmware/config.yaml` and rendered into
`firmware/config.h` by `firmware/tools/gen_config.py`. See the manifest for
current values.

## API Reference

### Core Functions

```c
void state_machine_init(void);           // Initialize/reset state machine
void state_machine_update(void);         // Call from main loop (10-100Hz)
system_state_t state_machine_get_state(void);  // Get current state
fault_code_t state_machine_get_fault(void);    // Get active fault code
```

### User Control

```c
void state_machine_set_target_temp(float temp_celsius);  // Set target (50-250°C)
void state_machine_set_timer(bool enabled, uint32_t time_ms);  // Cooking timer
```

### Debug/Test

```c
const char* state_machine_get_state_string(system_state_t state);
const char* state_machine_get_fault_string(fault_code_t code);
void state_machine_force_state(system_state_t new_state);  // Testing only
```

## Contributing

1. All state machine changes require corresponding test updates
2. Run full test suite before committing: `ctest --output-on-failure`
3. Follow existing code style (K&R braces, 4-space indent)
4. Update this README for any API changes
